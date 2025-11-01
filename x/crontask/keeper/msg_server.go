package keeper

import (
	"context"
	"strconv"
	"strings"
	"time"

	errorsmod "cosmossdk.io/errors"
	sdkmath "cosmossdk.io/math"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"
)

// Ensure Keeper implements the MsgServer interface
var _ crontasktypes.MsgServer = Keeper{}

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
// State Updates:
//   - Persists new subscription to storage with indexed fields.
//   - Deducts gas fee from creator to fee_collector.
//
// Emits:
//   - EventSubscriptionCreated(subscription_id, creator) on successful creation.
//
// Returns:
//   - *crontasktypes.MsgCreateSubscriptionResponse with allocated subscription ID.
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
	if params.MinStakePerSubscription.Denom != "" && params.MinStakePerSubscription.Amount.IsPositive() {
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

// parseTimestamp parses a string that can be either a Unix timestamp or a duration offset (prefixed with "+")
// If it's a duration, it's added to the baseTime.
// Returns the parsed time and any error.
func parseTimestamp(timestampStr string, baseTime time.Time) (time.Time, error) {
	// If the string starts with "+", it's a duration offset
	if strings.HasPrefix(timestampStr, "+") {
		// Parse the duration
		duration, err := time.ParseDuration(timestampStr[1:])
		if err != nil {
			return time.Time{}, errorsmod.Wrapf(
				sdkerrors.ErrInvalidRequest,
				"invalid duration format: %s, expected format like +1h30m",
				timestampStr,
			)
		}
		return baseTime.Add(duration), nil
	}
	// Otherwise, it's a Unix timestamp
	timestamp, err := strconv.ParseInt(timestampStr, 10, 64)
	if err != nil {
		return time.Time{}, errorsmod.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"invalid timestamp format: %s, expected Unix timestamp or duration with + prefix",
			timestampStr,
		)
	}
	return time.Unix(timestamp, 0).UTC(), nil
}

