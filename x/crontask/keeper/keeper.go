package keeper

import (
	"encoding/json"
	"fmt"

	"cosmossdk.io/collections"
	"cosmossdk.io/collections/indexes"
	"cosmossdk.io/core/store"
	errorsmod "cosmossdk.io/errors"
	"cosmossdk.io/log"
	sdkmath "cosmossdk.io/math"
	abci "github.com/cometbft/cometbft/abci/types"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/tidwall/gjson"

	"dysonprotocol.com/x/crontask"
	eventnorm "dysonprotocol.com/x/crontask/keeper/eventnormalizer"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	scripttypes "dysonprotocol.com/x/script/types"
)

var (
	// TasksKey is the prefix for the tasks collection
	TasksKey = collections.NewPrefix(0)

	// NextTaskIDKey is the key for the next task ID
	NextTaskIDKey = collections.NewPrefix(1)

	// ParamsKey is the prefix for the module parameters
	ParamsKey = collections.NewPrefix(2)

	// Task index prefixes
	TasksByAddressPrefix         = collections.NewPrefix(3)
	TasksByStatusTimestampPrefix = collections.NewPrefix(4)
	TasksByStatusGasPricePrefix  = collections.NewPrefix(5)

	// MetricsKey is the key for the metrics singleton
	MetricsKey = collections.NewPrefix(6)

	// Subscriptions map and sequence prefixes
	SubscriptionsKey      = collections.NewPrefix(7)
	NextSubscriptionIDKey = collections.NewPrefix(8)

	// Collections indexes for subscriptions
	SubscriptionsByStatusPrefix  = collections.NewPrefix(9)
	SubscriptionsByCreatorPrefix = collections.NewPrefix(10)

	// Manual raw KV index prefixes (single-byte for simplicity)
	indexAddrPrefix      = []byte{0xA1}
	indexStatusTsPrefix  = []byte{0xA2}
	indexStatusGasPrefix = []byte{0xA3}
)

type Keeper struct {
	cdc           codec.Codec
	storeService  store.KVStoreService
	bankKeeper    crontasktypes.BankKeeper
	accountKeeper crontasktypes.AccountKeeper
	stakingKeeper crontasktypes.StakingKeeper
	config        crontask.Config
	authority     string // the address that is authorized to update module parameters

	// Services from the app's depinject setup
	MsgRouterService *baseapp.MsgServiceRouter
	Logger           log.Logger

	Schema collections.Schema

	// Tasks is the primary collection for tasks
	Tasks collections.Map[uint64, crontasktypes.Task]

	// NextTaskID is a sequence for task IDs
	NextTaskID collections.Sequence

	// Params stores module parameters
	Params collections.Item[crontasktypes.Params]

	// Metrics stores the aggregate metrics singleton
	Metrics collections.Item[crontasktypes.Metrics]

	// Subscriptions is the primary collection for event subscriptions (indexed)
	Subscriptions *collections.IndexedMap[uint64, crontasktypes.Subscription, SubscriptionIndexes]
	// NextSubscriptionID sequence
	NextSubscriptionID collections.Sequence
}

