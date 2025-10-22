package keeper

import (
	"context"
	"strconv"
	"strings"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
)

func (k Keeper) MakeOffer(ctx context.Context, msg *whaleswapv1.MsgMakeOffer) (*whaleswapv1.MsgMakeOfferResponse, error) {
	// Parse maker
	makerBz, err := k.accKeeper.AddressCodec().StringToBytes(msg.Maker)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid maker: %s", err.Error())
	}
	maker := sdk.AccAddress(makerBz)

	have := msg.Have
	want := msg.Want
	if err := sdk.ValidateDenom(have.Denom); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid have denom: %s", have.Denom)
	}
	if err := sdk.ValidateDenom(want.Denom); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid want denom: %s", want.Denom)
	}
	if have.Denom == want.Denom {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "have and want denoms must differ: %s", have.Denom)
	}
	if !have.Amount.IsPositive() || !want.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "amounts must be > 0")
	}

	if k.bank.GetSupply(ctx, want.Denom).Amount.IsZero() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "want denom has no supply: %s", want.Denom)
	}
	if k.isLiquidDenom(want.Denom) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "want denom is liquid: %s", want.Denom)
	}
	// Per-offer balance check: maker must currently hold at least `have` amount
	balHaveCoin := k.bank.GetBalance(ctx, maker, have.Denom)
	if !balHaveCoin.IsGTE(have) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "have exceeds maker balance: %s < %s", balHaveCoin.String(), have.String())
	}

	pfandCoin := sdk.NewCoin(k.GetParams(ctx).PfandPerOffer.Denom, math.NewInt(0))
	if k.isLiquidDenom(have.Denom) {
		req := k.GetParams(ctx).PfandPerOffer
		if !req.Amount.IsZero() {
			bal := k.bank.GetBalance(ctx, maker, req.Denom)
			if !bal.IsGTE(req) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient pfand: %s < %s", bal.String(), req.String())
			}
			if err := k.bank.SendCoinsFromAccountToModule(ctx, maker, whaleswap.ModuleName, sdk.NewCoins(req)); err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "failed to lock pfand %s from maker %s", req.String(), msg.Maker)
			}
		}
		pfandCoin = k.GetParams(ctx).PfandPerOffer
	} else {
		if err := k.bank.SendCoinsFromAccountToModule(ctx, maker, whaleswap.ModuleName, sdk.NewCoins(have)); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to escrow have %s from maker %s", have.String(), msg.Maker)
		}
	}

	// GCD-first units: reduce ratio to simplest terms
	g := k.gcdInt(have.Amount, want.Amount)
	if !g.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid gcd")
	}
	unitHave := have.Amount.Quo(g)
	unitWant := want.Amount.Quo(g)
	if unitHave.IsZero() || unitWant.IsZero() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid unit ints")
	}
	remainingUnits := g
	if remainingUnits.IsZero() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "remaining units is zero")
	}

	id, err := k.offerSeq.Next(ctx)
	if err != nil {
		return nil, err
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	t := sdkCtx.BlockTime()
	offer := whaleswapv1.OfferData{
		OfferId:          id,
		Status:           whaleswapv1.OfferStatusOpen,
		Maker:            msg.Maker,
		UpdatedHeight:    uint64(sdkCtx.BlockHeight()),
		UpdatedTimestamp: &t,
		InitialHave:      have,
		InitialWant:      want,
		RemainingHave:    have,
		RemainingWant:    want,
		UnitHaveInt:      unitHave.String(),
		UnitWantInt:      unitWant.String(),
		RemainingUnits:   remainingUnits.String(),
		PfandLocked:      pfandCoin,
	}
	if err := k.OffersMap.Set(ctx, id, offer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to save offer %d", id)
	}
	if err := k.indexOfferOpen(ctx, offer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to index offer %d", id)
	}
	// Emit EventOfferCreated with plain numeric string (no extra quotes) for offer_id
	sdkCtx.EventManager().EmitEvent(
		sdk.NewEvent(
			"dysonprotocol.whaleswap.v1.EventOfferCreated",
			sdk.NewAttribute("offer_id", strconv.FormatUint(id, 10)),
		),
	)
	if pfandCoin.Amount.IsPositive() {
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPfandLocked{
			Amount:  pfandCoin,
			OfferId: id,
		}); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPfandLocked")
		}
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant failed after MakeOffer")
	}
	return &whaleswapv1.MsgMakeOfferResponse{OfferId: id}, nil
}

