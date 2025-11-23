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
)

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