// NewKeeper creates a new crontask Keeper instance
func NewKeeper(
	cdc codec.Codec,
	storeService store.KVStoreService,
	accountKeeper crontasktypes.AccountKeeper,
	bankKeeper crontasktypes.BankKeeper,
	stakingKeeper crontasktypes.StakingKeeper,
	msgRouter *baseapp.MsgServiceRouter,
	config crontask.Config,
	authority string,
	logger log.Logger,
) Keeper {
	// Add the module name to the logger
	logger = logger.With(log.ModuleKey, "x/"+crontask.ModuleName)

	sb := collections.NewSchemaBuilder(storeService)

	// plain tasks map
	tasks := collections.NewMap(
		sb,
		TasksKey,
		"tasks",
		collections.Uint64Key,
		codec.CollValue[crontasktypes.Task](cdc),
	)

	nextTaskID := collections.NewSequence(
		sb,
		NextTaskIDKey,
		"next_task_id",
	)

	// Create a Item params item for parameters storage
	params := collections.NewItem(
		sb,
		ParamsKey,
		"params",
		codec.CollValue[crontasktypes.Params](cdc),
	)

	// Create metrics singleton item
	metrics := collections.NewItem(
		sb,
		MetricsKey,
		"metrics",
		codec.CollValue[crontasktypes.Metrics](cdc),
	)

	// Subscriptions indexed map
	subIdx := SubscriptionIndexes{
		ByStatus: indexes.NewMulti(
			sb,
			SubscriptionsByStatusPrefix,
			"subscriptions_by_status",
			collections.StringKey, // status
			collections.Uint64Key, // subscription_id
			func(_ uint64, v crontasktypes.Subscription) (string, error) { return v.Status, nil },
		),
		ByCreator: indexes.NewMulti(
			sb,
			SubscriptionsByCreatorPrefix,
			"subscriptions_by_creator",
			collections.StringKey, // creator address string
			collections.Uint64Key, // subscription_id
			func(_ uint64, v crontasktypes.Subscription) (string, error) { return v.Creator, nil },
		),
	}

	subscriptions := collections.NewIndexedMap(
		sb,
		SubscriptionsKey,
		"subscriptions",
		collections.Uint64Key,
		codec.CollValue[crontasktypes.Subscription](cdc),
		subIdx,
	)

	// Next subscription id
	nextSubID := collections.NewSequence(
		sb,
		NextSubscriptionIDKey,
		"next_subscription_id",
	)

	schema, err := sb.Build()
	if err != nil {
		panic(err)
	}

	keeper := Keeper{
		cdc:                cdc,
		storeService:       storeService,
		bankKeeper:         bankKeeper,
		accountKeeper:      accountKeeper,
		stakingKeeper:      stakingKeeper,
		config:             config,
		authority:          authority,
		Tasks:              tasks,
		NextTaskID:         nextTaskID,
		Params:             params,
		Metrics:            metrics,
		Subscriptions:      subscriptions,
		NextSubscriptionID: nextSubID,
		Schema:             schema,
		Logger:             logger,
		MsgRouterService:   msgRouter,
	}

	// Add debug logging about keeper initialization
	logger.Debug("Crontask keeper initialized",
		"msg_router_service_set", keeper.MsgRouterService != nil,
		"bank_keeper_set", keeper.bankKeeper != nil,
		"account_keeper_set", keeper.accountKeeper != nil)

	return keeper
}

