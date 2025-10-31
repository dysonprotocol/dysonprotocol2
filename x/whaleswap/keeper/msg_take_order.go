package keeper

import (
	"context"
	"strings"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
)

func (k Keeper) TakeOffer(ctx context.Context, msg *whaleswapv1.MsgTakeOffer) (*whaleswapv1.MsgTakeOfferResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)

	logger.Info("TakeOffer starting", "taker", msg.Taker, "trades_count", len(msg.Trades))

	takerBz, err := k.accKeeper.AddressCodec().StringToBytes(msg.Taker)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid taker: %s", msg.Taker)
	}
	taker := sdk.AccAddress(takerBz)
	if len(msg.Trades) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "trades list must be non-empty")
	}

	seen := map[uint64]struct{}{}
	t := sdkCtx.BlockTime()

	outputsByAddr := map[string]sdk.Coins{}
	inputsByAddr := map[string]sdk.Coins{}
	var operations []whaleswapv1.TradeOperation
	type pfandRelease struct {
		offerId uint64
		amount  sdk.Coin
	}
	var pfandReleases []pfandRelease

	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	moduleBech := moduleAddr.String()

	logger.Info("TakeOffer processing trades")
	for _, it := range msg.Trades {
		logger.Info("TakeOffer processing trade", "offer_id", it.OfferId, "take_units", it.TakeUnits)
		if _, dup := seen[it.OfferId]; dup {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "duplicate offer_id %d", it.OfferId)
		}
		seen[it.OfferId] = struct{}{}

		offer, err := k.OffersMap.Get(ctx, it.OfferId)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "offer not found: %d", it.OfferId)
		}
		if offer.Status != whaleswapv1.OfferStatusOpen {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "offer %d not open", it.OfferId)
		}
		remainingUnits, ok := math.NewIntFromString(offer.RemainingUnits)
		if !ok || !remainingUnits.IsPositive() {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid remaining units")
		}
		takeUnits, perr := k.parseTakeUnits(remainingUnits, strings.TrimSpace(it.TakeUnits))
		if perr != nil {
			return nil, perr
		}
		unitWant, _ := math.NewIntFromString(offer.UnitWantInt)
		unitHave, _ := math.NewIntFromString(offer.UnitHaveInt)
		requiredWant := takeUnits.Mul(unitWant)
		deliverHave := takeUnits.Mul(unitHave)

		wantDenom := offer.RemainingWant.Denom
		haveDenom := offer.RemainingHave.Denom
		maker := offer.Maker

		// Aggregate outputs: pay maker solid want; pay taker have per settlement mode
		outputsByAddr[maker] = outputsByAddr[maker].Add(sdk.NewCoin(wantDenom, requiredWant))
		if offer.SettlementMode == whaleswapv1.SettlementMode_SETTLEMENT_LIQUID {
			outputsByAddr[msg.Taker] = outputsByAddr[msg.Taker].Add(sdk.NewCoin(haveDenom, deliverHave))
			inputsByAddr[maker] = inputsByAddr[maker].Add(sdk.NewCoin(haveDenom, deliverHave))
		} else {
			outputsByAddr[msg.Taker] = outputsByAddr[msg.Taker].Add(sdk.NewCoin(haveDenom, deliverHave))
		}

		// Update offer state; include pfand release as output to taker
		newUnits := remainingUnits.Sub(takeUnits)
		offer.UpdatedHeight = uint64(sdkCtx.BlockHeight())
		offer.UpdatedTimestamp = &t
		if newUnits.IsZero() {
			offer.Status = whaleswapv1.OfferStatusClosed
			offer.RemainingUnits = newUnits.String()
			offer.RemainingHave.Amount = math.NewInt(0)
			offer.RemainingWant.Amount = math.NewInt(0)
			if offer.PfandLocked.Amount.IsPositive() {
				// Pfand flows: module → taker (was locked in module when offer created)
				inputsByAddr[moduleBech] = inputsByAddr[moduleBech].Add(offer.PfandLocked)
				outputsByAddr[msg.Taker] = outputsByAddr[msg.Taker].Add(offer.PfandLocked)
				pfandReleases = append(pfandReleases, pfandRelease{offerId: offer.OfferId, amount: offer.PfandLocked})
			}
		} else {
			offer.RemainingUnits = newUnits.String()
			offer.RemainingHave.Amount = newUnits.Mul(unitHave)
			offer.RemainingWant.Amount = newUnits.Mul(unitWant)
		}

		// Received denom is always base have denom
		recDenom := haveDenom

		// Build operation record with execution results
		takeItemCopy := it
		op := whaleswapv1.TradeOperation{
			Op:       &whaleswapv1.TradeOperation_Take{Take: &takeItemCopy},
			Sent:     sdk.NewCoin(wantDenom, requiredWant),
			Received: sdk.NewCoin(recDenom, deliverHave),
		}
		operations = append(operations, op)

		// Persist offer (EventOfferTaken emitted by recordTradeWithOperations with proper trade_id)
		prev, _ := k.OffersMap.Get(ctx, offer.OfferId)
		if err := k.OffersMap.Set(ctx, offer.OfferId, offer); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to update offer %d", offer.OfferId)
		}
		if err := k.reindexOfferOnStatusChange(ctx, prev, offer); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to reindex offer after take")
		}
	}

	// Compute taker deficits per solid denom from outputs only (makers get wants; taker gets credits)
	makerWants := sdk.NewCoins()
	for addr, coins := range outputsByAddr {
		if addr == msg.Taker || addr == moduleBech {
			continue
		}
		for _, c := range coins {
			// all denoms are solid
			makerWants = makerWants.Add(c)
		}
	}
	takerCredits := sdk.NewCoins()
	if tcoins, ok := outputsByAddr[msg.Taker]; ok {
		for _, c := range tcoins {
			// all denoms are solid
			takerCredits = takerCredits.Add(c)
		}
	}

	// Net taker same-denom credits against maker wants, then add taker inputs: base first, then liquid L(denom)
	for _, wantCoin := range makerWants {
		denom := wantCoin.Denom
		wantAmt := wantCoin.Amount
		credit := takerCredits.AmountOf(denom)

		// Reduce taker outputs by the nettable portion min(credit, wantAmt)
		nettable := credit
		if wantAmt.LT(credit) {
			nettable = wantAmt
		}
		if nettable.IsPositive() {
			if coins, ok := outputsByAddr[msg.Taker]; ok {
				outputsByAddr[msg.Taker] = coins.Sub(sdk.NewCoin(denom, nettable))
				if outputsByAddr[msg.Taker].IsZero() {
					delete(outputsByAddr, msg.Taker)
				}
			}
		}

		if credit.GTE(wantAmt) {
			continue
		}
		deficit := wantAmt.Sub(credit)
		baseBal := k.bank.GetBalance(ctx, taker, denom).Amount
		basePart := baseBal
		if basePart.GT(deficit) {
			basePart = deficit
		}
		if basePart.IsPositive() {
			inputsByAddr[msg.Taker] = inputsByAddr[msg.Taker].Add(sdk.NewCoin(denom, basePart))
		}
		// No liquid remainder; module will cover remaining deficit
	}

	// No liquid inputs to route to module

	// Module solid inputs to cover remaining solid outputs not funded by taker base
	outputsSolidCoins := sdk.NewCoins()
	for _, coins := range outputsByAddr {
		for _, c := range coins {
			outputsSolidCoins = outputsSolidCoins.Add(c)
		}
	}
	inputsSolidCoins := sdk.NewCoins()
	for _, coins := range inputsByAddr {
		for _, c := range coins {
			inputsSolidCoins = inputsSolidCoins.Add(c)
		}
	}
	for _, out := range outputsSolidCoins {
		denom := out.Denom
		outAmt := out.Amount
		inAmt := inputsSolidCoins.AmountOf(denom)
		need := outAmt.Sub(inAmt)
		if need.IsPositive() {
			bal := k.bank.GetBalance(ctx, moduleAddr, denom).Amount
			if bal.LT(need) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "module backing insufficient %s: %s < %s", denom, bal.String(), need.String())
			}
			inputsByAddr[moduleBech] = inputsByAddr[moduleBech].Add(sdk.NewCoin(denom, need))
		}
	}

	var inputs []banktypes.Input
	for addr, coins := range inputsByAddr {
		if coins.IsZero() {
			continue
		}
		inputs = append(inputs, banktypes.Input{Address: addr, Coins: coins})
	}
	var outputs []banktypes.Output
	for addr, coins := range outputsByAddr {
		if coins.IsZero() {
			continue
		}
		outputs = append(outputs, banktypes.Output{Address: addr, Coins: coins})
	}
	if len(inputs) == 0 || len(outputs) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "no inputs or outputs for batch move")
	}

	// Debug: log the inputs and outputs before calling wsMoveCoins
	logger.Info("TakeOffer wsMoveCoins debug", "inputs_count", len(inputs), "outputs_count", len(outputs))
	for i, in := range inputs {
		logger.Info("TakeOffer input", "idx", i, "addr", in.Address, "coins", in.Coins.String())
	}
	for i, out := range outputs {
		logger.Info("TakeOffer output", "idx", i, "addr", out.Address, "coins", out.Coins.String())
	}

	if err := k.wsMoveCoins(ctx, inputs, outputs); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "move coins failed")
	}

	// No liquid burn required

	// totalSent/Recv already accumulated

	logger.Info("TakeOffer checking invariants")
	if err := k.AssertInvariants(ctx); err != nil {
		logger.Error("TakeOffer invariant check failed", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "invariant failed after TakeOffer")
	}

	// Record single trade with all operations
	logger.Info("TakeOffer recording trade", "operations_count", len(operations))
	tradeId, err := k.recordTradeWithOperations(ctx, msg.Taker, operations, "")
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to record trade")
	}
	logger.Info("TakeOffer trade recorded", "trade_id", tradeId)

	// Emit EventPfandReleased for any offers that were closed
	if len(pfandReleases) > 0 {
		logger.Info("TakeOffer emitting pfand release events", "pfand_releases_count", len(pfandReleases))
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

	// Compute totals from operations
	totalSent := sdk.NewCoins()
	totalRecv := sdk.NewCoins()
	for _, op := range operations {
		totalSent = totalSent.Add(op.Sent)
		totalRecv = totalRecv.Add(op.Received)
	}
	logger.Info("TakeOffer completed successfully", "trade_id", tradeId, "total_sent", totalSent, "total_received", totalRecv)

	return &whaleswapv1.MsgTakeOfferResponse{Sent: totalSent, Received: totalRecv}, nil
}
