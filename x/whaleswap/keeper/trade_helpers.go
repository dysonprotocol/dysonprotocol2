package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// tradeApplySwapLeg executes a single SwapLeg against the pool, persists pool state, and records a Trade.
// It returns the (in, out) coins used for aggregator accounting.
func (k Keeper) tradeApplySwapLeg(ctx context.Context, trader string, leg *whaleswapv1.SwapLeg, note string) (sdk.Coin, sdk.Coin, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if leg == nil || leg.PoolId == 0 {
		return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id required")
	}
	pool, gerr := k.PoolsMap.Get(ctx, leg.PoolId)
	if gerr != nil {
		return sdk.Coin{}, sdk.Coin{}, gerr
	}
	if len(pool.Coins) != 2 {
		return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
	}

	fee := math.LegacyNewDec(0)
	if pool.FeePct != "" {
		f, ferr := math.LegacyNewDecFromStr(pool.FeePct)
		if ferr != nil {
			return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool fee_pct: "+ferr.Error())
		}
		fee = f
	}
	one := math.LegacyNewDec(1)

	hasIn := leg.SwapIn.Denom != "" && leg.SwapIn.Amount.IsPositive()
	hasOut := leg.SwapOut.Denom != "" && leg.SwapOut.Amount.IsPositive()
	if hasIn && hasOut {
		return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_in and swap_out cannot both be set; specify exactly one per leg and use message-level max_input/min_output for global constraints")
	}
	if !hasIn && !hasOut {
		return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "leg requires swap_in or swap_out")
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
			return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "input denom %s not in pool %d", leg.SwapIn.Denom, leg.PoolId)
		}
		outputIdx = 1 - inputIdx
		actualInCoin = leg.SwapIn
	} else {
		if leg.SwapOut.Denom == pool.Coins[0].Denom {
			outputIdx = 0
		} else if leg.SwapOut.Denom == pool.Coins[1].Denom {
			outputIdx = 1
		} else {
			return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "output denom %s not in pool %d", leg.SwapOut.Denom, leg.PoolId)
		}
		inputIdx = 1 - outputIdx
		targetOutAmt = leg.SwapOut.Amount
	}

	if len(pool.MinPrice) == 2 {
		// concentrated liquidity math
		sa, sb, err := k.bandSqrt(pool)
		if err != nil {
			return sdk.Coin{}, sdk.Coin{}, err
		}
		sp, err := k.poolSqrtPrice(pool, pool.Coins[0].Denom, pool.Coins[1].Denom)
		if err != nil {
			return sdk.Coin{}, sdk.Coin{}, err
		}
		L, _, _, err := k.liquidityForReserves(pool)
		if err != nil {
			return sdk.Coin{}, sdk.Coin{}, err
		}
		if !L.IsPositive() {
			return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool liquidity")
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
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity")
				}
				spPrime, err := k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
				if err != nil {
					return sdk.Coin{}, sdk.Coin{}, err
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
				return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_out must be > 0")
			}
			if outputIdx == 1 { // token0-in
				outDec := math.LegacyNewDecFromInt(targetOutAmt)
				spPrime := sp.Sub(outDec.Quo(L))
				if spPrime.LT(sa) {
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds band capacity")
				}
				effInDec := L.Mul(math.LegacyOneDec().Quo(spPrime).Sub(math.LegacyOneDec().Quo(sp)))
				gross := effInDec.Quo(one.Sub(fee)).Ceil().TruncateInt()
				if !gross.IsPositive() {
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
				}
				effInActual := math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
				invSpPrime := math.LegacyOneDec().Quo(sp).Add(effInActual.Quo(L))
				spPrimeAct, err := k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
				if err != nil {
					return sdk.Coin{}, sdk.Coin{}, err
				}
				outAct := L.Mul(sp.Sub(spPrimeAct)).TruncateInt()
				if outAct.LT(targetOutAmt) {
					gross = gross.AddRaw(1)
					effInActual = math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
					invSpPrime = math.LegacyOneDec().Quo(sp).Add(effInActual.Quo(L))
					spPrimeAct, err = k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
					if err != nil {
						return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to compute next sqrt price (recheck)")
					}
					outAct = L.Mul(sp.Sub(spPrimeAct)).TruncateInt()
					if outAct.LT(targetOutAmt) {
						return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out: outAct=%s targetOutAmt=%s", outAct.String(), targetOutAmt.String())
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
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds pool capacity")
				}
				spPrime := math.LegacyOneDec().Quo(denom)
				if spPrime.GT(sb) {
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds band capacity")
				}
				effInDec := L.Mul(spPrime.Sub(sp))
				gross := effInDec.Quo(one.Sub(fee)).Ceil().TruncateInt()
				if !gross.IsPositive() {
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
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
						return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out")
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
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap would deplete quote reserve to zero in pool %d: quote_reserve=%s, swap_output=%s", leg.PoolId, pool.Coins[1].String(), outAmt.String())
				}
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
				outDenom = pool.Coins[1].Denom
			} else {
				new0 := pool.Coins[0].Amount.Sub(outAmt)
				if !new0.IsPositive() {
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap would deplete base reserve to zero in pool %d: base_reserve=%s, swap_output=%s", leg.PoolId, pool.Coins[0].String(), outAmt.String())
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
			return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price below band after swap in pool %d: reserves=[%s%s,%s%s], min_price=%s%s/%s%s", leg.PoolId, rBase.String(), denomA, rQuote.String(), denomB, minBase.String(), denomA, minQuote.String(), denomB)
		}
		if rQuote.Mul(maxBase).GT(rBase.Mul(maxQuote)) {
			return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price above band after swap in pool %d: reserves=[%s%s,%s%s], max_price=%s%s/%s%s", leg.PoolId, rBase.String(), denomA, rQuote.String(), denomB, maxBase.String(), denomA, maxQuote.String(), denomB)
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
				return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap output too small in pool %d: input=%s%s, computed_output=%s, reserves=[%s,%s], fee=%s", leg.PoolId, actualInCoin.Amount.String(), actualInCoin.Denom, outAmt.String(), pool.Coins[inputIdx].String(), pool.Coins[outputIdx].String(), fee.String())
			}
			newIn := pool.Coins[inputIdx].Amount.Add(actualInCoin.Amount)
			newOut := pool.Coins[outputIdx].Amount.Sub(outAmt)
			if !newOut.IsPositive() {
				return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap would deplete output reserve to zero in pool %d: output_reserve=%s, swap_output=%s", leg.PoolId, pool.Coins[outputIdx].String(), outAmt.String())
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
				return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "exact-out equals/exceeds reserve in pool %d: requested_output=%s, output_reserve=%s", leg.PoolId, targetOutAmt.String(), pool.Coins[outputIdx].String())
			}
			effInReq := rIn.Mul(rOut.Quo(rOut.Sub(out)).Sub(one))
			gross := effInReq.Quo(one.Sub(fee)).Ceil().TruncateInt()
			if !gross.IsPositive() {
				return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "computed input not positive in pool %d: requested_output=%s, reserves=[%s,%s], fee=%s", leg.PoolId, targetOutAmt.String(), pool.Coins[inputIdx].String(), pool.Coins[outputIdx].String(), fee.String())
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
					return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out in pool %d: requested=%s, achievable=%s, reserves=[%s,%s]", leg.PoolId, targetOutAmt.String(), outAct.String(), pool.Coins[inputIdx].String(), pool.Coins[outputIdx].String())
				}
			}
			feeInt := gross.Sub(effInActual.TruncateInt())
			if feeInt.IsPositive() {
				pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[inputIdx].Denom, feeInt))
			}
			newIn := pool.Coins[inputIdx].Amount.Add(gross)
			newOut := pool.Coins[outputIdx].Amount.Sub(targetOutAmt)
			if !newOut.IsPositive() {
				return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap would deplete output reserve to zero in pool %d: output_reserve=%s, requested_output=%s", leg.PoolId, pool.Coins[outputIdx].String(), targetOutAmt.String())
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
			return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap_out denom %s doesn't match computed %s", leg.SwapOut.Denom, outDenom)
		}
		if !outAmt.Equal(leg.SwapOut.Amount) {
			return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "computed out %s != required %s", outAmt.String(), leg.SwapOut.Amount.String())
		}
	}

	// Persist pool and emit events
	pool.NumTrades += 1
	if err := k.updatePool(ctx, &pool); err != nil {
		return sdk.Coin{}, sdk.Coin{}, err
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolSwap{PoolId: pool.PoolId}); err != nil {
		return sdk.Coin{}, sdk.Coin{}, err
	}

	tradeId, terr := k.tradeSeq.Next(ctx)
	if terr != nil {
		return sdk.Coin{}, sdk.Coin{}, terr
	}
	t := sdkCtx.BlockTime()
	trade := whaleswapv1.Trade{
		TradeId:   tradeId,
		OfferId:   0,
		Taker:     trader,
		Height:    uint64(sdkCtx.BlockHeight()),
		Timestamp: &t,
		Sent:      actualInCoin,
		Received:  sdk.NewCoin(outDenom, outAmt),
		PoolId:    pool.PoolId,
		AuctionId: 0,
		Note:      note,
	}
	if err := k.TradesMap.Set(ctx, tradeId, trade); err != nil {
		return sdk.Coin{}, sdk.Coin{}, err
	}
	if err := k.TradesByPoolIndex.Set(ctx, collections.Join(pool.PoolId, tradeId), tradeId); err != nil {
		return sdk.Coin{}, sdk.Coin{}, err
	}
	if err := k.TradesByTakerIndex.Set(ctx, collections.Join(trader, tradeId), tradeId); err != nil {
		return sdk.Coin{}, sdk.Coin{}, err
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventTradeRecorded{TradeId: tradeId, OfferId: 0, PoolId: pool.PoolId, AuctionId: 0, Note: note}); err != nil {
		return sdk.Coin{}, sdk.Coin{}, err
	}

	return actualInCoin, sdk.NewCoin(outDenom, outAmt), nil
}

