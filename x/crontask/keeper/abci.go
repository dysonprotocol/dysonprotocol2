package keeper

import (
	"context"
	"encoding/binary"
	"fmt"
	"runtime/debug"

	storetypes "cosmossdk.io/store/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	crontasktypes "dysonprotocol.com/x/crontask/types"
)

// BeginBlocker is called at the beginning of every block
func (k Keeper) BeginBlocker(ctx sdk.Context) error {
	// Get current block time directly from SDK context
	currentTime := ctx.BlockTime().Unix()
	k.Logger.Info("Current block time", "unix_time", currentTime)

	// Get module parameters to access BlockGasLimit
	params := k.GetParams(ctx)

	// Track how many tasks we selected this block (diagnostics)
	var selectedCount int = 0
	// Track cron gas used this block to enforce module-level cap
	var cronGasUsed uint64 = 0
	// Track last-block totals for metrics
	var blockTotalFees sdk.Coins

	// 1. expire overdue SCHEDULED tasks
	k.checkExpiredTasks(ctx, currentTime)

	// 2. move due SCHEDULED tasks to PENDING
	k.moveDueTasks(ctx, currentTime)

	// 3. process PENDING tasks ordered by gas price (desc)
	// Collect IDs first, then close iterator before mutating store for determinism
	iter := k.iterateStatusGas(ctx, crontasktypes.TaskStatus_PENDING, true)

	var pendingIDs []uint64
	for ; iter.Valid(); iter.Next() {
		key := iter.Key()
		id := binary.BigEndian.Uint64(key[len(key)-8:])
		pendingIDs = append(pendingIDs, id)
	}
	iter.Close()

	// pending metrics accumulators for tasks that remain pending into next block
	var pendingCount uint64 = 0
	var pendingGasRequested uint64 = 0
	var pendingOldestScheduledTs int64 = 0
	var pendingTotalFees sdk.Coins

	// Execute each pending task respecting block gas limit
	for _, taskId := range pendingIDs {
		task, err := k.GetTask(ctx, taskId)
		if err != nil {
			k.Logger.Error("failed to get pending task", "task_id", taskId, "error", err)
			continue
		}

		// Expiry guard: skip and expire overdue PENDING tasks before any budgeting or fees
		if task.ExpiryTimestamp <= currentTime {
			task.Status = crontasktypes.TaskStatus_EXPIRED
			task.ErrorLog = "Task expired before execution"
			// set execution markers to current block for observability
			task.ExecutionTimestamp = ctx.BlockTime().Unix()
			task.ExecutionBlockHeight = ctx.BlockHeight()
			if err := k.SetTask(ctx, task); err != nil {
				k.Logger.Error("failed to set task expired in pending guard", "task_id", task.TaskId, "error", err)
			} else {
				if emitErr := ctx.EventManager().EmitTypedEvent(
					&crontasktypes.EventTaskExpired{
						TaskId:  task.TaskId,
						Creator: task.Creator,
					},
				); emitErr != nil {
					k.Logger.Error("failed to emit task expired event in pending guard", "task_id", task.TaskId, "error", emitErr)
				}
			}
			continue
		}

		// Admit based on both the global block gas meter and module-level cap
		remainingBlock := ctx.BlockGasMeter().GasRemaining()
		var remainingModule uint64
		if params.BlockGasLimit > cronGasUsed {
			remainingModule = params.BlockGasLimit - cronGasUsed
		} else {
			remainingModule = 0
		}
		if task.TaskGasLimit > remainingBlock || task.TaskGasLimit > remainingModule {
			k.Logger.Debug("Skipping task - insufficient remaining gas",
				"task_id", taskId,
				"task_gas_limit", task.TaskGasLimit,
				"remaining_block_gas", remainingBlock,
				"remaining_module_gas", remainingModule,
				"module_block_gas_limit", params.BlockGasLimit,
			)
			// count towards next block's pending snapshot
			pendingCount++
			pendingGasRequested += task.TaskGasLimit
			if pendingOldestScheduledTs == 0 || task.ScheduledTimestamp < pendingOldestScheduledTs {
				pendingOldestScheduledTs = task.ScheduledTimestamp
			}
			pendingTotalFees = pendingTotalFees.Add(task.TaskGasFee)
			continue
		}

		// Log selection decision before execution
		k.Logger.Debug("crontask selecting task",
			"task_id", taskId,
			"task_gas_limit", task.TaskGasLimit,
			"block_gas_remaining_before", remainingBlock,
			"module_gas_remaining_before", remainingModule,
		)
		selectedCount++

		// Collect fee
		gasFee := sdk.NewCoins(task.TaskGasFee)
		creatorAddr, err := sdk.AccAddressFromBech32(task.Creator)
		if err != nil {
			task.Status = crontasktypes.TaskStatus_FAILED
			task.ErrorLog = fmt.Sprintf("invalid creator address: %s", err)
			// mark execution time for consistency with FAILED semantics
			task.ExecutionTimestamp = ctx.BlockTime().Unix()
			task.ExecutionBlockHeight = ctx.BlockHeight()
			if err := k.SetTask(ctx, task); err != nil {
				k.Logger.Error("failed to set task failed due to invalid creator address", "task_id", task.TaskId, "error", err)
			}
			// emit failure event
			if emitErr := ctx.EventManager().EmitTypedEvent(
				&crontasktypes.EventTaskFailed{
					TaskId:  task.TaskId,
					Creator: task.Creator,
					Error:   task.ErrorLog,
				},
			); emitErr != nil {
				k.Logger.Error("failed to emit task failed event (invalid creator)", "task_id", task.TaskId, "error", emitErr)
			}
			continue
		}

		if err := k.bankKeeper.SendCoinsFromAccountToModule(ctx, creatorAddr, "fee_collector", gasFee); err != nil {
			task.Status = crontasktypes.TaskStatus_FAILED
			task.ErrorLog = fmt.Sprintf("fee deduction failed: %s", err)
			// mark execution time for consistency with FAILED semantics
			task.ExecutionTimestamp = ctx.BlockTime().Unix()
			task.ExecutionBlockHeight = ctx.BlockHeight()
			if err := k.SetTask(ctx, task); err != nil {
				k.Logger.Error("failed to set task failed due to fee deduction failure", "task_id", task.TaskId, "error", err)
			}
			// emit failure event
			if emitErr := ctx.EventManager().EmitTypedEvent(
				&crontasktypes.EventTaskFailed{
					TaskId:  task.TaskId,
					Creator: task.Creator,
					Error:   task.ErrorLog,
				},
			); emitErr != nil {
				k.Logger.Error("failed to emit task failed event (fee deduction)", "task_id", task.TaskId, "error", emitErr)
			}
			continue
		}

		// Track total fees for metrics (sum per denom)
		blockTotalFees = blockTotalFees.Add(gasFee...)

		// Execute
		if err := k.executeTask(ctx, &task); err != nil {
			k.Logger.Error("execution error", "task_id", taskId, "error", err)
		}

		// no per-task message counting for metrics; remain cumulative-free per the new spec
		// Track actual cron gas used against module cap
		cronGasUsed += task.TaskGasConsumed
		k.Logger.Debug("Task executed", "task_id", taskId, "gas_used", task.TaskGasConsumed)
	}

	k.Logger.Info("crontask selection summary", "selected_count", selectedCount, "block_gas_used", ctx.BlockGasMeter().GasConsumed(), "cron_module_gas_used", cronGasUsed, "cron_module_gas_limit", params.BlockGasLimit)

	// Persist last-block metrics as singleton for reference by new crontasks
	metrics := crontasktypes.Metrics{
		ExecutedTotalGas:         cronGasUsed,
		ExecutedTotalFees:        blockTotalFees,
		ExecutedTaskCount:        uint64(selectedCount),
		PendingTaskCount:         pendingCount,
		PendingGasRequested:      pendingGasRequested,
		PendingOldestScheduledTs: pendingOldestScheduledTs,
		// removed highest gas price field
	}
	if err := k.SetMetrics(ctx, metrics); err != nil {
		k.Logger.Error("failed to persist last-block metrics", "error", err)
	}

	// Emit metrics event for observability each block
	if emitErr := ctx.EventManager().EmitTypedEvent(
		&crontasktypes.EventCrontaskMetrics{
			ExecutedTotalGas:         cronGasUsed,
			ExecutedTotalFees:        []sdk.Coin(blockTotalFees),
			ExecutedTaskCount:        uint64(selectedCount),
			PendingTaskCount:         pendingCount,
			PendingGasRequested:      pendingGasRequested,
			PendingOldestScheduledTs: pendingOldestScheduledTs,
			PendingTotalGasFees:      []sdk.Coin(pendingTotalFees),
		},
	); emitErr != nil {
		k.Logger.Error("failed to emit crontask metrics event", "error", emitErr)
	}
	// 4. clean up old tasks beyond retention window
	if err := k.removeOldTasks(ctx, currentTime); err != nil {
		k.Logger.Error("failed to clean up old tasks", "error", err)
	}

	return nil
}

