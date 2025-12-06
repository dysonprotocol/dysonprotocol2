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

/**
 * CancelOffer (maker or authorized third party) cancels an open offer and
 * refunds escrowed assets to the maker while releasing PFAND to the closer.
 */
// CancelOffer cancels an open offer, refunding escrowed assets to the maker and
// releasing PFAND to the authorized closer (maker or eligible third party).
//
// Semantics:
//   - Eligibility: maker may always cancel; for liquid-mode offers, third party
//     may cancel if maker's balance of the have-denom drops below one unit_have
//     (enables recovery when maker becomes insolvent).
//   - State updates: sets offer status to cancelled, persists the offer, and
//     reindexes it for queries.
//   - Refunds: for escrow-settlement offers, sends remaining have coins from
//     module to maker; sends any locked PFAND from module to closer.
//   - Reindexing: updates reverse indexes (owner, status) via helper.
//
// Emits:
//   - EventOfferCancelled (offer_id)
//   - EventPfandReleased (amount, offer_id, trade_id=0) if PFAND was locked
//
// Returns:
//   - *whaleswapv1.MsgCancelOfferResponse (empty)
//
// Errors are returned on offer not found, offer not open, invalid addresses,
// invalid unit_have_int, closer not eligible, storage failures, bank transfer
// failures, event emission failures, or invariant assertion failures; no panics.
func (k Keeper) CancelOffer(ctx context.Context, msg *whaleswapv1.MsgCancelOffer) (*whaleswapv1.MsgCancelOfferResponse, error) {
	offer, err := k.OffersMap.Get(ctx, msg.OfferId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", msg.OfferId)
	}
	if offer.Status != whaleswapv1.OfferStatusOpen {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "offer not open: %s", offer.Status)
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
		// Compute diagnostics for detailed error context
		diagHaveDenom := offer.RemainingHave.Denom
		diagUnitHave := offer.UnitHaveInt
		diagMakerBal := k.bank.GetBalance(ctx, maker, diagHaveDenom).Amount
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"not eligible to cancel offer: closer=%s maker=%s pfand_locked=%s have_denom=%s unit_have_int=%s maker_balance=%s",
			msg.Closer,
			offer.Maker,
			pfandLocked.String(),
			diagHaveDenom,
			diagUnitHave,
			diagMakerBal.String(),
		)
	}

	// Capture previous state BEFORE status change for correct reindexing
	prevStatus := offer.Status
	offer.Status = whaleswapv1.OfferStatusCancelled
	if err := k.OffersMap.Set(ctx, offer.OfferId, offer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update offer %d", offer.OfferId)
	}
	// Remove reverse index entries and update owner/status via helper
	// Create a copy with the old status for proper index removal
	prev := offer
	prev.Status = prevStatus
	if err := k.reindexOfferOnStatusChange(ctx, prev, offer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to reindex offer after cancel")
	}

	// Update address metrics
	volumeTaken := offer.InitialHave.Amount.Sub(offer.RemainingHave.Amount)
	takenCoin := sdk.NewCoin(offer.InitialHave.Denom, volumeTaken)
	if err := k.incrementOfferStatusChange(ctx, offer.Maker, offer.Status, takenCoin); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update offer metrics")
	}
	// Refund escrowed base have for escrow-mode offers
	if offer.SettlementMode == whaleswapv1.SettlementMode_SETTLEMENT_ESCROW && offer.RemainingHave.Amount.IsPositive() {
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