// HandleBlockEvents receives all block events (begin, txs, end) as a flat list
func (k Keeper) HandleBlockEvents(ctx sdk.Context, allEvents []abci.Event) {
	if len(allEvents) == 0 {
		return
	}

	now := ctx.BlockTime().Unix()

	// Build normalizedBlockEvents once and JSON-encode for GJSON filtering
	normalizedBlockEvents := make([]map[string]any, 0, len(allEvents))
	for _, ev := range allEvents {
		attrs := make([]eventnorm.Attribute, 0, len(ev.Attributes))
		for _, a := range ev.Attributes {
			attrs = append(attrs, eventnorm.Attribute{Key: a.Key, Value: a.Value, Index: a.Index})
		}
		ne := eventnorm.NormalizeEvent(eventnorm.Event{Type: ev.Type, Attributes: attrs})
		normalizedBlockEvents = append(normalizedBlockEvents, map[string]any{
			"type":       ne.Type,
			"attributes": ne.Attributes,
		})
	}
	jsonNormalized, err := marshalDeterministic(normalizedBlockEvents)
	if err != nil {
		k.Logger.Error("failed to marshal normalized block events", "err", err)
		return
	}
	//k.Logger.Info("HandleBlockEvents", "jsonNormalized", string(jsonNormalized))

	// Iterate enabled subscriptions via ByStatus index
	it, err := k.Subscriptions.Indexes.ByStatus.MatchExact(ctx, "enabled")
	if err != nil {
		k.Logger.Error("failed to open ByStatus index iterator", "status", "enabled", "err", err)
		return
	}
	defer func() { _ = it.Close() }()
	for ; it.Valid(); it.Next() {
		id, pkErr := it.PrimaryKey()
		if pkErr != nil {
			k.Logger.Error("failed to read subscription primary key", "err", pkErr)
			continue
		}
		sub, err := k.Subscriptions.Get(ctx, id)
		if err != nil {
			k.Logger.Error("failed to load subscription from primary map", "id", id, "err", err)
			continue
		}

		// Disable subscriptions past their expiry_timestamp (recoverable via RenewSubscription)
		if sub.ExpiryTimestamp > 0 && sub.ExpiryTimestamp <= now {
			sub.Status = "disabled"
			sub.StatusMessage = fmt.Sprintf("expired at [%d]", sub.ExpiryTimestamp)
			if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
				k.Logger.Error("failed to mark subscription disabled (expired)", "id", id, "err", err)
			}
			continue
		}

		// Mark as error if creator address is invalid (unrecoverable - data corruption)
		creatorAddr, addrErr := sdk.AccAddressFromBech32(sub.Creator)
		if addrErr != nil {
			k.Logger.Error("invalid creator address in subscription; marking as error", "id", id, "err", addrErr)
			sub.Status = "error"
			sub.StatusMessage = "invalid creator address"
			if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
				k.Logger.Error("failed to persist error subscription", "id", id, "err", err)
			}
			continue
		}
		// Apply subscription filter against array of normalized events; schedule for each match
		res := gjson.GetBytes(jsonNormalized, sub.Filter)
		if !res.Exists() {
			continue
		}

		var matches []gjson.Result
		if res.IsArray() {
			matches = res.Array()
		} else {
			matches = []gjson.Result{res}
		}

		if len(matches) == 0 {
			continue
		}

		// Check balance upfront for ALL matches - require full coverage or disable (recoverable via RenewSubscription)
		totalRequired := sub.TaskGasFee.Amount.MulRaw(int64(len(matches)))
		balance := k.bankKeeper.GetBalance(ctx, creatorAddr, sub.TaskGasFee.Denom)
		if balance.Amount.LT(totalRequired) {
			k.Logger.Info("disabling subscription due to insufficient balance for all triggers",
				"id", id,
				"matches", len(matches),
				"required", sdk.NewCoin(sub.TaskGasFee.Denom, totalRequired).String(),
				"balance", balance.String())
			sub.Status = "disabled"
			sub.StatusMessage = fmt.Sprintf("insufficient funds: need %s for %d triggers, have %s",
				sdk.NewCoin(sub.TaskGasFee.Denom, totalRequired).String(),
				len(matches),
				balance.String())
			if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
				k.Logger.Error("failed to persist disabled subscription", "id", id, "err", err)
			}
			continue
		}

		// Process matches
		for _, m := range matches {
			var matched map[string]any
			if err := json.Unmarshal([]byte(m.Raw), &matched); err != nil {
				k.Logger.Error("failed to unmarshal matched normalized event", "id", id, "err", err)
				continue
			}
			if err := k.createTaskForSubscriptionWithNormalized(ctx, sub, matched); err != nil {
				k.Logger.Error("failed to create task for subscription", "id", id, "err", err)
				// Mark as error on task creation failure (unrecoverable - likely config issue).
				// The outer persist at the end of the loop will save this status.
				sub.Status = "error"
				sub.StatusMessage = fmt.Sprintf("task creation error: %v", err)
				break
			}
			// Only increment after successful task creation
			sub.TriggerCount++
		}

		// persist updates
		if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
			k.Logger.Error("failed to persist subscription update", "id", id, "err", err)
		}
	}
}

