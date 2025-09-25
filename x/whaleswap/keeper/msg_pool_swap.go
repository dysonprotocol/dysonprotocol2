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

	// Build end-of-tx debit caps per denom
	caps := sdk.NewCoins(msg.Input...)

	// module delta per denom: amount>0 means module receives; amount<0 means module pays
	deltaByDenom := map[string]math.Int{}

	// Simulate each leg against pool snapshots, update pools and record trades
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	t := sdkCtx.BlockTime()
	for _, leg := range msg.Legs {
		if leg.PoolId == 0 {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id required")
		}
		inCoin := leg.SwapIn
		if inCoin.Denom == "" || !inCoin.Amount.IsPositive() {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_in must be > 0 with denom")
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

		// Validate input denom is in pool and compute out denom index
		inputIdx := -1
		if inCoin.Denom == pool.Coins[0].Denom {
			inputIdx = 0
		} else if inCoin.Denom == pool.Coins[1].Denom {
			inputIdx = 1
		} else {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "input denom %s not in pool %d", inCoin.Denom, leg.PoolId)
		}
		outputIdx := 1 - inputIdx

		var outAmt math.Int
		var outDenom string

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
			effIn := math.LegacyNewDecFromInt(inCoin.Amount).Mul(one.Sub(fee))
			feeInt := inCoin.Amount.Sub(effIn.TruncateInt())
			if feeInt.IsPositive() {
				fees := sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(inCoin.Denom, feeInt))
				pool.FeesEarned = fees
			}
			L := Lcur
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
			if !outAmt.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap output too small")
			}
			if inputIdx == 0 {
				new0 := pool.Coins[0].Amount.Add(inCoin.Amount)
				new1 := pool.Coins[1].Amount.Sub(outAmt)
				if !new1.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete quote reserve to zero")
				}
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
				outDenom = pool.Coins[1].Denom
			} else {
				new0 := pool.Coins[0].Amount.Sub(outAmt)
				new1 := pool.Coins[1].Amount.Add(inCoin.Amount)
				if !new0.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete base reserve to zero")
				}
				pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
				outDenom = pool.Coins[0].Denom
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
			effIn := math.LegacyNewDecFromInt(inCoin.Amount).Mul(one.Sub(fee))
			feeInt := inCoin.Amount.Sub(effIn.TruncateInt())
			if feeInt.IsPositive() {
				fees := sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(inCoin.Denom, feeInt))
				pool.FeesEarned = fees
			}
			kDec := rIn.Mul(rOut)
			q := kDec.Quo(rIn.Add(effIn)).Ceil()
			outDec := rOut.Sub(q)
			outAmt = outDec.TruncateInt()
			if !outAmt.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap output too small")
			}
			newIn := pool.Coins[inputIdx].Amount.Add(inCoin.Amount)
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
		if v, ok := deltaByDenom[inCoin.Denom]; ok {
			deltaByDenom[inCoin.Denom] = v.Add(inCoin.Amount)
		} else {
			deltaByDenom[inCoin.Denom] = inCoin.Amount
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
			Sent:      inCoin,
			Received:  sdk.NewCoin(outDenom, outAmt),
			PoolId:    pool.PoolId,
			AuctionId: 0,
		}
		if err := k.TradesMap.Set(ctx, tradeId, trade); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to save trade")
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