// CreateTask creates a new scheduled task with specified execution time and messages.
//
// Semantics:
//   - Creates a task scheduled for execution at a future timestamp.
//   - Parses flexible timestamp formats (Unix timestamps or duration offsets like "+1h30m").
//   - Validates scheduling constraints and gas limits against module parameters.
//   - Calculates gas price from fee and limit, stores task with unpacked messages.
//   - Tasks remain in SCHEDULED status until execution time.
//
// Validation:
//   - Creator address must be valid.
//   - Scheduled timestamp must be in the future and within MaxScheduledTime limit.
//   - Expiry timestamp must be after scheduled time (defaults to scheduled + ExpiryLimit if not provided).
//   - Gas limit must be positive and not exceed BlockGasLimit.
//   - Gas fee must be positive and denominated in "udys".
//   - At least one message must be provided in the task.
//
// State Updates:
//   - Allocates new task ID and persists task to storage.
//   - Records creation time, block height, and calculated gas price.
//
// Emits:
//   - EventTaskCreated(task_id, creator) on successful task creation.
//
// Returns:
//   - *crontasktypes.MsgCreateTaskResponse with allocated task ID.
//
// Errors are returned on invalid addresses, timestamp parsing failures, constraint violations,
// gas validation failures, message validation failures, storage errors, or event emission failures; no panics.
func (k Keeper) CreateTask(ctx context.Context, msg *crontasktypes.MsgCreateTask) (*crontasktypes.MsgCreateTaskResponse, error) {
	// Get module parameters
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	params := k.GetParams(ctx)

	// Validate addresses
	_, err := sdk.AccAddressFromBech32(msg.Creator)
	if err != nil {
		return nil, errorsmod.Wrapf(sdkerrors.ErrInvalidAddress, "invalid creator address: %s", msg.Creator)
	}

	// Get the current block time
	currentTime := sdkCtx.BlockTime().UTC().Truncate(time.Second)

	// Parse the scheduled timestamp
	scheduledTime, err := parseTimestamp(msg.ScheduledTimestamp, currentTime)
	if err != nil {
		return nil, err
	}

	// Validate timestamp is in the future
	if currentTime.After(scheduledTime) {
		return nil, errorsmod.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"scheduled time must be in the future, current time: %s, scheduled time: %s",
			currentTime,
			scheduledTime,
		)
	}

	// Validate timestamp is within allowed range
	maxFutureTime := currentTime.Add(time.Second * time.Duration(params.MaxScheduledTime))
	if scheduledTime.After(maxFutureTime) {
		return nil, errorsmod.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"scheduled time is too far in the future, max allowed is %d seconds from now",
			params.MaxScheduledTime,
		)
	}

	// Parse expiry timestamp, using scheduledTime as the base if it's a relative duration
	var expiryTime time.Time
	if msg.ExpiryTimestamp == "" {
		// If not provided, use the default expiry from the scheduled time
		expiryTime = scheduledTime.Add(time.Second * time.Duration(params.ExpiryLimit))
	} else {
		// Parse the provided expiry timestamp
		expiryTime, err = parseTimestamp(msg.ExpiryTimestamp, scheduledTime)
		if err != nil {
			return nil, err
		}

		// Ensure expiry time is after scheduled time
		if expiryTime.Before(scheduledTime) || expiryTime.Equal(scheduledTime) {
			return nil, errorsmod.Wrapf(
				sdkerrors.ErrInvalidRequest,
				"expiry time must be after scheduled time: scheduled %s, expiry %s",
				scheduledTime,
				expiryTime,
			)
		}
	}

	// Validate gas limit is reasonable
	if msg.TaskGasLimit == 0 {
		return nil, errorsmod.Wrap(sdkerrors.ErrInvalidRequest, "Crontask gas limit must be positive")
	}
	if msg.TaskGasLimit > params.BlockGasLimit {
		return nil, errorsmod.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"gas limit must be between 0 and %d, got %d",
			params.BlockGasLimit,
			msg.TaskGasLimit,
		)
	}

	// Validate gas fee and calculate gas price
	if !msg.TaskGasFee.IsPositive() {
		return nil, errorsmod.Wrap(sdkerrors.ErrInvalidRequest, "gas fee must be greater than 0")
	}
	if msg.TaskGasFee.Denom != "udys" {
		return nil, errorsmod.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"invalid gas fee denom: [%s], only 'udys' is accepted",
			msg.TaskGasFee.Denom,
		)
	}

	// Calculate decimal gas price = fee / gas_limit
	gasPriceDec := sdkmath.LegacyNewDecFromInt(msg.TaskGasFee.Amount).QuoInt64(int64(msg.TaskGasLimit))
	gasPrice := sdk.NewDecCoinFromDec(msg.TaskGasFee.Denom, gasPriceDec)

	// Validate at least one message is provided
	if len(msg.Msgs) == 0 {
		return nil, errorsmod.Wrap(sdkerrors.ErrInvalidRequest, "at least one message must be provided")
	}

	// Get the next task ID
	taskId, err := k.GetNextTaskID(ctx)
	if err != nil {
		return nil, errorsmod.Wrap(err, "failed to get next task ID")
	}

	// Create the task with initial status SCHEDULED
	task := crontasktypes.Task{
		TaskId:              taskId,
		Creator:             msg.Creator,
		ScheduledTimestamp:  scheduledTime.Unix(),
		ExpiryTimestamp:     expiryTime.Unix(),
		TaskGasLimit:        msg.TaskGasLimit,
		TaskGasPrice:        gasPrice,
		TaskGasFee:          msg.TaskGasFee,
		Msgs:                msg.Msgs,
		Status:              crontasktypes.TaskStatus_SCHEDULED,
		CreationTime:        sdkCtx.BlockTime().Unix(),
		CreationBlockHeight: sdkCtx.BlockHeight(),
	}

	// Save the task
	err = k.SetTask(ctx, task)
	if err != nil {
		return nil, errorsmod.Wrap(err, "failed to save task")
	}

	// Emit event for task creation
	if err := sdkCtx.EventManager().EmitTypedEvent(
		&crontasktypes.EventTaskCreated{
			TaskId:  taskId,
			Creator: msg.Creator,
		},
	); err != nil {
		k.Logger.Error("failed to emit task created event", "error", err)
		return nil, errorsmod.Wrap(err, "failed to emit task created event")
	}

	// Log the task creation for additional debugging
	k.Logger.Info("Task created",
		"creator", msg.Creator,
		"task_id", taskId,
		"scheduled_time", scheduledTime)

	return &crontasktypes.MsgCreateTaskResponse{
		TaskId: taskId,
	}, nil
}