// checkExpiredTasks finds and marks expired tasks that haven't been executed yet
func (k Keeper) checkExpiredTasks(ctx context.Context, currentTime int64) {
	// Scan both SCHEDULED and PENDING to purge overdue tasks before selection
	statuses := []string{
		crontasktypes.TaskStatus_SCHEDULED,
		crontasktypes.TaskStatus_PENDING,
	}

	for _, status := range statuses {
		iter := k.iterateStatusTimestamp(ctx, status, false)
		statusPrefix := append(indexStatusTsPrefix, []byte(status)...)

		// collect first, then close iterator before mutating
		var toExpire []uint64
		for ; iter.Valid(); iter.Next() {
			key := iter.Key()
			if len(key) < len(statusPrefix)+8+8 {
				continue
			}
			id := binary.BigEndian.Uint64(key[len(key)-8:])

			task, err := k.GetTask(ctx, id)
			if err != nil {
				k.Logger.Error("failed to load task", "id", id, "err", err)
				continue
			}

			if task.ExpiryTimestamp <= currentTime {
				toExpire = append(toExpire, id)
			}
		}
		iter.Close()

		for _, id := range toExpire {
			task, err := k.GetTask(ctx, id)
			if err != nil {
				k.Logger.Error("failed to load task before expire", "id", id, "err", err)
				continue
			}
			task.Status = crontasktypes.TaskStatus_EXPIRED
			task.ErrorLog = "Task expired before execution"
			// set execution markers to current block for observability
			sdkCtx := sdk.UnwrapSDKContext(ctx)
			task.ExecutionTimestamp = sdkCtx.BlockTime().Unix()
			task.ExecutionBlockHeight = sdkCtx.BlockHeight()
			if err := k.SetTask(ctx, task); err != nil {
				k.Logger.Error("failed to set task expired", "task_id", task.TaskId, "error", err)
				continue
			}
			// Emit EventTaskExpired for observability
			if emitErr := sdkCtx.EventManager().EmitTypedEvent(
				&crontasktypes.EventTaskExpired{
					TaskId:  task.TaskId,
					Creator: task.Creator,
				},
			); emitErr != nil {
				k.Logger.Error("failed to emit task expired event", "task_id", task.TaskId, "error", emitErr)
			}
		}
	}
}