func (k Keeper) TakeOffer(ctx context.Context, msg *whaleswapv1.MsgTakeOffer) (*whaleswapv1.MsgTakeOfferResponse, error) {
	takerBz, err := k.accKeeper.AddressCodec().StringToBytes(msg.Taker)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid taker: %s", msg.Taker)
	}
	taker := sdk.AccAddress(takerBz)
	if len(msg.Trades) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "trades list must be non-empty")
	}

	seen := map[uint64]struct{}{}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
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

	for _, it := range msg.Trades {
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

		// Aggregate outputs: pay maker solid want; pay taker solid have
		outputsByAddr[maker] = outputsByAddr[maker].Add(sdk.NewCoin(wantDenom, requiredWant))
		if k.isLiquidDenom(haveDenom) {
			baseHave, derr := k.decodeLiquidDenom(haveDenom)
			if derr != nil {
				return nil, derr
			}
			outputsByAddr[msg.Taker] = outputsByAddr[msg.Taker].Add(sdk.NewCoin(baseHave, deliverHave))
			// Aggregate inputs: maker supplies liquid have to be burned
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

		// Determine received denom (unwrap liquid if needed)
		recDenom := haveDenom
		if k.isLiquidDenom(haveDenom) {
			if baseHave, derr := k.decodeLiquidDenom(haveDenom); derr == nil {
				recDenom = baseHave
			}
		}

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
			if k.isLiquidDenom(c.Denom) {
				continue
			}
			makerWants = makerWants.Add(c)
		}
	}
	takerCredits := sdk.NewCoins()
	if tcoins, ok := outputsByAddr[msg.Taker]; ok {
		for _, c := range tcoins {
			if k.isLiquidDenom(c.Denom) {
				continue
			}
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
		rem := deficit.Sub(basePart)
		if rem.IsPositive() {
			ldenom := whaleswapv1.LiquidDenom(denom)
			liqBal := k.bank.GetBalance(ctx, taker, ldenom).Amount
			if liqBal.LT(rem) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "taker insufficient %s: %s < %s", ldenom, liqBal.String(), rem.String())
			}
			inputsByAddr[msg.Taker] = inputsByAddr[msg.Taker].Add(sdk.NewCoin(ldenom, rem))
		}
	}

	// Module receives all liquid inputs to burn; add as outputs to module
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

	// Module solid inputs to cover remaining solid outputs not funded by taker base
	outputsSolidCoins := sdk.NewCoins()
	for _, coins := range outputsByAddr {
		for _, c := range coins {
			if k.isLiquidDenom(c.Denom) {
				continue
			}
			outputsSolidCoins = outputsSolidCoins.Add(c)
		}
	}
	inputsSolidCoins := sdk.NewCoins()
	for _, coins := range inputsByAddr {
		for _, c := range coins {
			if k.isLiquidDenom(c.Denom) {
				continue
			}
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

	if err := k.wsMoveCoins(ctx, inputs, outputs); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "move coins failed")
	}

	toBurn := sdk.NewCoins()
	if mcoins, ok := outputsByAddr[moduleBech]; ok {
		for _, c := range mcoins {
			if k.isLiquidDenom(c.Denom) && c.Amount.IsPositive() {
				toBurn = toBurn.Add(c)
			}
		}
	}
	if !toBurn.IsZero() {
		if _, err := k.nameSvc.BurnCoins(ctx, &nameservicev1.MsgBurnCoins{NameDestination: moduleBech, Amount: toBurn}); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "burn liquid failed")
		}
	}

	// totalSent/Recv already accumulated

	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant failed after TakeOffer")
	}

	// Record single trade with all operations
	tradeId, err := k.recordTradeWithOperations(ctx, msg.Taker, operations, "")
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to record trade")
	}

	// Emit EventPfandReleased for any offers that were closed
	for _, pr := range pfandReleases {
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPfandReleased{
			Amount:  pr.amount,
			OfferId: pr.offerId,
			TradeId: tradeId,
		}); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to emit EventPfandReleased")
		}
	}

	// Compute totals from operations
	totalSent := sdk.NewCoins()
	totalRecv := sdk.NewCoins()
	for _, op := range operations {
		totalSent = totalSent.Add(op.Sent)
		totalRecv = totalRecv.Add(op.Received)
	}

	return &whaleswapv1.MsgTakeOfferResponse{Sent: totalSent, Received: totalRecv}, nil
}

