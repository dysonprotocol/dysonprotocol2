package keeper

import (
	"context"

	errorsmod "cosmossdk.io/errors"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

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
