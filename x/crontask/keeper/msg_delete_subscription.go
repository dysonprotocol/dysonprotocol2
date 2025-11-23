package keeper

import (
	"context"

	errorsmod "cosmossdk.io/errors"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// DeleteSubscription removes an existing subscription, allowing only the creator to delete.
//
// Semantics:
//   - Permanently removes a subscription from storage.
//   - Only the creator of the subscription can delete it.
//   - No refunds are provided for remaining subscription time or fees.
//
// Validation:
//   - Creator address must be valid.
//   - Subscription must exist.
//   - Creator must match the subscription's creator field.
//
// State Updates:
//   - Removes subscription from storage (indexes are maintained automatically).
//
// Emits:
//   - EventSubscriptionDeleted(subscription_id, creator) on successful deletion.
//
// Returns:
//   - *crontasktypes.MsgDeleteSubscriptionResponse (empty response).
//
// Errors are returned on validation failures, subscription not found, unauthorized deletion,
// storage errors, or event emission failures; no panics.
func (k Keeper) DeleteSubscription(ctx context.Context, msg *crontasktypes.MsgDeleteSubscription) (*crontasktypes.MsgDeleteSubscriptionResponse, error) {
	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	sub, err := k.Subscriptions.Get(ctx, msg.SubscriptionId)
	if err != nil {
		return nil, errorsmod.Wrapf(sdkerrors.ErrNotFound, "subscription %d not found", msg.SubscriptionId)
	}
	if sub.Creator != msg.Creator {
		return nil, errorsmod.Wrap(sdkerrors.ErrUnauthorized, "only creator can delete subscription")
	}
	if err := k.Subscriptions.Remove(ctx, msg.SubscriptionId); err != nil {
		return nil, errorsmod.Wrapf(err, "failed to delete subscription [%d]", msg.SubscriptionId)
	}
	// No manual index cleanup required with IndexedMap; indexes are maintained automatically
	if err := sdkCtx.EventManager().EmitTypedEvent(&crontasktypes.EventSubscriptionDeleted{SubscriptionId: msg.SubscriptionId, Creator: msg.Creator}); err != nil {
		return nil, errorsmod.Wrap(err, "failed to emit subscription deleted event")
	}
	return &crontasktypes.MsgDeleteSubscriptionResponse{}, nil
}
