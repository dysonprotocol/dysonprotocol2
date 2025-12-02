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

// MakeTrade combines AMM pool swaps and orderbook takes into a single
// transaction with end-of-tx settlement.
//
// Semantics:
//   - Processes SwapLeg (AMM pool swaps) and TakeItem (orderbook takes)
//     operations in order.
//   - Aggregates all inputs/outputs across operations, then performs
//     orderbook-style netting.
//   - Trader credits offset maker wants; deficits covered from trader base
//     balance.
//   - PFAND released to trader when offers close, applied pre-netting.
//   - Enforces per-denom debit caps (max_input) and minimum outputs (min_output)
//     after netting.
//   - Executes final settlement via multisend; all operations succeed or
//     transaction fails.
//   - Enables circular trade dependencies through self-netting: trader
//     debit/credit pairs by denom are netted out, allowing complex arbitrage
//     chains where intermediate results cancel (e.g., A→B→C→A becomes net B+C
//     profit).
//
// Validation:
//   - Trader address must be valid.
//   - Operations must be non-empty.
//   - Note length capped by module params.
//   - Swap operations: pool must exist, denoms match pool, no duplicate pool_ids.
//   - Take operations: offer must exist and be open, no duplicate offer_ids.
//   - Auction operations currently rejected.
//
// State Updates:
//   - AMM pools: reserves updated, fees accrued, trade counters incremented.
//   - Offers: remaining units/wants/haves updated; closed when fully taken.
//   - Trade recorded with all operations, indexed by trader/pool/offer/auction.
//
// Emits:
//   - EventPfandReleased for each closed offer (amount, offer_id, trade_id)
//   - EventPoolSwap for each swap (pool_id, trade_id, operation_index)
//   - EventOfferTaken for each take (offer_id, trade_id, units_taken)
//   - EventTradeRecorded summary (trade_id, trader, num_operations, note)
//
// Returns:
//   - trade_id and final net trader_inputs/outputs after
//     netting/coverage/self-net.
//
// Errors are returned on validation failures (invalid trader, empty operations,
// malformed operations, caps exceeded) or execution failures (pool/offer updates,
// settlement, event emission); no panics.
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

	// Resolve key addresses
	moduleBech := k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String()
	traderBech := msg.Trader

	// Execute operations in order, mutating pools/offers and accumulating
	logger.Info("MakeTrade processing operations", "operations_count", len(msg.Operations))
	var operations []whaleswapv1.TradeOperation
	type pfandRelease struct {
		offerId uint64
		amount  sdk.Coin
	}
	var pfandReleases []pfandRelease
	pfandCredits := sdk.NewCoins()
	// Note: Duplicate pool IDs are allowed in operations. Each swap modifies
	// pool state sequentially, and deltaByDenom accumulates all changes.
	// This enables complex multi-step strategies like opposite-direction
	// trades on the same pool within a single MakeTrade (e.g., arbitrage cycles).
	seenOffers := make(map[uint64]bool)
	seenAuctions := make(map[uint64]bool)

	for i, op := range msg.Operations {
		switch v := op.Op.(type) {
		case *whaleswapv1.TradeOperation_Swap:
			leg := v.Swap
			if leg == nil || leg.PoolId == 0 {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap leg invalid")
			}
			logger.Info("MakeTrade processing swap operation", "operation_idx", i, "pool_id", leg.PoolId, "swap_in", leg.SwapIn, "swap_out", leg.SwapOut)
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
			if item == nil {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "take item missing")
			}
			logger.Info("MakeTrade processing take operation", "operation_idx", i, "offer_id", item.OfferId, "take_units", item.TakeUnits)
			if item.OfferId > 0 && seenOffers[item.OfferId] {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "duplicate offer_id %d in operations", item.OfferId)
			}
			seenOffers[item.OfferId] = true
			tradeOp, maker, makerWant, takerRecv, makerLiqIn, pfand, terr := k.tradeApplyTakeItem(ctx, msg.Trader, item, msg.Note)
			if terr != nil {
				return nil, terr
			}
			logger.Info("x/whaleswap MakeTrade take operation applied", "operation_idx", i, "maker", maker, "maker_want", makerWant, "taker_recv", takerRecv, "maker_liq_in", makerLiqIn, "pfand", pfand)
			operations = append(operations, tradeOp)
			// For self-takes (taker == maker), makerWant is a self-payment that nets to zero - don't add to outputs
			if maker != msg.Trader {
				addOut(maker, makerWant)
			}
			// DON'T add taker input explicitly - let tradeNetAndCover determine it via coverage
			addOut(msg.Trader, takerRecv)
			// Settlement funding
			if makerLiqIn.IsValid() && makerLiqIn.Amount.IsPositive() {
				// LIQUID: maker funds base-have
				addIn(maker, makerLiqIn)
			} else {
				// ESCROW: module funds base-have from escrowed balances
				addIn(moduleBech, takerRecv)
			}
			if pfand.IsValid() && pfand.Amount.IsPositive() {
				// Accumulate PFAND credit to trader (released on close), to be applied pre-netting
				pfandReleases = append(pfandReleases, pfandRelease{offerId: item.OfferId, amount: pfand})
				pfandCredits = pfandCredits.Add(pfand)
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

	// Apply PFAND releases (module -> trader) before netting so ordering of operations (SWAP vs TAKE) is irrelevant.
	// Also log explicit PFAND credits and add to aggregators as effective inputs.
	if !pfandCredits.IsZero() {
		logger.Info("x/whaleswap MakeTrade applying PFAND credits pre-netting", "pfand", pfandCredits)
		for _, c := range pfandCredits {
			addIn(moduleBech, c)
			addOut(traderBech, c)
		}
	}

	// Orderbook-style netting and coverage
	logger.Info("x/whaleswap MakeTrade before netting and coverage", "inputs_by_addr", inputsByAddr, "outputs_by_addr", outputsByAddr, "pfand", pfandCredits)
	if err := k.tradeNetAndCover(ctx, traderBech, inputsByAddr, outputsByAddr); err != nil {
		return nil, err
	}
	logger.Info("x/whaleswap MakeTrade after netting and coverage", "inputs_by_addr", inputsByAddr, "outputs_by_addr", outputsByAddr)

	// Self-net trader debits and credits by denom to allow circular profit without explicit debits.
	// Keep totals balanced by subtracting the same amount from the module's symmetric entries.
	// IMPORTANT: Do NOT self-net PFAND denoms; those flows must persist (module -> trader release and trader -> maker payment).
	{
		trIn := inputsByAddr[traderBech]
		trOut := outputsByAddr[traderBech]
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
				if outputsByAddr[moduleBech].AmountOf(d).IsPositive() {
					outputsByAddr[moduleBech] = outputsByAddr[moduleBech].Sub(sdk.NewCoin(d, n))
					if outputsByAddr[moduleBech].IsZero() {
						delete(outputsByAddr, moduleBech)
					}
				}
				if inputsByAddr[moduleBech].AmountOf(d).IsPositive() {
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
	noSettlement := len(inputs) == 0 && len(outputs) == 0
	if noSettlement {
		// No settlement required after full netting and coverage.
		logger.Info("MakeTrade no settlement required")
	} else {
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

	// Compute final trader inputs/outputs for response
	finalTraderInputs := inputsByAddr[traderBech]
	finalTraderOutputs := outputsByAddr[traderBech]

	logger.Info("MakeTrade completed successfully", "trade_id", tradeId, "trader_inputs", finalTraderInputs, "trader_outputs", finalTraderOutputs)
	return &whaleswapv1.MsgMakeTradeResponse{TradeId: tradeId, TraderInputs: finalTraderInputs, TraderOutputs: finalTraderOutputs}, nil
}
