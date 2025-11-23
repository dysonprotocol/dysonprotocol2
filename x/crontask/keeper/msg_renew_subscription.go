package keeper

import (
	"context"

	errorsmod "cosmossdk.io/errors"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// RenewSubscription extends subscription expiry and recharges the fee, allowing only the creator.
//
// Semantics:
//   - Extends subscription expiry to current time + max_subscription_duration.
//   - Recharges the task gas fee from creator to fee_collector.
//   - Re-enables expired subscriptions if they were in "expired" status.
//   - Enforces minimum stake requirements before renewal.
//
// Validation:
//   - Creator address must be valid.
//   - Subscription must exist.
//   - Creator must match the subscription's creator field.
//   - Creator must have sufficient bonded stake if MinStakePerSubscription is configured.
//
// State Updates:
//   - Updates subscription expiry timestamp.
//   - Recharges gas fee from creator to fee_collector.
//   - Changes status from "expired" to "enabled" if previously expired.
//
// Emits:
//   - No events are emitted for renewal (subscription remains active).
//
// Returns:
//   - *crontasktypes.MsgRenewSubscriptionResponse (empty response).
//
// Errors are returned on validation failures, subscription not found, unauthorized renewal,
// insufficient stake, fee deduction failures, or storage errors; no panics.
func (k Keeper) RenewSubscription(ctx context.Context, msg *crontasktypes.MsgRenewSubscription) (*crontasktypes.MsgRenewSubscriptionResponse, error) {
	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	sub, err := k.Subscriptions.Get(ctx, msg.SubscriptionId)
	if err != nil {
		return nil, errorsmod.Wrapf(sdkerrors.ErrNotFound, "subscription %d not found", msg.SubscriptionId)
	}
	if sub.Creator != msg.Creator {
		return nil, errorsmod.Wrap(sdkerrors.ErrUnauthorized, "only creator can renew subscription")
	}
	// Enforce minimum stake per subscription (proxy via bank balance) before renewing
	params := k.GetParams(ctx)
	if params.MinStakePerSubscription.Denom != "" && params.MinStakePerSubscription.Amount.IsPositive() {
		// Count all current subscriptions for creator and multiply requirement via ByCreator index
		it, err := k.Subscriptions.Indexes.ByCreator.MatchExact(ctx, sub.Creator)
		if err != nil {
			return nil, errorsmod.Wrapf(err, "failed to iterate subscriptions by creator: %s", sub.Creator)
		}
		var totalSubs uint64
		for ; it.Valid(); it.Next() {
			totalSubs++
		}
		_ = it.Close()
		if totalSubs == 0 {
			totalSubs = 1
		}
		required := params.MinStakePerSubscription.Amount.MulRaw(int64(totalSubs))
		creatorAddr, err := sdk.AccAddressFromBech32(sub.Creator)
		if err != nil {
			return nil, errorsmod.Wrapf(sdkerrors.ErrInvalidAddress, "invalid creator address: %s", sub.Creator)
		}
		totalBonded, err := k.stakingKeeper.GetDelegatorBonded(ctx, creatorAddr)
		if err != nil {
			return nil, errorsmod.Wrap(err, "failed to get total bonded stake")
		}
		if totalBonded.LT(required) {
			return nil, errorsmod.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient delegated stake: have %s udys, need >= %s udys for %d subscriptions", totalBonded.String(), required.String(), totalSubs)
		}
	}

	// Renew: recharge fee and extend expiry to now + max_subscription_duration
	// charge fee equal to task_gas_fee
	creatorAddr, _ := sdk.AccAddressFromBech32(sub.Creator)
	if err := k.bankKeeper.SendCoinsFromAccountToModule(sdkCtx, creatorAddr, "fee_collector", sdk.NewCoins(sub.TaskGasFee)); err != nil {
		return nil, errorsmod.Wrapf(sdkerrors.ErrInsufficientFunds, "fee deduction failed: %s", err)
	}
	sub.ExpiryTimestamp = sdkCtx.BlockTime().Add(params.MaxSubscriptionDuration).Unix()
	if sub.Status == "expired" {
		sub.Status = "enabled"
		sub.StatusMessage = "renewed"
	}
	if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
		return nil, err
	}
	return &crontasktypes.MsgRenewSubscriptionResponse{}, nil
}
