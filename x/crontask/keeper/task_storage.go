package keeper

import (
	"context"
	"errors"

	"cosmossdk.io/collections"
	errorsmod "cosmossdk.io/errors"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	scripttypes "dysonprotocol.com/x/script/types"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// SetTask sets a task in the store
func (k Keeper) SetTask(ctx context.Context, task crontasktypes.Task) error {
	// Normalize MsgExec args/kwargs JSON for all embedded script exec messages
	for i, anyMsg := range task.Msgs {
		var sdkMsg sdk.Msg
		if err := k.cdc.UnpackAny(anyMsg, &sdkMsg); err != nil {
			return errorsmod.Wrapf(err, "failed to unpack message at index %d", i)
		}
		if exec, ok := sdkMsg.(*scripttypes.MsgExec); ok {
			// Validate and minify args (array) and kwargs (object)
			minArgs, err := minifyJSONArray(exec.Args)
			if err != nil {
				return errorsmod.Wrapf(err, "invalid args JSON in MsgExec at index %d", i)
			}
			minKw, err := minifyJSONObject(exec.Kwargs)
			if err != nil {
				return errorsmod.Wrapf(err, "invalid kwargs JSON in MsgExec at index %d", i)
			}
			exec.Args = minArgs
			exec.Kwargs = minKw
			// Re-pack back into Any
			packed, err := cdctypes.NewAnyWithValue(exec)
			if err != nil {
				return errorsmod.Wrapf(err, "failed to re-pack MsgExec at index %d", i)
			}
			task.Msgs[i] = packed
		}
	}

	// If an existing task with the same ID is present, remove its current index
	// entries before writing the updated task. This guarantees that secondary
	// indexes are always in sync with the primary record and mirrors the cleanup
	// logic performed in RemoveTask.

	// Attempt to fetch the previous version of the task. We purposefully ignore
	// a collections.ErrNotFound error because that simply means this is a brand
	// new task.
	if prev, err := k.Tasks.Get(ctx, task.TaskId); err == nil {
		if err := k.removeIndexes(ctx, prev); err != nil {
			return errorsmod.Wrapf(err, "failed to remove old indexes for task %d", task.TaskId)
		}
	} else if !errors.Is(err, collections.ErrNotFound) {
		// Any other error (e.g. I/O problems) should be reported upstream.
		return err
	}

	// Write the new / updated task and create its secondary-index keys.
	if err := k.Tasks.Set(ctx, task.TaskId, task); err != nil {
		return err
	}

	if err := k.addIndexes(ctx, task); err != nil {
		return errorsmod.Wrapf(err, "failed to add indexes for task %d", task.TaskId)
	}
	return nil
}

// GetTask gets a task by ID
func (k Keeper) GetTask(ctx context.Context, id uint64) (crontasktypes.Task, error) {
	return k.Tasks.Get(ctx, id)
}

// RemoveTask deletes a task from the store
func (k Keeper) RemoveTask(ctx context.Context, id uint64) error {
	// Load the task first so we can clean up its secondary indexes. If the task
	// does not exist we simply propagate the original collections.ErrNotFound
	// so the caller can decide how to handle it.
	task, err := k.Tasks.Get(ctx, id)
	if err != nil {
		return err
	}

	// Delete secondary-index keys (address, status+timestamp, status+gasPrice)
	if err := k.removeIndexes(ctx, task); err != nil {
		return errorsmod.Wrapf(err, "failed to remove indexes for task %d", id)
	}

	// Finally remove the primary record from the `Tasks` map.
	return k.Tasks.Remove(ctx, id)
}