// tradeApplyTakeItem executes one TakeItem: updates the offer, records the trade,
// and returns aggregator contributions: maker (for outputs), maker want coin, taker receive coin,
// makerLiquidIn to inputs (for burn), and pfandReleased to add to taker outputs when closing.
func (k Keeper) tradeApplyTakeItem(ctx context.Context, taker string, item *whaleswapv1.TakeItem, note string) (string, sdk.Coin, sdk.Coin, sdk.Coin, sdk.Coin, error) {
	if item == nil || item.OfferId == 0 {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "offer_id required")
	}
	offer, err := k.OffersMap.Get(ctx, item.OfferId)
	if err != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "offer not found: %d", item.OfferId)
	}
	if offer.Status != whaleswapv1.OfferStatusOpen {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "offer %d not open", item.OfferId)
	}
	remainingUnits, ok := math.NewIntFromString(offer.RemainingUnits)
	if !ok || !remainingUnits.IsPositive() {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid remaining units")
	}
	takeUnits, perr := k.parseTakeUnits(remainingUnits, item.TakeUnits)
	if perr != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, perr
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

	// Persist trade and offer
	tradeId, terr := k.tradeSeq.Next(ctx)
	if terr != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, terr
	}
	recDenom := haveDenom
	if k.isLiquidDenom(haveDenom) {
		if baseHave, derr := k.decodeLiquidDenom(haveDenom); derr == nil {
			recDenom = baseHave
		}
	}
	trade := whaleswapv1.Trade{
		TradeId:   tradeId,
		OfferId:   offer.OfferId,
		Taker:     taker,
		Height:    uint64(sdkCtx.BlockHeight()),
		Timestamp: &t,
		Sent:      sdk.NewCoin(wantDenom, requiredWant),
		Received:  sdk.NewCoin(recDenom, deliverHave),
		PoolId:    0,
		AuctionId: 0,
		Note:      note,
	}
	if err := k.TradesMap.Set(ctx, tradeId, trade); err != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, err
	}
	if err := k.TradesByTakerIndex.Set(ctx, collections.Join(taker, tradeId), tradeId); err != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, err
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventTradeRecorded{TradeId: tradeId, OfferId: offer.OfferId, PoolId: 0, AuctionId: 0, Note: note}); err != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, err
	}
	prev, _ := k.OffersMap.Get(ctx, offer.OfferId)
	if err := k.OffersMap.Set(ctx, offer.OfferId, offer); err != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrapf(err, "failed to update offer %d", offer.OfferId)
	}
	if err := k.reindexOfferOnStatusChange(ctx, prev, offer); err != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, err
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventOfferTaken{OfferId: offer.OfferId, TradeId: tradeId}); err != nil {
		return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, err
	}
	// Parity with standalone TakeOffer: emit EventPfandReleased on close
	if pfandReleased.IsValid() && pfandReleased.Amount.IsPositive() {
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPfandReleased{Amount: pfandReleased}); err != nil {
			return "", sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, sdk.Coin{}, err
		}
	}

	// Aggregator contributions
	makerWant := sdk.NewCoin(wantDenom, requiredWant)
	var takerRecv sdk.Coin
	var makerLiqIn sdk.Coin
	if k.isLiquidDenom(haveDenom) {
		baseHave, _ := k.decodeLiquidDenom(haveDenom)
		takerRecv = sdk.NewCoin(baseHave, deliverHave)
		makerLiqIn = sdk.NewCoin(haveDenom, deliverHave)
	} else {
		takerRecv = sdk.NewCoin(haveDenom, deliverHave)
	}
	return maker, makerWant, takerRecv, makerLiqIn, pfandReleased, nil
}

