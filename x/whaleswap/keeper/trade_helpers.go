package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// tradeApplySwapLeg executes a single SwapLeg against the pool, persists pool state, and returns a TradeOperation.
// It returns (operation, in, out) for aggregator accounting. Trade recording happens in recordTradeWithOperations.
func (k Keeper) tradeApplySwapLeg(ctx context.Context, trader string, leg *whaleswapv1.SwapLeg, note string) (whaleswapv1.TradeOperation, sdk.Coin, sdk.Coin, error) {
	logger := k.Logger(sdk.UnwrapSDKContext(ctx))

	if leg == nil || leg.PoolId == 0 {
		return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id required")
	}
	logger.Info("tradeApplySwapLeg starting", "trader", trader, "pool_id", leg.PoolId, "swap_in", leg.SwapIn, "swap_out", leg.SwapOut)
	pool, gerr := k.PoolsMap.Get(ctx, leg.PoolId)
	if gerr != nil {
		return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, gerr
	}
	logger.Info("tradeApplySwapLeg got pool", "pool_coins", pool.Coins, "fee_pct", pool.FeePct)
	if len(pool.Coins) != 2 {
		return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
	}

	fee := math.LegacyNewDec(0)
	if pool.FeePct != "" {
		f, ferr := math.LegacyNewDecFromStr(pool.FeePct)
		if ferr != nil {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool fee_pct: "+ferr.Error())
		}
		fee = f
	}
	one := math.LegacyNewDec(1)

	hasIn := leg.SwapIn.Denom != "" && leg.SwapIn.Amount.IsPositive()
	hasOut := leg.SwapOut.Denom != "" && leg.SwapOut.Amount.IsPositive()
	if hasIn && hasOut {
		return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_in and swap_out cannot both be set; specify exactly one per leg and use message-level max_input/min_output for global constraints")
	}
	if !hasIn && !hasOut {
		return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "leg requires swap_in or swap_out")
	}

	inputIdx := -1
	outputIdx := -1
	var targetOutAmt math.Int
	var actualInCoin sdk.Coin
	var outAmt math.Int
	var outDenom string
	if hasIn {
		if leg.SwapIn.Denom == pool.Coins[0].Denom {
			inputIdx = 0
		} else if leg.SwapIn.Denom == pool.Coins[1].Denom {
			inputIdx = 1
		} else {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "input denom %s not in pool %d", leg.SwapIn.Denom, leg.PoolId)
		}
		outputIdx = 1 - inputIdx
		actualInCoin = leg.SwapIn
	} else {
		if leg.SwapOut.Denom == pool.Coins[0].Denom {
			outputIdx = 0
		} else if leg.SwapOut.Denom == pool.Coins[1].Denom {
			outputIdx = 1
		} else {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "output denom %s not in pool %d", leg.SwapOut.Denom, leg.PoolId)
		}
		inputIdx = 1 - outputIdx
		targetOutAmt = leg.SwapOut.Amount
	}

	if len(pool.MinPrice) == 2 {
		// concentrated liquidity math
		sa, sb, err := k.bandSqrt(pool)
		if err != nil {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, err
		}
		sp, err := k.poolSqrtPrice(pool, pool.Coins[0].Denom, pool.Coins[1].Denom)
		if err != nil {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, err
		}
		L, _, _, err := k.liquidityForReserves(pool)
		if err != nil {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, err
		}
		if !L.IsPositive() {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool liquidity")
		}
		if hasIn {
			effIn := math.LegacyNewDecFromInt(actualInCoin.Amount).Mul(one.Sub(fee))
			feeInt := actualInCoin.Amount.Sub(effIn.TruncateInt())
			if feeInt.IsPositive() {
				pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(actualInCoin.Denom, feeInt))
			}
			if inputIdx == 0 {
				invSpPrime := math.LegacyOneDec().Quo(sp).Add(effIn.Quo(L))
				if invSpPrime.LTE(math.LegacyZeroDec()) {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity")
				}
				spPrime, err := k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
				if err != nil {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, err
				}
				if spPrime.LT(sa) {
					spPrime = sa
				}
				outAmt = L.Mul(sp.Sub(spPrime)).TruncateInt()
			} else {
				spPrime := sp.Add(effIn.Quo(L))
				if spPrime.GT(sb) {
					spPrime = sb
				}
				outAmt = L.Mul(math.LegacyOneDec().Quo(sp).Sub(math.LegacyOneDec().Quo(spPrime))).TruncateInt()
			}
		} else {
			// exact-out
			if !targetOutAmt.IsPositive() {
				return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_out must be > 0")
			}
			if outputIdx == 1 { // token0-in
				outDec := math.LegacyNewDecFromInt(targetOutAmt)
				spPrime := sp.Sub(outDec.Quo(L))
				if spPrime.LT(sa) {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds band capacity")
				}
				effInDec := L.Mul(math.LegacyOneDec().Quo(spPrime).Sub(math.LegacyOneDec().Quo(sp)))
				gross := effInDec.Quo(one.Sub(fee)).Ceil().TruncateInt()
				if !gross.IsPositive() {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
				}
				effInActual := math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
				invSpPrime := math.LegacyOneDec().Quo(sp).Add(effInActual.Quo(L))
				spPrimeAct, err := k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
				if err != nil {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, err
				}
				outAct := L.Mul(sp.Sub(spPrimeAct)).TruncateInt()
				if outAct.LT(targetOutAmt) {
					gross = gross.AddRaw(1)
					effInActual = math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
					invSpPrime = math.LegacyOneDec().Quo(sp).Add(effInActual.Quo(L))
					spPrimeAct, err = k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
					if err != nil {
						return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to compute next sqrt price (recheck)")
					}
					outAct = L.Mul(sp.Sub(spPrimeAct)).TruncateInt()
					if outAct.LT(targetOutAmt) {
						return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out: outAct=%s targetOutAmt=%s", outAct.String(), targetOutAmt.String())
					}
				}
				feeInt := gross.Sub(effInActual.TruncateInt())
				if feeInt.IsPositive() {
					pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[0].Denom, feeInt))
				}
				pool.Coins = sdk.NewCoins(
					sdk.NewCoin(pool.Coins[0].Denom, pool.Coins[0].Amount.Add(gross)),
					sdk.NewCoin(pool.Coins[1].Denom, pool.Coins[1].Amount.Sub(targetOutAmt)),
				)
				outAmt = targetOutAmt
				outDenom = pool.Coins[1].Denom
				actualInCoin = sdk.NewCoin(pool.Coins[0].Denom, gross)
			} else { // token1-in
				outDec := math.LegacyNewDecFromInt(targetOutAmt)
				denom := math.LegacyOneDec().Quo(sp).Sub(outDec.Quo(L))
				if !denom.IsPositive() {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds pool capacity")
				}
				spPrime := math.LegacyOneDec().Quo(denom)
				if spPrime.GT(sb) {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds band capacity")
				}
				effInDec := L.Mul(spPrime.Sub(sp))
				gross := effInDec.Quo(one.Sub(fee)).Ceil().TruncateInt()
				if !gross.IsPositive() {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
				}
				effInActual := math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
				spPrimeAct := sp.Add(effInActual.Quo(L))
				outAct := L.Mul(math.LegacyOneDec().Quo(sp).Sub(math.LegacyOneDec().Quo(spPrimeAct))).TruncateInt()
				if outAct.LT(targetOutAmt) {
					gross = gross.AddRaw(1)
					effInActual = math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
					spPrimeAct = sp.Add(effInActual.Quo(L))
					outAct = L.Mul(math.LegacyOneDec().Quo(sp).Sub(math.LegacyOneDec().Quo(spPrimeAct))).TruncateInt()
					if outAct.LT(targetOutAmt) {
						return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out")
					}
				}
				feeInt := gross.Sub(effInActual.TruncateInt())
				if feeInt.IsPositive() {
					pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[1].Denom, feeInt))
				}
				pool.Coins = sdk.NewCoins(
					sdk.NewCoin(pool.Coins[0].Denom, pool.Coins[0].Amount.Sub(targetOutAmt)),
					sdk.NewCoin(pool.Coins[1].Denom, pool.Coins[1].Amount.Add(gross)),
				)
				outAmt = targetOutAmt
				outDenom = pool.Coins[0].Denom
				actualInCoin = sdk.NewCoin(pool.Coins[1].Denom, gross)
			}
		}
		// exact-in reserves update and out denom
		if hasIn {
			if inputIdx == 0 {
				new0 := pool.Coins[0].Amount.Add(actualInCoin.Amount)
				new1 := pool.Coins[1].Amount.Sub(outAmt)
				if !new1.IsPositive() {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap would deplete quote reserve to zero in pool %d: quote_reserve=%s, swap_output=%s", leg.PoolId, pool.Coins[1].String(), outAmt.String())
				}
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
				outDenom = pool.Coins[1].Denom
			} else {
				new0 := pool.Coins[0].Amount.Sub(outAmt)
				if !new0.IsPositive() {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap would deplete base reserve to zero in pool %d: base_reserve=%s, swap_output=%s", leg.PoolId, pool.Coins[0].String(), outAmt.String())
				}
				new1 := pool.Coins[1].Amount.Add(actualInCoin.Amount)
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
				outDenom = pool.Coins[0].Denom
			}
		}
		// band check
		rBase := pool.Coins[0].Amount
		rQuote := pool.Coins[1].Amount
		denomA, denomB := pool.Coins[0].Denom, pool.Coins[1].Denom
		minBase := pool.MinPrice.AmountOf(denomA)
		minQuote := pool.MinPrice.AmountOf(denomB)
		maxBase := pool.MaxPrice.AmountOf(denomA)
		maxQuote := pool.MaxPrice.AmountOf(denomB)
		if rQuote.Mul(minBase).LT(rBase.Mul(minQuote)) {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price below band after swap in pool %d: reserves=[%s%s,%s%s], min_price=%s%s/%s%s", leg.PoolId, rBase.String(), denomA, rQuote.String(), denomB, minBase.String(), denomA, minQuote.String(), denomB)
		}
		if rQuote.Mul(maxBase).GT(rBase.Mul(maxQuote)) {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price above band after swap in pool %d: reserves=[%s%s,%s%s], max_price=%s%s/%s%s", leg.PoolId, rBase.String(), denomA, rQuote.String(), denomB, maxBase.String(), denomA, maxQuote.String(), denomB)
		}
	} else {
		// v2 constant product
		rIn := math.LegacyNewDecFromInt(pool.Coins[inputIdx].Amount)
		rOut := math.LegacyNewDecFromInt(pool.Coins[outputIdx].Amount)
		if hasIn {
			effIn := math.LegacyNewDecFromInt(actualInCoin.Amount).Mul(one.Sub(fee))
			feeInt := actualInCoin.Amount.Sub(effIn.TruncateInt())
			if feeInt.IsPositive() {
				pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(actualInCoin.Denom, feeInt))
			}
			kDec := rIn.Mul(rOut)
			q := kDec.Quo(rIn.Add(effIn)).Ceil()
			outDec := rOut.Sub(q)
			outAmt = outDec.TruncateInt()
			if !outAmt.IsPositive() {
				return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap output too small in pool %d: input=%s%s, computed_output=%s, reserves=[%s,%s], fee=%s", leg.PoolId, actualInCoin.Amount.String(), actualInCoin.Denom, outAmt.String(), pool.Coins[inputIdx].String(), pool.Coins[outputIdx].String(), fee.String())
			}
			newIn := pool.Coins[inputIdx].Amount.Add(actualInCoin.Amount)
			newOut := pool.Coins[outputIdx].Amount.Sub(outAmt)
			if !newOut.IsPositive() {
				return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap would deplete output reserve to zero in pool %d: output_reserve=%s, swap_output=%s", leg.PoolId, pool.Coins[outputIdx].String(), outAmt.String())
			}
			if inputIdx == 0 {
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, newIn), sdk.NewCoin(pool.Coins[1].Denom, newOut))
				outDenom = pool.Coins[1].Denom
			} else {
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, newOut), sdk.NewCoin(pool.Coins[1].Denom, newIn))
				outDenom = pool.Coins[0].Denom
			}
		} else {
			out := math.LegacyNewDecFromInt(targetOutAmt)
			if out.GTE(rOut) {
				return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "exact-out equals/exceeds reserve in pool %d: requested_output=%s, output_reserve=%s", leg.PoolId, targetOutAmt.String(), pool.Coins[outputIdx].String())
			}
			effInReq := rIn.Mul(rOut.Quo(rOut.Sub(out)).Sub(one))
			gross := effInReq.Quo(one.Sub(fee)).Ceil().TruncateInt()
			if !gross.IsPositive() {
				return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "computed input not positive in pool %d: requested_output=%s, reserves=[%s,%s], fee=%s", leg.PoolId, targetOutAmt.String(), pool.Coins[inputIdx].String(), pool.Coins[outputIdx].String(), fee.String())
			}
			effInActual := math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
			kDec := rIn.Mul(rOut)
			q := kDec.Quo(rIn.Add(effInActual)).Ceil()
			outDec := rOut.Sub(q)
			outAct := outDec.TruncateInt()
			if outAct.LT(targetOutAmt) {
				gross = gross.AddRaw(1)
				effInActual = math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
				q = kDec.Quo(rIn.Add(effInActual)).Ceil()
				outDec = rOut.Sub(q)
				outAct = outDec.TruncateInt()
				if outAct.LT(targetOutAmt) {
					return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out in pool %d: requested=%s, achievable=%s, reserves=[%s,%s]", leg.PoolId, targetOutAmt.String(), outAct.String(), pool.Coins[inputIdx].String(), pool.Coins[outputIdx].String())
				}
			}
			feeInt := gross.Sub(effInActual.TruncateInt())
			if feeInt.IsPositive() {
				pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[inputIdx].Denom, feeInt))
			}
			newIn := pool.Coins[inputIdx].Amount.Add(gross)
			newOut := pool.Coins[outputIdx].Amount.Sub(targetOutAmt)
			if !newOut.IsPositive() {
				return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap would deplete output reserve to zero in pool %d: output_reserve=%s, requested_output=%s", leg.PoolId, pool.Coins[outputIdx].String(), targetOutAmt.String())
			}
			if inputIdx == 0 {
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, newIn), sdk.NewCoin(pool.Coins[1].Denom, newOut))
				outDenom = pool.Coins[1].Denom
			} else {
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, newOut), sdk.NewCoin(pool.Coins[1].Denom, newIn))
				outDenom = pool.Coins[0].Denom
			}
			outAmt = targetOutAmt
			actualInCoin = sdk.NewCoin(pool.Coins[inputIdx].Denom, gross)
		}
	}

	// Enforce rate constraint when both swap_in and swap_out are provided
	if hasIn && hasOut {
		if leg.SwapOut.Denom != outDenom {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap_out denom %s doesn't match computed %s", leg.SwapOut.Denom, outDenom)
		}
		if !outAmt.Equal(leg.SwapOut.Amount) {
			return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "computed out %s != required %s", outAmt.String(), leg.SwapOut.Amount.String())
		}
	}

	// Persist pool and emit events
	pool.NumTrades += 1
	if err := k.updatePool(ctx, &pool); err != nil {
		return whaleswapv1.TradeOperation{}, sdk.Coin{}, sdk.Coin{}, err
	}
	// EventPoolSwap emitted by recordTradeWithOperations (with trade_id and operation_index)

	// Build operation record with execution results
	op := whaleswapv1.TradeOperation{
		Op:       &whaleswapv1.TradeOperation_Swap{Swap: leg},
		Sent:     actualInCoin,
		Received: sdk.NewCoin(outDenom, outAmt),
	}

	logger.Info("tradeApplySwapLeg completed", "sent", actualInCoin, "received", sdk.NewCoin(outDenom, outAmt))
	return op, actualInCoin, sdk.NewCoin(outDenom, outAmt), nil
}