// deprecated single-event filter helper removed; block-level filtering is used instead

// createTaskForSubscription creates a scheduled crontask for the event
func (k Keeper) createTaskForSubscription(ctx sdk.Context, sub crontasktypes.Subscription, ev abci.Event) error {
	// Charge per-trigger fee to fee_collector
	fee := sdk.NewCoins(sub.TaskGasFee)
	creatorAddr, err := sdk.AccAddressFromBech32(sub.Creator)
	if err != nil {
		return err
	}
	if err := k.bankKeeper.SendCoinsFromAccountToModule(ctx, creatorAddr, "fee_collector", fee); err != nil {
		return errorsmod.Wrapf(err, "fee deduction failed for creator [%s]", sub.Creator)
	}

	// Normalize event and merge into kwargs under key "event" using eventnormalizer
	attrsIn := make([]eventnorm.Attribute, 0, len(ev.Attributes))
	for _, a := range ev.Attributes {
		attrsIn = append(attrsIn, eventnorm.Attribute{Key: a.Key, Value: a.Value, Index: a.Index})
	}
	normalizedEvent := eventnorm.NormalizeEvent(eventnorm.Event{Type: ev.Type, Attributes: attrsIn})

	var kwargsMap map[string]any
	if len(sub.Kwargs) > 0 {
		if err := json.Unmarshal([]byte(sub.Kwargs), &kwargsMap); err != nil {
			return errorsmod.Wrapf(err, "invalid kwargs JSON for subscription [%d]", sub.SubscriptionId)
		}
	} else {
		kwargsMap = make(map[string]any)
	}
	kwargsMap["event"] = normalizedEvent
	mergedKwargsBytes, err := marshalDeterministic(kwargsMap)
	if err != nil {
		return errorsmod.Wrapf(err, "failed to encode merged kwargs for subscription [%d]", sub.SubscriptionId)
	}

	// Build script MsgExec Any
	exec := &scripttypes.MsgExec{
		ExecutorAddress: sub.Creator,
		ScriptAddress:   sub.ScriptAddress,
		FunctionName:    sub.Function,
		Args:            sub.Args,
		Kwargs:          string(mergedKwargsBytes),
	}
	anyExec, err := cdctypes.NewAnyWithValue(exec)
	if err != nil {
		return err
	}

	// Create Task
	now := ctx.BlockTime().Unix()
	scheduled := now
	if sub.TaskScheduledTimestamp > 0 {
		scheduled = sub.TaskScheduledTimestamp
	}
	expiry := scheduled + k.config.ExpiryLimit
	if sub.TaskExpiryTimestamp > 0 {
		expiry = sub.TaskExpiryTimestamp
	}
	taskID, err := k.GetNextTaskID(ctx)
	if err != nil {
		return err
	}
	task := crontasktypes.Task{
		TaskId:              taskID,
		Creator:             sub.Creator,
		ScheduledTimestamp:  scheduled,
		ExpiryTimestamp:     expiry,
		TaskGasLimit:        sub.TaskGasLimit,
		TaskGasFee:          sub.TaskGasFee,
		TaskGasPrice:        sdk.NewDecCoinFromDec(sub.TaskGasFee.Denom, sdkmath.LegacyNewDecFromInt(sub.TaskGasFee.Amount).QuoInt64(int64(sub.TaskGasLimit))),
		Msgs:                []*cdctypes.Any{anyExec},
		Status:              crontasktypes.TaskStatus_SCHEDULED,
		CreationTime:        now,
		CreationBlockHeight: ctx.BlockHeight(),
	}
	if sub.TaskGasPrice.Denom != "" {
		task.TaskGasPrice = sub.TaskGasPrice
	}
	if err := k.SetTask(ctx, task); err != nil {
		return err
	}
	// emit triggered event
	if err := ctx.EventManager().EmitTypedEvent(&crontasktypes.EventSubscriptionTriggered{SubscriptionId: sub.SubscriptionId, Creator: sub.Creator}); err != nil {
		return errorsmod.Wrap(err, "failed to emit subscription triggered event")
	}
	return nil
}