// moveDueTasks moves tasks from SCHEDULED to PENDING when their scheduled time has arrived
func (k Keeper) moveDueTasks(ctx context.Context, currentTime int64) {
	iter := k.iterateStatusTimestamp(ctx, crontasktypes.TaskStatus_SCHEDULED, false)

	statusPrefix := append(indexStatusTsPrefix, []byte(crontasktypes.TaskStatus_SCHEDULED)...)

	// collect first, then close iterator before mutating
	var toPending []uint64
	for ; iter.Valid(); iter.Next() {
		key := iter.Key()
		if len(key) < len(statusPrefix)+8+8 {
			continue
		}
		scheduledTime := int64(binary.BigEndian.Uint64(key[len(statusPrefix) : len(statusPrefix)+8]))
		if scheduledTime > currentTime {
			break
		}
		id := binary.BigEndian.Uint64(key[len(key)-8:])

		task, err := k.GetTask(ctx, id)
		if err != nil {
			k.Logger.Error("failed to load task", "id", id, "err", err)
			continue
		}

		if task.ScheduledTimestamp <= currentTime {
			toPending = append(toPending, id)
		}
	}
	iter.Close()

	for _, id := range toPending {
		task, err := k.GetTask(ctx, id)
		if err != nil {
			k.Logger.Error("failed to load task before pending", "id", id, "err", err)
			continue
		}
		task.Status = crontasktypes.TaskStatus_PENDING
		if err := k.SetTask(ctx, task); err != nil {
			k.Logger.Error("failed to set task pending in moveDueTasks", "task_id", task.TaskId, "error", err)
			continue
		}
		// Emit EventTaskPending when transitioning to PENDING
		sdkCtx := sdk.UnwrapSDKContext(ctx)
		if emitErr := sdkCtx.EventManager().EmitTypedEvent(
			&crontasktypes.EventTaskPending{
				TaskId:  task.TaskId,
				Creator: task.Creator,
			},
		); emitErr != nil {
			k.Logger.Error("failed to emit task pending event", "task_id", task.TaskId, "error", emitErr)
		}
	}
}