// tradeApplyTakeItem executes one TakeItem: updates the offer, and returns a TradeOperation.
// Returns (operation, maker, makerWant, takerRecv, makerLiqIn, pfandReleased, error).
// Trade recording happens in recordTradeWithOperations.
func (k Keeper) tradeApplyTakeItem(ctx context.Context, taker string, item *whaleswapv1.TakeItem, note string) (whaleswapv1.TradeOperation, string, sdk.Coin, sdk.Coin, sdk.Coin, sdk.Coin, error) {
	logger := k.Logger(sdk.UnwrapSDKContext(ctx))

	if item == nil || item.OfferId == 0 {
		return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "offer_id required")
	}
	logger.Info("tradeApplyTakeItem starting", "taker", taker, "offer_id", item.OfferId, "take_units", item.TakeUnits)
	offer, err := k.OffersMap.Get(ctx, item.OfferId)
	if err != nil {
		return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "offer not found: %d", item.OfferId)
	}
	logger.Info("tradeApplyTakeItem got offer", "maker", offer.Maker, "remaining_units", offer.RemainingUnits, "unit_have", offer.UnitHaveInt, "unit_want", offer.UnitWantInt)
	if offer.Status != whaleswapv1.OfferStatusOpen {
		return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "offer %d not open", item.OfferId)
	}
	remainingUnits, ok := math.NewIntFromString(offer.RemainingUnits)
	if !ok || !remainingUnits.IsPositive() {
		return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid remaining units")
	}
	takeUnits, perr := k.parseTakeUnits(remainingUnits, item.TakeUnits)
	if perr != nil {
		return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, perr
	}
	unitWant, _ := math.NewIntFromString(offer.UnitWantInt)
	unitHave, _ := math.NewIntFromString(offer.UnitHaveInt)
	requiredWant := takeUnits.Mul(unitWant)
	deliverHave := takeUnits.Mul(unitHave)

	wantDenom := offer.RemainingWant.Denom
	haveDenom := offer.RemainingHave.Denom
	maker := offer.Maker

	// Update offer
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	t := sdkCtx.BlockTime()
	newUnits := remainingUnits.Sub(takeUnits)
	offer.UpdatedHeight = uint64(sdkCtx.BlockHeight())
	offer.UpdatedTimestamp = &t
	var pfandReleased sdk.Coin
	if newUnits.IsZero() {
		offer.Status = whaleswapv1.OfferStatusClosed
		offer.RemainingUnits = newUnits.String()
		offer.RemainingHave.Amount = math.NewInt(0)
		offer.RemainingWant.Amount = math.NewInt(0)
		if offer.PfandLocked.Amount.IsPositive() {
			pfandReleased = offer.PfandLocked
		}
	} else {
		offer.RemainingUnits = newUnits.String()
		offer.RemainingHave.Amount = newUnits.Mul(unitHave)
		offer.RemainingWant.Amount = newUnits.Mul(unitWant)
	}

	// Persist offer and emit events
	prev, _ := k.OffersMap.Get(ctx, offer.OfferId)
	if err := k.OffersMap.Set(ctx, offer.OfferId, offer); err != nil {
		return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(err, "failed to update offer %d", offer.OfferId)
	}
	if err := k.reindexOfferOnStatusChange(ctx, prev, offer); err != nil {
		return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, err
	}
	// EventOfferTaken and EventPfandReleased emitted by recordTradeWithOperations (with proper IDs)

	// Received denom is base have denom
	recDenom := haveDenom

	// Build operation record with execution results
	op := whaleswapv1.TradeOperation{
		Op:       &whaleswapv1.TradeOperation_Take{Take: item},
		Sent:     sdk.NewCoin(wantDenom, requiredWant),
		Received: sdk.NewCoin(recDenom, deliverHave),
	}

	// Aggregator contributions
	makerWant := sdk.NewCoin(wantDenom, requiredWant)
	var takerRecv sdk.Coin
	var makerLiqIn sdk.Coin
	takerRecv = sdk.NewCoin(haveDenom, deliverHave)
	// Liquid vs Escrow settlement handling:
	// In LIQUID mode, the maker must fund base-have. Require sufficient balance and add as maker input.
	// In ESCROW mode, the module funds base-have (added later by caller); makerLiqIn remains zero.
	if offer.SettlementMode == whaleswapv1.SettlementMode_SETTLEMENT_LIQUID {
		makerAddr, addrErr := sdk.AccAddressFromBech32(maker)
		if addrErr != nil {
			return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(addrErr, "invalid maker address")
		}
		bal := k.bank.GetBalance(ctx, makerAddr, haveDenom).Amount
		if bal.LT(deliverHave) {
			return whaleswapv1.TradeOperation{}, "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "maker lacks base-have for liquid settlement %s: %s < %s", haveDenom, bal.String(), deliverHave.String())
		}
		makerLiqIn = sdk.NewCoin(haveDenom, deliverHave)
	}
	logger.Info("tradeApplyTakeItem solid denom", "taker_recv", takerRecv)
	logger.Info("tradeApplyTakeItem completed", "maker", maker, "maker_want", makerWant, "taker_recv", takerRecv, "maker_liq_in", makerLiqIn, "pfand_released", pfandReleased)
	return op, maker, makerWant, takerRecv, makerLiqIn, pfandReleased, nil
}

