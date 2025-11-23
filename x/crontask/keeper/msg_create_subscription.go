package keeper

import (
	"context"

	errorsmod "cosmossdk.io/errors"
	sdkmath "cosmossdk.io/math"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// CreateSubscription creates a new event-triggered subscription with upfront fee payment.
//
// Semantics:
//   - Creates a subscription that triggers script execution when events match the filter.
//   - Enforces minimum stake requirements across all creator's subscriptions.
//   - Deducts anti-spam fee to fee_collector module account.
//   - Allocates unique subscription ID and sets expiry to current time + max_subscription_duration.
//   - Minifies JSON args/kwargs for storage efficiency.
//   - Initializes subscription with "enabled" status and zero trigger count.
//
// Validation:
//   - Creator address must be valid.
//   - Script address must be valid and non-empty.
//   - Function name must be non-empty.
//   - Task gas limit must be positive.
//   - Task gas fee must be positive.
//   - Filter, script_address, function, args, kwargs must not exceed length limits.
//   - Creator must have sufficient bonded stake if MinStakePerSubscription is configured.
//   - Args/kwargs must be valid JSON (array for args, object for kwargs).
//
// Emits:
//   - EventSubscriptionCreated(subscription_id, creator) on successful creation.
//
// Returns:
//   - MsgCreateSubscriptionResponse with allocated subscription ID.
//
// Errors are returned on validation failures, insufficient stake, fee deduction failures,
// JSON parsing errors, storage errors, or event emission failures; no panics.
func (k Keeper) CreateSubscription(ctx context.Context, msg *crontasktypes.MsgCreateSubscription) (*crontasktypes.MsgCreateSubscriptionResponse, error) {
	if err := msg.ValidateBasic(); err != nil {
		return nil, err
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Enforce minimum stake per subscription (across all subscriptions)
	params := k.GetParams(ctx)
	if !params.MinStakePerSubscription.IsZero() {
		// Count all subscriptions for this creator (any status) via ByCreator index
		it, err := k.Subscriptions.Indexes.ByCreator.MatchExact(ctx, msg.Creator)
		if err != nil {
			return nil, errorsmod.Wrapf(err, "failed to iterate subscriptions by creator: %s", msg.Creator)
		}
		var totalSubs uint64
		for ; it.Valid(); it.Next() {
			totalSubs++
		}
		_ = it.Close()
		if totalSubs == 0 {
			totalSubs = 1 // include the one being created
		} else {
			totalSubs++ // account for this new subscription
		}
		// required = MinStakePerSubscription.Amount * totalSubs
		required := params.MinStakePerSubscription.Amount.MulRaw(int64(totalSubs))
		creatorAddr, err := sdk.AccAddressFromBech32(msg.Creator)
		if err != nil {
			return nil, errorsmod.Wrapf(sdkerrors.ErrInvalidAddress, "invalid creator address: %s", msg.Creator)
		}
		totalBonded, err := k.stakingKeeper.GetDelegatorBonded(ctx, creatorAddr)
		if err != nil {
			return nil, errorsmod.Wrap(err, "failed to get total bonded stake")
		}
		if totalBonded.LT(required) {
			return nil, errorsmod.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient delegated stake: have %s udys, need >= %s udysfor %d subscriptions", totalBonded.String(), required.String(), totalSubs)
		}
	}

	// deduct anti-spam fee to fee_collector
	fee := sdk.NewCoins(msg.TaskGasFee)
	creatorAddr, err := sdk.AccAddressFromBech32(msg.Creator)
	if err != nil {
		return nil, errorsmod.Wrapf(sdkerrors.ErrInvalidAddress, "invalid creator address: %s", msg.Creator)
	}
	if err := k.bankKeeper.SendCoinsFromAccountToModule(sdkCtx, creatorAddr, "fee_collector", fee); err != nil {
		return nil, errorsmod.Wrapf(sdkerrors.ErrInsufficientFunds, "fee deduction failed for creator %s: %v", msg.Creator, err)
	}

	id, err := k.NextSubscriptionID.Next(ctx)
	if err != nil {
		return nil, errorsmod.Wrap(err, "failed to allocate next subscription_id")
	}

	// Minify and validate args/kwargs now (subscription storage should keep normalized values)
	minArgs, err := minifyJSONArray(msg.Args)
	if err != nil {
		return nil, errorsmod.Wrap(err, "invalid args JSON: must be array")
	}
	minKwargs, err := minifyJSONObject(msg.Kwargs)
	if err != nil {
		return nil, errorsmod.Wrap(err, "invalid kwargs JSON: must be object")
	}

	sub := crontasktypes.Subscription{
		SubscriptionId: id,
		Creator:        msg.Creator,
		Filter:         msg.Filter,
		ScriptAddress:  msg.ScriptAddress,
		Function:       msg.Function,
		Args:           minArgs,
		Kwargs:         minKwargs,
		TaskGasLimit:   msg.TaskGasLimit,
		TaskGasFee:     msg.TaskGasFee,
		Status:         "enabled",
		TriggerCount:   0,
	}
	// Set expiry to now + max_subscription_duration
	sdkNow := sdkCtx.BlockTime()
	sub.ExpiryTimestamp = sdkNow.Add(params.MaxSubscriptionDuration).Unix()
	// Ensure TaskGasPrice has a valid denom to avoid panics in JSON encoding
	sub.TaskGasPrice = sdk.NewDecCoinFromDec(msg.TaskGasFee.Denom, sdkmath.LegacyNewDec(0))

	if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
		return nil, errorsmod.Wrapf(err, "failed to persist subscription [%d]", id)
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&crontasktypes.EventSubscriptionCreated{SubscriptionId: id, Creator: msg.Creator}); err != nil {
		return nil, errorsmod.Wrap(err, "failed to emit subscription created event")
	}
	return &crontasktypes.MsgCreateSubscriptionResponse{SubscriptionId: id}, nil
}
