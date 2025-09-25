package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
)

// MakeTrade mixes SwapLegs and TakeItems with single end-of-tx settlement.
func (k Keeper) MakeTrade(ctx context.Context, msg *whaleswapv1.MsgMakeTrade) (*whaleswapv1.MsgMakeTradeResponse, error) {
	if len(msg.Operations) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "operations must be non-empty")
	}

	accCodec := k.accKeeper.AddressCodec()
	_, err := accCodec.StringToBytes(msg.Trader)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid trader: %s", err.Error())
	}

	// Caps per denom (vector)
	caps := sdk.NewCoins(msg.MaxInput...)

	// Aggregators
	deltaByDenom := map[string]math.Int{} // AMM module deltas only
	inputsByAddr := map[string]sdk.Coins{}
	outputsByAddr := map[string]sdk.Coins{}

	addIn := func(addr string, c sdk.Coin) {
		if !c.Amount.IsPositive() {
			return
		}
		inputsByAddr[addr] = inputsByAddr[addr].Add(c)
	}
	addOut := func(addr string, c sdk.Coin) {
		if !c.Amount.IsPositive() {
			return
		}
		outputsByAddr[addr] = outputsByAddr[addr].Add(c)
	}

	_ = sdk.UnwrapSDKContext(ctx)

	// Execute operations in order, mutating pools/offers and accumulating
	for _, op := range msg.Operations {
		switch v := op.Op.(type) {
		case *whaleswapv1.TradeOperation_Swap:
			leg := v.Swap
			if leg == nil || leg.PoolId == 0 {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap leg invalid")
			}
			inCoin, outCoin, derr := k.tradeApplySwapLeg(ctx, msg.Trader, leg)
			if derr != nil {
				return nil, derr
			}
			if v, ok := deltaByDenom[inCoin.Denom]; ok {
				deltaByDenom[inCoin.Denom] = v.Add(inCoin.Amount)
			} else {
				deltaByDenom[inCoin.Denom] = inCoin.Amount
			}
			if v, ok := deltaByDenom[outCoin.Denom]; ok {
				deltaByDenom[outCoin.Denom] = v.Sub(outCoin.Amount)
			} else {
				deltaByDenom[outCoin.Denom] = outCoin.Amount.Neg()
			}

		case *whaleswapv1.TradeOperation_Take:
			item := v.Take
			if item == nil {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "take item missing")
			}
			maker, makerWant, takerRecv, makerLiqIn, pfand, terr := k.tradeApplyTakeItem(ctx, msg.Trader, item)
			if terr != nil {
				return nil, terr
			}
			addOut(maker, makerWant)
			addOut(msg.Trader, takerRecv)
			if makerLiqIn.IsValid() && makerLiqIn.Amount.IsPositive() {
				addIn(maker, makerLiqIn)
			}
			if pfand.IsValid() && pfand.Amount.IsPositive() {
				addOut(msg.Trader, pfand)
			}

		default:
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "operation must be swap or take")
		}
	}

	moduleBech := k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String()
	traderBech := msg.Trader

	// Convert AMM module deltas to inputs/outputs entries (trader <-> module)
	for denom, modAmt := range deltaByDenom {
		if modAmt.IsZero() {
			continue
		}
		if modAmt.IsPositive() {
			addIn(traderBech, sdk.NewCoin(denom, modAmt))
			addOut(moduleBech, sdk.NewCoin(denom, modAmt))
		} else {
			addIn(moduleBech, sdk.NewCoin(denom, modAmt.Abs()))
			addOut(traderBech, sdk.NewCoin(denom, modAmt.Abs()))
		}
	}

	// Orderbook-style netting and coverage
	if err := k.tradeNetAndCover(ctx, traderBech, inputsByAddr, outputsByAddr); err != nil {
		return nil, err
	}

	// Enforce caps: sum inputsByAddr[trader] per denom ≤ caps
	traderInputs := inputsByAddr[traderBech]
	for _, c := range traderInputs {
		capAmt := caps.AmountOf(c.Denom)
		if capAmt.IsZero() || capAmt.LT(c.Amount) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "debit exceeds cap for %s: need %s <= cap %s", c.Denom, c.Amount.String(), capAmt.String())
		}
	}

	// Enforce min_output on trader credits
	traderOutputs := outputsByAddr[traderBech]
	for _, m := range msg.MinOutput {
		got := traderOutputs.AmountOf(m.Denom)
		if got.LT(m.Amount) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_output not met for %s: got %s < %s", m.Denom, got.String(), m.Amount.String())
		}
	}

	// Build multisend IO and execute once
	var inputs []banktypes.Input
	var outputs []banktypes.Output
	for addr, coins := range inputsByAddr {
		if !coins.IsZero() {
			inputs = append(inputs, banktypes.Input{Address: addr, Coins: coins})
		}
	}
	for addr, coins := range outputsByAddr {
		if !coins.IsZero() {
			outputs = append(outputs, banktypes.Output{Address: addr, Coins: coins})
		}
	}
	if len(inputs) == 0 || len(outputs) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "no inputs or outputs for make-trade move")
	}
	if err := k.wsMoveCoins(ctx, inputs, outputs); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "move coins failed")
	}
	if err := k.tradeBurnModuleLiquid(ctx, outputsByAddr); err != nil {
		return nil, err
	}

	// AMM invariants reuse
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AMM invariant after MakeTrade")
	}

	return &whaleswapv1.MsgMakeTradeResponse{AmountOut: traderOutputs}, nil
}

// executeSwapLegAndPersist mirrors one-leg logic from PoolSwap, updating pool and recording trade.
func (k Keeper) executeSwapLegAndPersist(ctx context.Context, trader string, leg *whaleswapv1.SwapLeg) (in sdk.Coin, out sdk.Coin, err error) {
	// Compose a synthetic one-leg message and call the internal logic by adapting msg_pool_swap.go code
	// For brevity, we call the existing PoolSwap with a single leg and no caps/min, then compute delta from response
	// but to avoid a second settlement, we inline minimal logic would be ideal. Here we do a minimal safe approach:
	// Inline: fetch pool and follow the same math as msg_pool_swap.go for a single leg.
	// To keep this edit small, we reuse the existing helper by forking the core; for now, return an error to avoid duplication.
	return sdk.Coin{}, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "executeSwapLegAndPersist not yet wired")
}

// executeTakeItemAndAggregate applies one orderbook take into aggregators, updating offers and recording trade.
func (k Keeper) executeTakeItemAndAggregate(ctx context.Context, taker string, item *whaleswapv1.TakeItem, addIn func(string, sdk.Coin), addOut func(string, sdk.Coin)) error {
	return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "executeTakeItemAndAggregate not yet wired")
}
