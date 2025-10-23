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
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)

	logger.Info("MakeTrade starting", "trader", msg.Trader, "operations_count", len(msg.Operations), "max_input", msg.MaxInput, "min_output", msg.MinOutput)

	if len(msg.Operations) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "operations must be non-empty")
	}

	accCodec := k.accKeeper.AddressCodec()
	_, err := accCodec.StringToBytes(msg.Trader)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid trader: %s", err.Error())
	}

	params := k.GetParams(sdkCtx)
	if len(msg.Note) > int(params.MaxNoteLength) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "note too long: %d > %d", len(msg.Note), params.MaxNoteLength)
	}

	// Caps per denom (vector). If unspecified, treat as zero (no debits allowed).
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

	// Execute operations in order, mutating pools/offers and accumulating
	logger.Info("MakeTrade processing operations", "operations_count", len(msg.Operations))
	var operations []whaleswapv1.TradeOperation
	type pfandRelease struct {
		offerId uint64
		amount  sdk.Coin
	}
	var pfandReleases []pfandRelease
	seenPools := make(map[uint64]bool)
	seenOffers := make(map[uint64]bool)
	seenAuctions := make(map[uint64]bool)

	for i, op := range msg.Operations {
		switch v := op.Op.(type) {
		case *whaleswapv1.TradeOperation_Swap:
			leg := v.Swap
			logger.Info("MakeTrade processing swap operation", "operation_idx", i, "pool_id", leg.PoolId, "swap_in", leg.SwapIn, "swap_out", leg.SwapOut)
			if leg == nil || leg.PoolId == 0 {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap leg invalid")
			}
			if seenPools[leg.PoolId] {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "duplicate pool_id %d in operations", leg.PoolId)
			}
			seenPools[leg.PoolId] = true
			tradeOp, inCoin, outCoin, derr := k.tradeApplySwapLeg(ctx, msg.Trader, leg, msg.Note)
			if derr != nil {
				return nil, derr
			}
			operations = append(operations, tradeOp)
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
			logger.Info("MakeTrade processing take operation", "operation_idx", i, "offer_id", item.OfferId, "take_units", item.TakeUnits)
			if item == nil {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "take item missing")
			}
			if item.OfferId > 0 && seenOffers[item.OfferId] {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "duplicate offer_id %d in operations", item.OfferId)
			}
			seenOffers[item.OfferId] = true
			tradeOp, maker, makerWant, takerRecv, makerLiqIn, pfand, terr := k.tradeApplyTakeItem(ctx, msg.Trader, item, msg.Note)
			if terr != nil {
				return nil, terr
			}
			logger.Info("MakeTrade take operation applied", "operation_idx", i, "maker", maker, "maker_want", makerWant, "taker_recv", takerRecv, "maker_liq_in", makerLiqIn, "pfand", pfand)
			operations = append(operations, tradeOp)
			// For self-takes (taker == maker), makerWant is a self-payment that nets to zero - don't add to outputs
			if maker != msg.Trader {
				addOut(maker, makerWant)
			}
			// DON'T add taker input explicitly - let tradeNetAndCover determine it via coverage
			addOut(msg.Trader, takerRecv)
			if makerLiqIn.IsValid() && makerLiqIn.Amount.IsPositive() {
				addIn(maker, makerLiqIn)
			}
			if pfand.IsValid() && pfand.Amount.IsPositive() {
				addOut(msg.Trader, pfand)
				pfandReleases = append(pfandReleases, pfandRelease{offerId: item.OfferId, amount: pfand})
			}

		case *whaleswapv1.TradeOperation_Auction:
			auction := v.Auction
			if auction == nil {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "auction item missing")
			}
			if auction.AuctionId > 0 && seenAuctions[auction.AuctionId] {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "duplicate auction_id %d in operations", auction.AuctionId)
			}
			seenAuctions[auction.AuctionId] = true
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "auction operations not yet implemented in MakeTrade")

		default:
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "operation must be swap, take, or auction")
		}
	}

	logger.Info("MakeTrade operations completed", "amm_deltas", deltaByDenom, "pfand_releases", len(pfandReleases))

	moduleBech := k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String()
	traderBech := msg.Trader

	logger.Info("MakeTrade converting AMM deltas to inputs/outputs", "module_addr", moduleBech, "trader_addr", traderBech)
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
	logger.Info("MakeTrade before netting and coverage", "inputs_by_addr", inputsByAddr, "outputs_by_addr", outputsByAddr)
	if err := k.tradeNetAndCover(ctx, traderBech, inputsByAddr, outputsByAddr); err != nil {
		return nil, err
	}
	logger.Info("MakeTrade after netting and coverage", "inputs_by_addr", inputsByAddr, "outputs_by_addr", outputsByAddr)

	// Self-net trader debits and credits by denom to allow circular profit without explicit debits.
	// Keep totals balanced by subtracting the same amount from the module's symmetric entries.
	{
		trIn := inputsByAddr[traderBech]
		trOut := outputsByAddr[traderBech]
		modIn := outputsByAddr[moduleBech] // module receives when trader pays
		modOut := inputsByAddr[moduleBech] // module pays when trader receives
		// Build union of denoms present in trader in/out
		seen := map[string]struct{}{}
		for _, c := range trIn {
			seen[c.Denom] = struct{}{}
		}
		for _, c := range trOut {
			seen[c.Denom] = struct{}{}
		}
		for d := range seen {
			inAmt := trIn.AmountOf(d)
			outAmt := trOut.AmountOf(d)
			var n math.Int
			if inAmt.LT(outAmt) {
				n = inAmt
			} else {
				n = outAmt
			}
			if n.IsPositive() {
				if inputsByAddr[traderBech].AmountOf(d).IsPositive() {
					inputsByAddr[traderBech] = inputsByAddr[traderBech].Sub(sdk.NewCoin(d, n))
					if inputsByAddr[traderBech].IsZero() {
						delete(inputsByAddr, traderBech)
					}
				}
				if outputsByAddr[traderBech].AmountOf(d).IsPositive() {
					outputsByAddr[traderBech] = outputsByAddr[traderBech].Sub(sdk.NewCoin(d, n))
					if outputsByAddr[traderBech].IsZero() {
						delete(outputsByAddr, traderBech)
					}
				}
				if modIn.AmountOf(d).IsPositive() {
					outputsByAddr[moduleBech] = outputsByAddr[moduleBech].Sub(sdk.NewCoin(d, n))
					if outputsByAddr[moduleBech].IsZero() {
						delete(outputsByAddr, moduleBech)
					}
				}
				if modOut.AmountOf(d).IsPositive() {
					inputsByAddr[moduleBech] = inputsByAddr[moduleBech].Sub(sdk.NewCoin(d, n))
					if inputsByAddr[moduleBech].IsZero() {
						delete(inputsByAddr, moduleBech)
					}
				}
			}
		}
	}

	// Enforce caps on NET debits per denom: need = max(0, inputs[trader]-outputs[trader])
	traderInputs := inputsByAddr[traderBech]
	traderOutputs := outputsByAddr[traderBech]
	// Build a quick map of input amounts by denom for iteration
	for _, c := range traderInputs {
		outAmt := traderOutputs.AmountOf(c.Denom)
		need := c.Amount.Sub(outAmt)
		if need.IsPositive() {
			capAmt := caps.AmountOf(c.Denom)
			if capAmt.IsZero() || capAmt.LT(need) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "debit exceeds cap for %s: need %s <= cap %s", c.Denom, need.String(), capAmt.String())
			}
		}
	}

	// Enforce min_output on trader credits
	traderOutputs = outputsByAddr[traderBech]
	for _, m := range msg.MinOutput {
		got := traderOutputs.AmountOf(m.Denom)
		if got.LT(m.Amount) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_output not met for %s: got %s < %s", m.Denom, got.String(), m.Amount.String())
		}
	}

	// Build multisend IO and execute once
	logger.Info("MakeTrade building multisend inputs/outputs", "inputs_by_addr", inputsByAddr, "outputs_by_addr", outputsByAddr)
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
	if len(inputs) == 0 && len(outputs) == 0 {
		// No settlement required after full netting and coverage: still burn any liquid outputs
		// destined for the module.
		logger.Info("MakeTrade no settlement required, burning module liquid")
		if err := k.tradeBurnModuleLiquid(ctx, outputsByAddr); err != nil {
			return nil, err
		}
		traderOutputs = outputsByAddr[traderBech]
		logger.Info("MakeTrade completed without settlement", "trader_outputs", traderOutputs)
		return &whaleswapv1.MsgMakeTradeResponse{AmountOut: traderOutputs}, nil
	}
	// Validate that both inputs and outputs are non-empty before calling wsMoveCoins
	if len(inputs) == 0 || len(outputs) == 0 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid netting result: inputs=%d, outputs=%d", len(inputs), len(outputs))
	}

	// Debug: log the inputs and outputs before calling wsMoveCoins
	logger.Info("MakeTrade wsMoveCoins debug", "inputs_count", len(inputs), "outputs_count", len(outputs))
	for i, in := range inputs {
		logger.Info("MakeTrade input", "idx", i, "addr", in.Address, "coins", in.Coins.String())
	}
	for i, out := range outputs {
		logger.Info("MakeTrade output", "idx", i, "addr", out.Address, "coins", out.Coins.String())
	}

	if err := k.wsMoveCoins(ctx, inputs, outputs); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "move coins failed")
	}
	if err := k.tradeBurnModuleLiquid(ctx, outputsByAddr); err != nil {
		return nil, err
	}

	// Module balance invariants (like MakeOffer and TakeOffer)
	logger.Info("MakeTrade checking invariants before assertion")
	if err := k.AssertInvariants(ctx); err != nil {
		logger.Error("MakeTrade invariant check failed", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "invariant after MakeTrade")
	}
	logger.Info("MakeTrade invariants passed")

	// Record single trade with all operations
	logger.Info("MakeTrade recording trade", "operations_count", len(operations))
	tradeId, err := k.recordTradeWithOperations(ctx, msg.Trader, operations, msg.Note)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to record trade")
	}
	logger.Info("MakeTrade trade recorded", "trade_id", tradeId)

	// Emit EventPfandReleased for any offers that were closed
	if len(pfandReleases) > 0 {
		logger.Info("MakeTrade emitting pfand release events", "pfand_releases_count", len(pfandReleases))
		for _, pr := range pfandReleases {
			if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPfandReleased{
				Amount:  pr.amount,
				OfferId: pr.offerId,
				TradeId: tradeId,
			}); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to emit EventPfandReleased")
			}
		}
	}

	logger.Info("MakeTrade completed successfully", "trade_id", tradeId, "trader_outputs", traderOutputs)
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