// createTaskForSubscriptionWithNormalized creates a scheduled crontask using a pre-normalized event map
func (k Keeper) createTaskForSubscriptionWithNormalized(ctx sdk.Context, sub crontasktypes.Subscription, normalized map[string]any) error {
	// Charge per-trigger fee to fee_collector
	fee := sdk.NewCoins(sub.TaskGasFee)
	creatorAddr, err := sdk.AccAddressFromBech32(sub.Creator)
	if err != nil {
		return err
	}
	if err := k.bankKeeper.SendCoinsFromAccountToModule(ctx, creatorAddr, "fee_collector", fee); err != nil {
		return errorsmod.Wrapf(err, "fee deduction failed for creator [%s]", sub.Creator)
	}

	// Merge normalized event into kwargs under key "event"
	var kwargsMap map[string]any
	if len(sub.Kwargs) > 0 {
		if err := json.Unmarshal([]byte(sub.Kwargs), &kwargsMap); err != nil {
			return errorsmod.Wrapf(err, "invalid kwargs JSON for subscription [%d]", sub.SubscriptionId)
		}
	} else {
		kwargsMap = make(map[string]any)
	}
	kwargsMap["event"] = normalized
	mergedKwargsBytes, err := marshalDeterministic(kwargsMap)
	if err != nil {
		return errorsmod.Wrapf(err, "failed to encode merged kwargs for subscription [%d]", sub.SubscriptionId)
	}

	// Build script MsgExec Any
	exec := &scripttypes.MsgExec{
		ExecutorAddress: sub.Creator,
		ScriptAddress:   sub.ScriptAddress,
		FunctionName:    sub.Function,
		Args:            sub.Args,
		Kwargs:          string(mergedKwargsBytes),
	}
	anyExec, err := cdctypes.NewAnyWithValue(exec)
	if err != nil {
		return err
	}

	// Create Task
	now := ctx.BlockTime().Unix()
	scheduled := now
	if sub.TaskScheduledTimestamp > 0 {
		scheduled = sub.TaskScheduledTimestamp
	}
	expiry := scheduled + k.config.ExpiryLimit
	if sub.TaskExpiryTimestamp > 0 {
		expiry = sub.TaskExpiryTimestamp
	}
	taskID, err := k.GetNextTaskID(ctx)
	if err != nil {
		return err
	}
	task := crontasktypes.Task{
		TaskId:              taskID,
		Creator:             sub.Creator,
		ScheduledTimestamp:  scheduled,
		ExpiryTimestamp:     expiry,
		TaskGasLimit:        sub.TaskGasLimit,
		TaskGasFee:          sub.TaskGasFee,
		TaskGasPrice:        sdk.NewDecCoinFromDec(sub.TaskGasFee.Denom, sdkmath.LegacyNewDecFromInt(sub.TaskGasFee.Amount).QuoInt64(int64(sub.TaskGasLimit))),
		Msgs:                []*cdctypes.Any{anyExec},
		Status:              crontasktypes.TaskStatus_SCHEDULED,
		CreationTime:        now,
		CreationBlockHeight: ctx.BlockHeight(),
	}
	if sub.TaskGasPrice.Denom != "" {
		task.TaskGasPrice = sub.TaskGasPrice
	}
	if err := k.SetTask(ctx, task); err != nil {
		return err
	}
	// emit triggered event
	if err := ctx.EventManager().EmitTypedEvent(&crontasktypes.EventSubscriptionTriggered{SubscriptionId: sub.SubscriptionId, Creator: sub.Creator}); err != nil {
		return errorsmod.Wrap(err, "failed to emit subscription triggered event")
	}
	return nil
}