// executeTask executes a task and updates its status based on the result
func (k Keeper) executeTask(ctx context.Context, task *crontasktypes.Task) error {
	// Reset results fields
	task.MsgResults = nil
	task.ErrorLog = ""
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	// Create a cache context with gas meter
	cacheCtx, write := sdkCtx.CacheContext()
	cacheCtx = cacheCtx.WithGasMeter(storetypes.NewGasMeter(task.TaskGasLimit))

	k.Logger.Info("Executing task",
		"task_id", task.TaskId,
		"gas_limit", task.TaskGasLimit,
		"msg_count", len(task.Msgs))

	// Execute messages
	err := k.executeMsgs(cacheCtx, task)

	// Calculate gas used and store it in the task
	gasUsed := cacheCtx.GasMeter().GasConsumed()
	task.TaskGasConsumed = gasUsed

	// Account actual gas used into the global block gas meter
	// This ensures cron execution contributes to the block-wide gas accounting.
	sdkCtx.BlockGasMeter().ConsumeGas(gasUsed, "crontask task used")

	if err != nil {
		// Update task status to failed
		task.Status = crontasktypes.TaskStatus_FAILED
		task.ExecutionTimestamp = sdkCtx.BlockTime().Unix()
		task.ExecutionBlockHeight = sdkCtx.BlockHeight()

		// Emit failure event (do not forward cached events on failure)
		emitErr := sdkCtx.EventManager().EmitTypedEvent(
			&crontasktypes.EventTaskFailed{
				TaskId:  task.TaskId,
				Creator: task.Creator,
				Error:   task.ErrorLog,
			},
		)
		if emitErr != nil {
			k.Logger.Error("failed to emit task failed event", "error", emitErr)
		}

		// Log the failure details
		k.Logger.Info("Task execution failed",
			"task_id", task.TaskId,
			"gas_used", gasUsed,
			"error", err,
			"error_log", task.ErrorLog)
	} else {
		// Update task status to done and write changes
		task.Status = crontasktypes.TaskStatus_DONE
		task.ExecutionTimestamp = sdkCtx.BlockTime().Unix()
		task.ExecutionBlockHeight = sdkCtx.BlockHeight()
		// NOTE: defer actual write and event forwarding until after we confirm state persisted

		// Get result count for logging
		resultCount := len(task.MsgResults)

		// Log the success details
		k.Logger.Info("Task execution successful",
			"task_id", task.TaskId,
			"gas_used", gasUsed,
			"results_count", resultCount)
	}

	// Save the updated task BEFORE committing cacheCtx. Only commit/forward events if both err and save succeed.
	saveErr := k.SetTask(ctx, *task)
	if err == nil && saveErr == nil {
		// Commit cached state; CacheContext will forward events automatically
		write()

		_ = sdkCtx.EventManager().EmitTypedEvent(
			&crontasktypes.EventTaskExecuted{
				TaskId:  task.TaskId,
				Creator: task.Creator,
				Status:  task.Status,
				Success: true,
			},
		)
		return nil
	}

	// If SetTask failed, prefer surfacing that error explicitly
	if saveErr != nil {
		return fmt.Errorf("failed to save task after execution: %w", saveErr)
	}

	// Otherwise return the original execution error
	return err
}