func (k Keeper) CancelOffer(ctx context.Context, msg *whaleswapv1.MsgCancelOffer) (*whaleswapv1.MsgCancelOfferResponse, error) {
	offer, err := k.OffersMap.Get(ctx, msg.OfferId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", msg.OfferId)
	}
	if offer.Status != whaleswapv1.OfferStatusOpen {
		return nil, cosmossdkerrors.Wrapf(err, "offer not open: %s", offer.Status)
	}
	closerBz, err := k.accKeeper.AddressCodec().StringToBytes(msg.Closer)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid closer: %s", msg.Closer)
	}
	closer := sdk.AccAddress(closerBz)
	makerBz, err := k.accKeeper.AddressCodec().StringToBytes(offer.Maker)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid maker: %s", offer.Maker)
	}
	maker := sdk.AccAddress(makerBz)

	eligible := closer.Equals(maker)
	pfandLocked := offer.PfandLocked
	if !eligible && pfandLocked.Amount.IsPositive() {
		haveDenom := offer.RemainingHave.Denom
		unitHave := offer.UnitHaveInt
		unit, ok := math.NewIntFromString(unitHave)
		if !ok || !unit.IsPositive() {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid unit_have_int")
		}
		makerBal := k.bank.GetBalance(ctx, maker, haveDenom).Amount
		if makerBal.LT(unit) {
			eligible = true
		}
	}
	if !eligible {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "not eligible to cancel offer")
	}

	offer.Status = whaleswapv1.OfferStatusCancelled
	if err := k.OffersMap.Set(ctx, offer.OfferId, offer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update offer %d", offer.OfferId)
	}
	// Remove reverse index entries and update owner/status via helper
	prev := offer
	if err := k.reindexOfferOnStatusChange(ctx, prev, offer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to reindex offer after cancel")
	}
	// Refund escrowed base have for normal offers
	if !k.isLiquidDenom(offer.RemainingHave.Denom) && offer.RemainingHave.Amount.IsPositive() {
		if err := k.bank.SendCoinsFromModuleToAccount(ctx, whaleswap.ModuleName, maker, sdk.NewCoins(offer.RemainingHave)); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to refund escrowed have %s to maker %s", offer.RemainingHave.String(), offer.Maker)
		}
	}
	if pfandLocked.Amount.IsPositive() {
		if err := k.bank.SendCoinsFromModuleToAccount(ctx, whaleswap.ModuleName, closer, sdk.NewCoins(pfandLocked)); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to send pfand %s to closer %s", pfandLocked.String(), msg.Closer)
		}
	}

	// Emit events
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventOfferCancelled{OfferId: offer.OfferId}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventOfferCancelled")
	}
	if pfandLocked.Amount.IsPositive() {
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPfandReleased{
			Amount:  pfandLocked,
			OfferId: offer.OfferId,
			TradeId: 0, // No trade for cancellation
		}); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPfandReleased")
		}
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant failed after CancelOffer")
	}
	return &whaleswapv1.MsgCancelOfferResponse{}, nil
}