// tradeNetAndCover performs orderbook-style netting and coverage on the aggregator maps.
func (k Keeper) tradeNetAndCover(ctx context.Context, traderBech string, inputsByAddr, outputsByAddr map[string]sdk.Coins) error {
	moduleBech := k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String()
	// maker wants (solid)
	makerWants := sdk.NewCoins()
	for addr, coins := range outputsByAddr {
		if addr == traderBech || addr == moduleBech {
			continue
		}
		for _, c := range coins {
			if k.isLiquidDenom(c.Denom) {
				continue
			}
			makerWants = makerWants.Add(c)
		}
	}
	// taker credits (solid)
	takerCredits := sdk.NewCoins()
	if tcoins, ok := outputsByAddr[traderBech]; ok {
		for _, c := range tcoins {
			if k.isLiquidDenom(c.Denom) {
				continue
			}
			takerCredits = takerCredits.Add(c)
		}
	}
	// First pass: compute nettable per denom and reduce trader credits accordingly
	for _, want := range makerWants {
		denom := want.Denom
		wantAmt := want.Amount
		credit := takerCredits.AmountOf(denom)
		nettable := credit
		if wantAmt.LT(credit) {
			nettable = wantAmt
		}
		if nettable.IsPositive() {
			if coins, ok := outputsByAddr[traderBech]; ok {
				outputsByAddr[traderBech] = coins.Sub(sdk.NewCoin(denom, nettable))
				if outputsByAddr[traderBech].IsZero() {
					delete(outputsByAddr, traderBech)
				}
			}
			// Also reduce module inputs for this denom by the same nettable amount (caps to available),
			// because those trader credits were funded by module (AMM or escrow) and have been netted away.
			if mcoins, ok := inputsByAddr[moduleBech]; ok {
				mAmt := mcoins.AmountOf(denom)
				use := nettable
				if mAmt.LT(use) {
					use = mAmt
				}
				if use.IsPositive() {
					inputsByAddr[moduleBech] = inputsByAddr[moduleBech].Sub(sdk.NewCoin(denom, use))
					if inputsByAddr[moduleBech].IsZero() {
						delete(inputsByAddr, moduleBech)
					}
				}
			}
			// Also reduce makers' wants by the same nettable amount across all makers
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
		if credit.GTE(wantAmt) {
			continue
		}
		deficit := wantAmt.Sub(credit)
		// Cover with taker base then taker liquid
		takerAddr, _ := sdk.AccAddressFromBech32(traderBech)
		baseBal := k.bank.GetBalance(ctx, takerAddr, denom).Amount
		basePart := baseBal
		if basePart.GT(deficit) {
			basePart = deficit
		}
		if basePart.IsPositive() {
			inputsByAddr[traderBech] = inputsByAddr[traderBech].Add(sdk.NewCoin(denom, basePart))
		}
		rem := deficit.Sub(basePart)
		if rem.IsPositive() {
			ldenom := whaleswapv1.LiquidDenom(denom)
			liqBal := k.bank.GetBalance(ctx, takerAddr, ldenom).Amount
			if liqBal.LT(rem) {
				return cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "taker insufficient %s: %s < %s", ldenom, liqBal.String(), rem.String())
			}
			inputsByAddr[traderBech] = inputsByAddr[traderBech].Add(sdk.NewCoin(ldenom, rem))
		}
	}
	// Module covers remaining solid deficits
	outputsSolid := sdk.NewCoins()
	for _, coins := range outputsByAddr {
		for _, c := range coins {
			if k.isLiquidDenom(c.Denom) {
				continue
			}
			outputsSolid = outputsSolid.Add(c)
		}
	}
	inputsSolid := sdk.NewCoins()
	for _, coins := range inputsByAddr {
		for _, c := range coins {
			if k.isLiquidDenom(c.Denom) {
				continue
			}
			inputsSolid = inputsSolid.Add(c)
		}
	}
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	for _, out := range outputsSolid {
		den := out.Denom
		need := out.Amount.Sub(inputsSolid.AmountOf(den))
		if need.IsPositive() {
			bal := k.bank.GetBalance(ctx, moduleAddr, den).Amount
			if bal.LT(need) {
				return cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "module backing insufficient %s: %s < %s", den, bal.String(), need.String())
			}
			inputsByAddr[moduleBech] = inputsByAddr[moduleBech].Add(sdk.NewCoin(den, need))
		}
	}
	// Liquid inputs to module must also be outputs for burn
	liquidToModule := sdk.NewCoins()
	for _, coins := range inputsByAddr {
		for _, c := range coins {
			if k.isLiquidDenom(c.Denom) && c.Amount.IsPositive() {
				liquidToModule = liquidToModule.Add(c)
			}
		}
	}
	if !liquidToModule.IsZero() {
		outputsByAddr[moduleBech] = outputsByAddr[moduleBech].Add(liquidToModule...)
	}
	return nil
}

// tradeBurnModuleLiquid burns any liquid coins sent to the module during settlement.
func (k Keeper) tradeBurnModuleLiquid(ctx context.Context, outputsByAddr map[string]sdk.Coins) error {
	moduleBech := k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String()
	if mcoins, ok := outputsByAddr[moduleBech]; ok {
		for _, c := range mcoins {
			if k.isLiquidDenom(c.Denom) && c.Amount.IsPositive() {
				if err := k.burnLiquid(ctx, c); err != nil {
					return cosmossdkerrors.Wrap(err, "burn liquid failed")
				}
			}
		}
	}
	return nil
}