// executeMsgs processes all messages in a task
func (k Keeper) executeMsgs(ctx context.Context, task *crontasktypes.Task) error {
	// Get messages from task using the GetMessages method
	msgs, err := task.GetMessages()
	if err != nil {
		task.ErrorLog = fmt.Sprintf("failed to unpack messages: %s", err.Error())
		return fmt.Errorf("failed to unpack messages: %w", err)
	}

	// Create a slice to collect successful results
	var results []sdk.Msg

	for i, msg := range msgs {
		// Safely invoke the message
		resultMsg, err := k.safeInvokeMsg(ctx, msg)
		if err != nil {
			// Set error in the task
			task.ErrorLog = fmt.Sprintf("message at index %d failed: %s", i, err.Error())

			// Return detailed error
			return fmt.Errorf("message at index %d failed: %w", i, err)
		}

		// Add the result to our collection (if not nil)
		if resultMsg != nil {
			results = append(results, resultMsg)
		}
	}

	// Set all results at once using the new SetMessageResults method
	if len(results) > 0 {
		if err := task.SetMessageResults(results); err != nil {
			task.ErrorLog = fmt.Sprintf("failed to set message results: %s", err.Error())
			return fmt.Errorf("failed to set message results: %w", err)
		}
	} else {
		// Ensure empty results
		task.MsgResults = nil
	}

	// Only log success if we get here without errors
	k.Logger.Info("All messages executed successfully",
		"task_id", task.TaskId,
		"result_count", len(results))

	return nil
}

// safeInvokeMsg safely executes a message, catching any panics that might occur
func (k Keeper) safeInvokeMsg(ctx context.Context, msg sdk.Msg) (result sdk.Msg, err error) {
	// Use defer-recover pattern to catch panics
	defer func() {
		if r := recover(); r != nil {
			stack := string(debug.Stack())

			// Check for specific gas-related panics from Cosmos SDK
			switch p := r.(type) {
			case storetypes.ErrorOutOfGas:
				err = fmt.Errorf("out of gas: %s", p.Descriptor)
				k.Logger.Error("Message execution ran out of gas",
					"msg_type", sdk.MsgTypeURL(msg),
					"descriptor", p.Descriptor)
			case storetypes.ErrorGasOverflow:
				err = fmt.Errorf("gas overflow: %s", p.Descriptor)
				k.Logger.Error("Message execution caused gas overflow",
					"msg_type", sdk.MsgTypeURL(msg),
					"descriptor", p.Descriptor)
			default:
				// Log the full error with stack trace for other panics
				k.Logger.Error("Message execution panicked",
					"msg_type", sdk.MsgTypeURL(msg),
					"panic", r,
					"stack", stack)
				err = fmt.Errorf("message execution panicked: %v", r)
			}
		}
	}()

	// Add debug logging to check if MsgRouterService is nil
	msgType := sdk.MsgTypeURL(msg)
	k.Logger.Info("Attempting to invoke message",
		"msg_type", msgType,
		"msg_router_is_nil", k.MsgRouterService == nil)

	// Invoke the message handler - use `HandleDeliver` method
	handler := k.MsgRouterService.Handler(msg)
	if handler == nil {
		return nil, fmt.Errorf("no handler found for message type: %s", sdk.MsgTypeURL(msg))
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)
	msgResult, err := handler(sdkCtx, msg)
	if err != nil {
		return nil, err
	}

	// Forward events produced by the message execution into the current context
	// so they are visible to the outer cache context and ultimately to ABCI once committed.
	if msgResult != nil && len(msgResult.Events) > 0 {
		for _, event := range msgResult.Events {
			k.Logger.Info("cron EmitTypedEvent msgResult.Events", "event", event)
			sdkCtx.EventManager().EmitEvent(sdk.Event{
				Type:       event.Type,
				Attributes: event.Attributes,
			})
		}
	}

	k.Logger.Info("cron forwarding events", "count", len(sdkCtx.EventManager().Events()))

	if msgResult != nil && msgResult.MsgResponses != nil && len(msgResult.MsgResponses) > 0 {
		resp, ok := msgResult.MsgResponses[0].GetCachedValue().(sdk.Msg)
		if ok {
			result = resp
		}
	}

	return result, nil
}

