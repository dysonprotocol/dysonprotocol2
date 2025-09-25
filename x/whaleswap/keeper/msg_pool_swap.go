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
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
)

func (k Keeper) PoolSwap(ctx context.Context, msg *whaleswapv1.MsgPoolSwap) (*whaleswapv1.MsgPoolSwapResponse, error) {
	accCodec := k.accKeeper.AddressCodec()
	traderBz, err := accCodec.StringToBytes(msg.Trader)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid trader: %s", err.Error())
	}
	_ = sdk.AccAddress(traderBz)

	if len(msg.Legs) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "legs must be non-empty")
	}

	// Build end-of-tx debit caps per denom (vector cap)
	caps := sdk.NewCoins(msg.MaxInput...)

	// module delta per denom: amount>0 means module receives; amount<0 means module pays
	deltaByDenom := map[string]math.Int{}

	// Simulate each leg against pool snapshots, update pools and record trades
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	t := sdkCtx.BlockTime()
	for _, leg := range msg.Legs {
		if leg.PoolId == 0 {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id required")
		}
		// At least one of swap_in or swap_out must be provided
		if (leg.SwapIn.Denom == "" || !leg.SwapIn.Amount.IsPositive()) && (leg.SwapOut.Denom == "" || !leg.SwapOut.Amount.IsPositive()) {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "each leg must specify swap_in or swap_out with positive amount")
		}
		pool, gerr := k.PoolsMap.Get(ctx, leg.PoolId)
		if gerr != nil {
			return nil, cosmossdkerrors.Wrapf(gerr, "pool not found: %d", leg.PoolId)
		}
		if len(pool.Coins) != 2 {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
		}
		// Parse fee once per leg from current pool state
		fee := math.LegacyNewDec(0)
		if pool.FeePct != "" {
			f, ferr := math.LegacyNewDecFromStr(pool.FeePct)
			if ferr != nil {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool fee_pct: "+ferr.Error())
			}
			fee = f
		}
		one := math.LegacyNewDec(1)

		// Determine orientation and target(s)
		hasIn := leg.SwapIn.Denom != "" && leg.SwapIn.Amount.IsPositive()
		hasOut := leg.SwapOut.Denom != "" && leg.SwapOut.Amount.IsPositive()
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
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "input denom %s not in pool %d", leg.SwapIn.Denom, leg.PoolId)
			}
			outputIdx = 1 - inputIdx
			actualInCoin = leg.SwapIn
		} else {
			// exact-out only: deduce input denom as the other reserve
			if leg.SwapOut.Denom == pool.Coins[0].Denom {
				outputIdx = 0
			} else if leg.SwapOut.Denom == pool.Coins[1].Denom {
				outputIdx = 1
			} else {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "output denom %s not in pool %d", leg.SwapOut.Denom, leg.PoolId)
			}
			inputIdx = 1 - outputIdx
			targetOutAmt = leg.SwapOut.Amount
		}

		if len(pool.MinPrice) == 2 {
			// concentrated liquidity path
			sa, sb, err := k.bandSqrt(pool)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to compute band sqrt prices")
			}
			sp, err := k.poolSqrtPrice(pool, pool.Coins[0].Denom, pool.Coins[1].Denom)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to compute current sqrt price")
			}
			Lcur, _, _, err := k.liquidityForReserves(pool)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "invalid pool liquidity")
			}
			if !Lcur.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool liquidity")
			}
			L := Lcur
			if hasIn {
				// exact-in as before
				effIn := math.LegacyNewDecFromInt(actualInCoin.Amount).Mul(one.Sub(fee))
				feeInt := actualInCoin.Amount.Sub(effIn.TruncateInt())
				if feeInt.IsPositive() {
					fees := sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(actualInCoin.Denom, feeInt))
					pool.FeesEarned = fees
				}
				if inputIdx == 0 {
					invSpPrime := math.LegacyOneDec().Quo(sp).Add(effIn.Quo(L))
					if invSpPrime.LTE(math.LegacyZeroDec()) {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity")
					}
					spPrime, err := k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
					if err != nil {
						return nil, cosmossdkerrors.Wrap(err, "failed to compute next sqrt price")
					}
					if spPrime.LT(sa) {
						spPrime = sa
					}
					outDec := L.Mul(sp.Sub(spPrime))
					outAmt = outDec.TruncateInt()
				} else {
					spPrime := sp.Add(effIn.Quo(L))
					if spPrime.GT(sb) {
						spPrime = sb
					}
					outDec := L.Mul(math.LegacyOneDec().Quo(sp).Sub(math.LegacyOneDec().Quo(spPrime)))
					outAmt = outDec.TruncateInt()
				}
			} else {
				// exact-out: compute minimal input to achieve targetOutAmt
				if !targetOutAmt.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_out must be > 0")
				}
				if outputIdx == 1 { // out denom is coin[1] => token0-in
					outDec := math.LegacyNewDecFromInt(targetOutAmt)
					spPrime := sp.Sub(outDec.Quo(L))
					if spPrime.LT(sa) {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds band capacity")
					}
					effInDec := L.Mul(math.LegacyOneDec().Quo(spPrime).Sub(math.LegacyOneDec().Quo(sp)))
					// gross input candidate
					gross := effInDec.Quo(one.Sub(fee)).Ceil().TruncateInt()
					if !gross.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
					}
					effInActual := math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
					invSpPrime := math.LegacyOneDec().Quo(sp).Add(effInActual.Quo(L))
					spPrimeAct, err := k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
					if err != nil {
						return nil, cosmossdkerrors.Wrap(err, "failed to compute next sqrt price")
					}
					outAct := L.Mul(sp.Sub(spPrimeAct)).TruncateInt()
					if outAct.LT(targetOutAmt) {
						gross = gross.AddRaw(1)
						effInActual = math.LegacyNewDecFromInt(gross).Mul(one.Sub(fee))
						invSpPrime = math.LegacyOneDec().Quo(sp).Add(effInActual.Quo(L))
						spPrimeAct, err = k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
						if err != nil {
							return nil, cosmossdkerrors.Wrap(err, "failed to compute next sqrt price (recheck)")
						}
						outAct = L.Mul(sp.Sub(spPrimeAct)).TruncateInt()
						if outAct.LT(targetOutAmt) {
							return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out")
						}
					}
					// Apply fees and reserves
					feeInt := gross.Sub(effInActual.TruncateInt())
					if feeInt.IsPositive() {
						fees := sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[0].Denom, feeInt))
						pool.FeesEarned = fees
					}
					// Update reserves: token0-in
					new0 := pool.Coins[0].Amount.Add(gross)
					new1 := pool.Coins[1].Amount.Sub(targetOutAmt)
					if !new1.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete quote reserve to zero")
					}
					pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
					outAmt = targetOutAmt
					outDenom = pool.Coins[1].Denom
					actualInCoin = sdk.NewCoin(pool.Coins[0].Denom, gross)
				} else { // outputIdx == 0 => token1-in
					outDec := math.LegacyNewDecFromInt(targetOutAmt)
					denom := math.LegacyOneDec().Quo(sp).Sub(outDec.Quo(L))
					if !denom.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds pool capacity")
					}
					spPrime := math.LegacyOneDec().Quo(denom)
					if spPrime.GT(sb) {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds band capacity")
					}
					effInDec := L.Mul(spPrime.Sub(sp))
					gross := effInDec.Quo(one.Sub(fee)).Ceil().TruncateInt()
					if !gross.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
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
							return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out")
						}
					}
					feeInt := gross.Sub(effInActual.TruncateInt())
					if feeInt.IsPositive() {
						fees := sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[1].Denom, feeInt))
						pool.FeesEarned = fees
					}
					// Update reserves: token1-in
					new0 := pool.Coins[0].Amount.Sub(targetOutAmt)
					new1 := pool.Coins[1].Amount.Add(gross)
					if !new0.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete base reserve to zero")
					}
					pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
					outAmt = targetOutAmt
					outDenom = pool.Coins[0].Denom
					actualInCoin = sdk.NewCoin(pool.Coins[1].Denom, gross)
				}
			}
			// When exact-in path, set outDenom and reserves update
			if hasIn {
				if inputIdx == 0 {
					new0 := pool.Coins[0].Amount.Add(actualInCoin.Amount)
					new1 := pool.Coins[1].Amount.Sub(outAmt)
					if !new1.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete quote reserve to zero")
					}
					pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
					outDenom = pool.Coins[1].Denom
				} else {
					new0 := pool.Coins[0].Amount.Sub(outAmt)
					new1 := pool.Coins[1].Amount.Add(actualInCoin.Amount)
					if !new0.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete base reserve to zero")
					}
					pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
					outDenom = pool.Coins[0].Denom
				}
			}
			// Band check post swap
			rBase := pool.Coins[0].Amount
			rQuote := pool.Coins[1].Amount
			denomA, denomB := pool.Coins[0].Denom, pool.Coins[1].Denom
			minBase := pool.MinPrice.AmountOf(denomA)
			minQuote := pool.MinPrice.AmountOf(denomB)
			maxBase := pool.MaxPrice.AmountOf(denomA)
			maxQuote := pool.MaxPrice.AmountOf(denomB)
			if rQuote.Mul(minBase).LT(rBase.Mul(minQuote)) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price below band after swap")
			}
			if rQuote.Mul(maxBase).GT(rBase.Mul(maxQuote)) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price above band after swap")
			}
		} else {
			// constant product path
			rIn := math.LegacyNewDecFromInt(pool.Coins[inputIdx].Amount)
			rOut := math.LegacyNewDecFromInt(pool.Coins[outputIdx].Amount)
			if hasIn {
				effIn := math.LegacyNewDecFromInt(actualInCoin.Amount).Mul(one.Sub(fee))
				feeInt := actualInCoin.Amount.Sub(effIn.TruncateInt())
				if feeInt.IsPositive() {
					fees := sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(actualInCoin.Denom, feeInt))
					pool.FeesEarned = fees
				}
				kDec := rIn.Mul(rOut)
				q := kDec.Quo(rIn.Add(effIn)).Ceil()
				outDec := rOut.Sub(q)
				outAmt = outDec.TruncateInt()
				if !outAmt.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap output too small")
				}
				newIn := pool.Coins[inputIdx].Amount.Add(actualInCoin.Amount)
				newOut := pool.Coins[outputIdx].Amount.Sub(outAmt)
				if !newOut.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete output reserve to zero")
				}
				if inputIdx == 0 {
					pool.Coins = sdk.NewCoins(
						sdk.NewCoin(pool.Coins[0].Denom, newIn),
						sdk.NewCoin(pool.Coins[1].Denom, newOut),
					)
					outDenom = pool.Coins[1].Denom
				} else {
					pool.Coins = sdk.NewCoins(
						sdk.NewCoin(pool.Coins[0].Denom, newOut),
						sdk.NewCoin(pool.Coins[1].Denom, newIn),
					)
					outDenom = pool.Coins[0].Denom
				}
			} else { // exact-out
				if !targetOutAmt.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_out must be > 0")
				}
				out := math.LegacyNewDecFromInt(targetOutAmt)
				if out.GTE(rOut) {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out equals/exceeds reserve")
				}
				// effInRequired = rIn*(rOut/(rOut-out) - 1)
				effInReq := rIn.Mul(rOut.Quo(rOut.Sub(out)).Sub(one))
				gross := effInReq.Quo(one.Sub(fee)).Ceil().TruncateInt()
				if !gross.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
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
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity for exact-out")
					}
				}
				feeInt := gross.Sub(effInActual.TruncateInt())
				if feeInt.IsPositive() {
					fees := sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[inputIdx].Denom, feeInt))
					pool.FeesEarned = fees
				}
				newIn := pool.Coins[inputIdx].Amount.Add(gross)
				newOut := pool.Coins[outputIdx].Amount.Sub(targetOutAmt)
				if !newOut.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete output reserve to zero")
				}
				if inputIdx == 0 {
					pool.Coins = sdk.NewCoins(
						sdk.NewCoin(pool.Coins[0].Denom, newIn),
						sdk.NewCoin(pool.Coins[1].Denom, newOut),
					)
					outDenom = pool.Coins[1].Denom
				} else {
					pool.Coins = sdk.NewCoins(
						sdk.NewCoin(pool.Coins[0].Denom, newOut),
						sdk.NewCoin(pool.Coins[1].Denom, newIn),
					)
					outDenom = pool.Coins[0].Denom
				}
				outAmt = targetOutAmt
				actualInCoin = sdk.NewCoin(pool.Coins[inputIdx].Denom, gross)
			}
		}

		// Persist pool changes and emit per-leg events
		pool.NumTrades += 1
		if err := k.updatePool(ctx, &pool); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to update pool %d after swap", pool.PoolId)
		}
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolSwap{PoolId: pool.PoolId}); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPoolSwap")
		}

		// Accumulate module delta and record trade (safe map accumulation)
		if v, ok := deltaByDenom[actualInCoin.Denom]; ok {
			deltaByDenom[actualInCoin.Denom] = v.Add(actualInCoin.Amount)
		} else {
			deltaByDenom[actualInCoin.Denom] = actualInCoin.Amount
		}
		if v, ok := deltaByDenom[outDenom]; ok {
			deltaByDenom[outDenom] = v.Sub(outAmt)
		} else {
			deltaByDenom[outDenom] = outAmt.Neg()
		}

		tradeId, terr := k.tradeSeq.Next(ctx)
		if terr != nil {
			return nil, cosmossdkerrors.Wrap(terr, "failed to allocate trade id")
		}
		trade := whaleswapv1.Trade{
			TradeId:   tradeId,
			OfferId:   0,
			Taker:     msg.Trader,
			Height:    uint64(sdkCtx.BlockHeight()),
			Timestamp: &t,
			Sent:      actualInCoin,
			Received:  sdk.NewCoin(outDenom, outAmt),
			PoolId:    pool.PoolId,
			AuctionId: 0,
		}
		if err := k.TradesMap.Set(ctx, tradeId, trade); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to save trade")
			// If both swap_in and swap_out provided, enforce rate constraint
			if hasIn && hasOut {
				if leg.SwapOut.Denom != outDenom {
					return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap_out denom %s doesn't match computed %s", leg.SwapOut.Denom, outDenom)
				}
				if outAmt.LT(leg.SwapOut.Amount) {
					return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "computed out %s < required %s", outAmt.String(), leg.SwapOut.Amount.String())
				}
			}
		}
		if err := k.TradesByPoolIndex.Set(ctx, collections.Join(pool.PoolId, tradeId), tradeId); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to index trade by pool")
		}
		if err := k.TradesByTakerIndex.Set(ctx, collections.Join(msg.Trader, tradeId), tradeId); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to index trade by taker")
		}
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventTradeRecorded{TradeId: tradeId, OfferId: 0, PoolId: pool.PoolId, AuctionId: 0}); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventTradeRecorded")
		}
	}

	// Derive debits (trader -> module) and credits (module -> trader) from module deltas
	requiredDebits := sdk.NewCoins()
	credits := sdk.NewCoins()
	for denom, modAmt := range deltaByDenom {
		if modAmt.IsZero() {
			continue
		}
		if modAmt.IsPositive() {
			// module receives => trader must pay this denom
			need := modAmt
			capAmt := caps.AmountOf(denom)
			if capAmt.IsZero() || capAmt.LT(need) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "debit exceeds cap for %s: need %s <= cap %s", denom, need.String(), capAmt.String())
			}
			requiredDebits = requiredDebits.Add(sdk.NewCoin(denom, need))
			continue
		}
		if modAmt.IsNegative() {
			// module pays => trader receives this denom
			credits = credits.Add(sdk.NewCoin(denom, modAmt.Abs()))
		}
	}
	// Enforce min_output
	for _, m := range msg.MinOutput {
		got := credits.AmountOf(m.Denom)
		if got.LT(m.Amount) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_output not met for %s: got %s < %s", m.Denom, got.String(), m.Amount.String())
		}
	}

	// Single aggregated move: trader <-> module
	inputs := []banktypes.Input{}
	outputs := []banktypes.Output{}
	traderBech := msg.Trader
	moduleBech := k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String()
	if !requiredDebits.IsZero() {
		inputs = append(inputs, banktypes.Input{Address: traderBech, Coins: requiredDebits})
		outputs = append(outputs, banktypes.Output{Address: moduleBech, Coins: requiredDebits})
	}
	if !credits.IsZero() {
		inputs = append(inputs, banktypes.Input{Address: moduleBech, Coins: credits})
		outputs = append(outputs, banktypes.Output{Address: traderBech, Coins: credits})
	}
	if len(inputs) == 0 || len(outputs) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "no inputs or outputs for pool swap move")
	}
	if err := k.wsMoveCoins(ctx, inputs, outputs); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "move coins failed")
	}

	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AMM invariant after aggregated PoolSwap")
	}

	return &whaleswapv1.MsgPoolSwapResponse{AmountOut: credits}, nil
}
