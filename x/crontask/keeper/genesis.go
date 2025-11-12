package keeper

import (
	"context"
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"

	crontasktypes "dysonprotocol.com/x/crontask/types"
)

// InitGenesis initializes the module's state from a genesis state.
func (k Keeper) InitGenesis(ctx context.Context, genState *crontasktypes.GenesisState) error {
	// Validate the genesis state
	if err := crontasktypes.ValidateGenesis(genState); err != nil {
		return err
	}

	// Set module parameters - always set them regardless of genesis state
	var moduleParams crontasktypes.Params
	if genState.Params == nil {
		// Use default params if not provided
		moduleParams = crontasktypes.DefaultParams()
	} else {
		moduleParams = *genState.Params
	}

	// Set the parameters
	if err := k.Params.Set(ctx, moduleParams); err != nil {
		return err
	}

	// Determine the next task ID. If not provided (0) or stale (<= max task id),
	// default to max(existing tasks)+1 (or 1 if no tasks).
	var maxTaskID uint64
	for _, task := range genState.Tasks {
		if task.TaskId > maxTaskID {
			maxTaskID = task.TaskId
		}
	}
	nextTaskIDToSet := genState.NextTaskId
	if nextTaskIDToSet == 0 {
		if maxTaskID == 0 {
			nextTaskIDToSet = 1
		} else {
			nextTaskIDToSet = maxTaskID + 1
		}
	} else if nextTaskIDToSet <= maxTaskID {
		nextTaskIDToSet = maxTaskID + 1
	}
	if err := k.NextTaskID.Set(ctx, nextTaskIDToSet); err != nil {
		return err
	}

	// Import all tasks with basic message unpack validation
	for _, task := range genState.Tasks {
		for i, anyMsg := range task.Msgs {
			var sdkMsg sdk.Msg
			if err := k.cdc.UnpackAny(anyMsg, &sdkMsg); err != nil {
				return fmt.Errorf("invalid task message at index %d: %w", i, err)
			}
		}
		// Use SetTask to ensure secondary indexes are created consistently
		if err := k.SetTask(ctx, *task); err != nil {
			return err
		}
	}

	// Import subscriptions if provided
	for _, sub := range genState.Subscriptions {
		// Write primary record
		if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, *sub); err != nil {
			return err
		}
	}

	// Initialize subscription ID sequence. If not provided (0) or stale (<= max), set to max+1 (or 1 if none)
	var maxSubID uint64
	for _, sub := range genState.Subscriptions {
		if sub.SubscriptionId > maxSubID {
			maxSubID = sub.SubscriptionId
		}
	}
	nextSubID := genState.NextSubscriptionId
	if nextSubID == 0 {
		if maxSubID == 0 {
			nextSubID = 1
		} else {
			nextSubID = maxSubID + 1
		}
	} else if nextSubID <= maxSubID {
		nextSubID = maxSubID + 1
	}
	if err := k.NextSubscriptionID.Set(ctx, nextSubID); err != nil {
		return err
	}

	// Rebuild any raw secondary indexes derived from primary data (idempotent)
	if err := k.RebuildIndexes(ctx); err != nil {
		return err
	}

	return nil
}

// ExportGenesis exports the module's state to a genesis state.
func (k Keeper) ExportGenesis(ctx context.Context) (*crontasktypes.GenesisState, error) {
	// Get params - simple error handling following SDK pattern
	params, err := k.Params.Get(ctx)
	if err != nil {
		return nil, err
	}

	// Get next task ID
	nextTaskID, err := k.NextTaskID.Peek(ctx)
	if err != nil {
		return nil, err // Direct error propagation
	}

	// Get next subscription ID
	nextSubscriptionID, err := k.NextSubscriptionID.Peek(ctx)
	if err != nil {
		return nil, err
	}

	// Get all tasks
	var tasks []*crontasktypes.Task
	if err := k.Tasks.Walk(ctx, nil, func(taskID uint64, task crontasktypes.Task) (bool, error) {
		taskCopy := task // Create a copy to avoid modifying the same memory
		tasks = append(tasks, &taskCopy)
		return false, nil
	}); err != nil {
		return nil, err // Direct error propagation
	}

	// Get all subscriptions
	var subs []*crontasktypes.Subscription
	if err := k.Subscriptions.Walk(ctx, nil, func(id uint64, sub crontasktypes.Subscription) (bool, error) {
		s := sub
		subs = append(subs, &s)
		return false, nil
	}); err != nil {
		return nil, err
	}

	return &crontasktypes.GenesisState{
		Tasks:              tasks,
		NextTaskId:         nextTaskID,
		Params:             &params,
		NextSubscriptionId: nextSubscriptionID,
		Subscriptions:      subs,
	}, nil
}