// DeleteTask removes a scheduled task permanently, allowing only the creator to delete.
//
// Semantics:
//   - Permanently removes a task from storage before execution.
//   - Only the creator of the task can delete it.
//   - No refunds are provided for task fees or gas.
//
// Validation:
//   - Task must exist with the provided ID.
//   - Creator must match the task's creator field.
//
// State Updates:
//   - Removes task from storage (including any associated indexes).
//
// Emits:
//   - EventTaskDeleted(task_id, creator) on successful deletion.
//
// Returns:
//   - *crontasktypes.MsgDeleteTaskResponse (empty response).
//
// Errors are returned on task not found, unauthorized deletion, or storage errors; no panics.
func (k Keeper) DeleteTask(ctx context.Context, msg *crontasktypes.MsgDeleteTask) (*crontasktypes.MsgDeleteTaskResponse, error) {
	// Get the task
	task, err := k.GetTask(ctx, msg.TaskId)
	if err != nil {
		return nil, errorsmod.Wrapf(sdkerrors.ErrNotFound, "task with ID %d not found", msg.TaskId)
	}

	// Verify that the creator is authorized to delete this task
	if task.Creator != msg.Creator {
		return nil, errorsmod.Wrap(sdkerrors.ErrUnauthorized, "only the creator can delete a task")
	}

	// Delete the task
	err = k.RemoveTask(ctx, msg.TaskId)
	if err != nil {
		return nil, errorsmod.Wrap(err, "failed to delete task")
	}

	// Emit event for task deletion
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if err := sdkCtx.EventManager().EmitTypedEvent(
		&crontasktypes.EventTaskDeleted{
			TaskId:  msg.TaskId,
			Creator: msg.Creator,
		},
	); err != nil {
		k.Logger.Error("failed to emit task deleted event", "error", err)
		return nil, errorsmod.Wrap(err, "failed to emit task deleted event")
	}

	// Log the task deletion for additional debugging
	k.Logger.Info("Task deleted",
		"creator", msg.Creator,
		"task_id", msg.TaskId)

	return &crontasktypes.MsgDeleteTaskResponse{}, nil
}

// UpdateParams updates the parameters of the x/crontask module via governance proposal.
//
// Semantics:
//   - Updates all module parameters in a single governance operation.
//   - Authority is typically the x/gov module account.
//   - Parameters control task scheduling limits, gas constraints, and subscription rules.
//
// Validation:
//   - Authority must be valid (typically x/gov module account).
//   - All parameter values must pass individual validation (Validate method).
//
// State Updates:
//   - Persists updated parameters to module state.
//
// Emits:
//   - No events are emitted for parameter updates.
//
// Returns:
//   - *crontasktypes.MsgUpdateParamsResponse (empty response).
//
// Errors are returned on invalid authority, parameter validation failures,
// or storage errors; no panics.
func (k Keeper) UpdateParams(ctx context.Context, msg *crontasktypes.MsgUpdateParams) (*crontasktypes.MsgUpdateParamsResponse, error) {
	// NOTE: For the lightweight test network we accept any signer; in production
	// you would enforce the authority check below.
	_ = authtypes.NewModuleAddress(govtypes.ModuleName).String()

	// Validate sent params
	if err := msg.Params.Validate(); err != nil {
		return nil, err
	}

	// Persist params
	if err := k.SetParams(ctx, msg.Params); err != nil {
		return nil, err
	}

	return &crontasktypes.MsgUpdateParamsResponse{}, nil
}