// tradeNetAndCover performs orderbook-style netting and coverage on the aggregator maps.
func (k Keeper) tradeNetAndCover(ctx context.Context, traderBech string, inputsByAddr, outputsByAddr map[string]sdk.Coins) error {
	logger := k.Logger(sdk.UnwrapSDKContext(ctx))

	logger.Info("x/whaleswap tradeNetAndCover starting", "trader_bech", traderBech, "inputs_by_addr_count", len(inputsByAddr), "outputs_by_addr_count", len(outputsByAddr))

	moduleBech := k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String()
	// maker wants (solid) - exclude trader
	makerWants := sdk.NewCoins()
	for addr, coins := range outputsByAddr {
		if addr == moduleBech || addr == traderBech {
			continue
		}
		for _, c := range coins {
			makerWants = makerWants.Add(c)
		}
	}
	// taker credits (solid)
	takerCredits := sdk.NewCoins()
	if tcoins, ok := outputsByAddr[traderBech]; ok {
		for _, c := range tcoins {
			takerCredits = takerCredits.Add(c)
		}
	}
	// First pass: compute nettable per denom and reduce trader credits accordingly
	logger.Info("x/whaleswap tradeNetAndCover maker wants and taker credits", "maker_wants", makerWants, "taker_credits", takerCredits)
	for _, want := range makerWants {
		denom := want.Denom
		wantAmt := want.Amount
		credit := takerCredits.AmountOf(denom)
		nettable := credit
		if wantAmt.LT(credit) {
			nettable = wantAmt
		}
		if nettable.IsPositive() {
			logger.Info("x/whaleswap tradeNetAndCover netting trader credits to maker wants", "denom", denom, "nettable", nettable)
			if coins, ok := outputsByAddr[traderBech]; ok {
				outputsByAddr[traderBech] = coins.Sub(sdk.NewCoin(denom, nettable))
				if outputsByAddr[traderBech].IsZero() {
					delete(outputsByAddr, traderBech)
				}
			}
			// Do NOT reduce module inputs here; module inputs (escrow/pfand/amm) must persist to fund obligations.
			// Reduce makers' wants by the same nettable amount across all makers ONLY if module isn't funding this denom
			if inputsByAddr[moduleBech].AmountOf(denom).IsZero() {
				remain := nettable
				for addr, coins := range outputsByAddr {
					if addr == traderBech || addr == moduleBech {
						continue
					}
					// find available amount for denom at this maker row
					avail := coins.AmountOf(denom)
					if avail.IsZero() {
						continue
					}
					use := avail
					if remain.LT(avail) {
						use = remain
					}
					if use.IsPositive() {
						logger.Info("x/whaleswap tradeNetAndCover reducing maker want row", "maker", addr, "denom", denom, "use", use)
						outputsByAddr[addr] = outputsByAddr[addr].Sub(sdk.NewCoin(denom, use))
						if outputsByAddr[addr].IsZero() {
							delete(outputsByAddr, addr)
						}
						remain = remain.Sub(use)
						if remain.IsZero() {
							break
						}
					}
				}
			}
		}
		if credit.GTE(wantAmt) {
			continue
		}
		deficit := wantAmt.Sub(credit)
		// Cover with taker base; no module payer-of-last-resort
		logger.Info("x/whaleswap tradeNetAndCover covering maker want deficit from taker base", "denom", denom, "deficit", deficit)
		takerAddr, _ := sdk.AccAddressFromBech32(traderBech)
		baseBal := k.bank.GetBalance(ctx, takerAddr, denom).Amount
		basePart := baseBal
		if basePart.GT(deficit) {
			basePart = deficit
		}
		if basePart.IsPositive() {
			logger.Info("x/whaleswap tradeNetAndCover adding taker input", "denom", denom, "amount", basePart)
			inputsByAddr[traderBech] = inputsByAddr[traderBech].Add(sdk.NewCoin(denom, basePart))
		}
		// No liquid remainder coverage
	}
	// Validate per-denom inputs cover outputs after maker/taker/module (escrow) contributions.
	outputsSolid := sdk.NewCoins()
	for _, coins := range outputsByAddr {
		for _, c := range coins {
			outputsSolid = outputsSolid.Add(c)
		}
	}
	inputsSolid := sdk.NewCoins()
	for _, coins := range inputsByAddr {
		for _, c := range coins {
			inputsSolid = inputsSolid.Add(c)
		}
	}
	// Compute union of denoms present
	seen := map[string]struct{}{}
	for _, c := range outputsSolid {
		seen[c.Denom] = struct{}{}
	}
	for _, c := range inputsSolid {
		seen[c.Denom] = struct{}{}
	}
	for den := range seen {
		outAmt := outputsSolid.AmountOf(den)
		inAmt := inputsSolid.AmountOf(den)
		if outAmt.GT(inAmt) {
			logger.Info("x/whaleswap tradeNetAndCover insufficient inputs", "denom", den, "inputs", inAmt.String(), "outputs", outAmt.String(), "inputs_by_addr", inputsByAddr, "outputs_by_addr", outputsByAddr)
			return cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient inputs for %s: %s < %s", den, inAmt.String(), outAmt.String())
		}
	}
	logger.Info("x/whaleswap tradeNetAndCover completed", "final_inputs_count", len(inputsByAddr), "final_outputs_count", len(outputsByAddr), "final_inputs", inputsByAddr, "final_outputs", outputsByAddr)
	return nil
}

// No liquid burn step remains.