// removeOldTasks deletes terminal-state tasks (DONE, FAILED, EXPIRED) whose
// execution/expiry timestamps are older than the configured CleanUpTime.
func (k Keeper) removeOldTasks(ctx context.Context, currentTime int64) error {
	params := k.GetParams(ctx)

	// If CleanUpTime is zero, feature disabled.
	if params.CleanUpTime == 0 {
		return nil
	}

	cutoff := currentTime - params.CleanUpTime

	// Terminal statuses
	statuses := []string{
		crontasktypes.TaskStatus_DONE,
		crontasktypes.TaskStatus_FAILED,
		crontasktypes.TaskStatus_EXPIRED,
	}

	for _, status := range statuses {
		iter := k.iterateStatusTimestamp(ctx, status, false) // oldest → newest
		var deleteIDs []uint64
		statusPrefix := append(indexStatusTsPrefix, []byte(status)...)

		for ; iter.Valid(); iter.Next() {
			key := iter.Key()
			if len(key) < len(statusPrefix)+8+8 {
				continue
			}
			ts := int64(binary.BigEndian.Uint64(key[len(statusPrefix) : len(statusPrefix)+8]))
			if ts > cutoff {
				// newer tasks; stop scanning further for this status
				break
			}
			id := binary.BigEndian.Uint64(key[len(key)-8:])
			deleteIDs = append(deleteIDs, id)
		}
		iter.Close()

		for _, id := range deleteIDs {
			// load task to get creator for event
			task, getErr := k.GetTask(ctx, id)
			if getErr != nil {
				k.Logger.Error("failed to load task before purge", "task_id", id, "error", getErr)
				// proceed with best-effort deletion
				if err := k.RemoveTask(ctx, id); err != nil {
					k.Logger.Error("failed to remove old task", "task_id", id, "error", err)
				}
				continue
			}

			if err := k.RemoveTask(ctx, id); err != nil {
				k.Logger.Error("failed to remove old task", "task_id", id, "error", err)
				continue
			}

			k.Logger.Info("old task deleted", "task_id", id, "status", status)
			// Emit purge event
			sdkCtx := sdk.UnwrapSDKContext(ctx)
			if emitErr := sdkCtx.EventManager().EmitTypedEvent(
				&crontasktypes.EventTaskPurged{
					TaskId:  id,
					Status:  status,
					Creator: task.Creator,
				},
			); emitErr != nil {
				k.Logger.Error("failed to emit task purged event", "task_id", id, "error", emitErr)
			}
		}
	}

	return nil
}

func (k Keeper) EndBlocker(ctx context.Context) error {
	return nil
}
