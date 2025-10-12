package keeper

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"

	"cosmossdk.io/collections"
	"cosmossdk.io/collections/indexes"
	"cosmossdk.io/core/store"
	errorsmod "cosmossdk.io/errors"
	"cosmossdk.io/log"
	sdkmath "cosmossdk.io/math"
	storetypes "cosmossdk.io/store/types"
	abci "github.com/cometbft/cometbft/abci/types"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/runtime"
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

// SubscriptionIndexes defines secondary indexes for subscriptions.
// - ByStatus: maps status string -> subscription_id (multi)
// - ByCreator: maps creator address string -> subscription_id (multi)
type SubscriptionIndexes struct {
	ByStatus  *indexes.Multi[string, uint64, crontasktypes.Subscription]
	ByCreator *indexes.Multi[string, uint64, crontasktypes.Subscription]
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

// GetNextTaskID gets and increments the global task ID counter
func (k Keeper) GetNextTaskID(ctx context.Context) (uint64, error) {
	return k.NextTaskID.Next(ctx)
}

// minifyJSONArray validates that the input is a JSON array and returns a compact representation
func minifyJSONArray(raw string) (string, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "[]", nil
	}
	var v []any
	if err := json.Unmarshal([]byte(trimmed), &v); err != nil {
		return "", errorsmod.Wrapf(err, "invalid JSON array")
	}
	b, err := marshalDeterministic(v)
	if err != nil {
		return "", errorsmod.Wrapf(err, "failed to encode JSON array")
	}
	return string(b), nil
}

// minifyJSONObject validates that the input is a JSON object and returns a compact representation
func minifyJSONObject(raw string) (string, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "{}", nil
	}
	var v map[string]any
	if err := json.Unmarshal([]byte(trimmed), &v); err != nil {
		return "", errorsmod.Wrapf(err, "invalid JSON object")
	}
	b, err := marshalDeterministic(v)
	if err != nil {
		return "", errorsmod.Wrapf(err, "failed to encode JSON object")
	}
	return string(b), nil
}

// marshalDeterministic encodes JSON with lexicographically-sorted object keys for deterministic bytes.
func marshalDeterministic(v any) ([]byte, error) {
	switch vv := v.(type) {
	case map[string]any:
		keys := make([]string, 0, len(vv))
		for k := range vv {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		buf := bytes.NewBuffer(make([]byte, 0, 256))
		buf.WriteByte('{')
		for i, k := range keys {
			kb, _ := json.Marshal(k)
			buf.Write(kb)
			buf.WriteByte(':')
			vb, err := marshalDeterministic(vv[k])
			if err != nil {
				return nil, err
			}
			buf.Write(vb)
			if i < len(keys)-1 {
				buf.WriteByte(',')
			}
		}
		buf.WriteByte('}')
		return buf.Bytes(), nil
	case []any:
		buf := bytes.NewBuffer(make([]byte, 0, 256))
		buf.WriteByte('[')
		for i, el := range vv {
			eb, err := marshalDeterministic(el)
			if err != nil {
				return nil, err
			}
			buf.Write(eb)
			if i < len(vv)-1 {
				buf.WriteByte(',')
			}
		}
		buf.WriteByte(']')
		return buf.Bytes(), nil
	default:
		return json.Marshal(v)
	}
}

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
		k.removeIndexes(ctx, prev)
	} else if !errors.Is(err, collections.ErrNotFound) {
		// Any other error (e.g. I/O problems) should be reported upstream.
		return err
	}

	// Write the new / updated task and create its secondary-index keys.
	if err := k.Tasks.Set(ctx, task.TaskId, task); err != nil {
		return err
	}

	k.addIndexes(ctx, task)
	return nil
}

// GetTask gets a task by ID
func (k Keeper) GetTask(ctx context.Context, id uint64) (crontasktypes.Task, error) {
	return k.Tasks.Get(ctx, id)
}

// DeleteTask deletes a task from the store
func (k Keeper) RemoveTask(ctx context.Context, id uint64) error {
	// Load the task first so we can clean up its secondary indexes. If the task
	// does not exist we simply propagate the original collections.ErrNotFound
	// so the caller can decide how to handle it.
	task, err := k.Tasks.Get(ctx, id)
	if err != nil {
		return err
	}

	// Delete secondary-index keys (address, status+timestamp, status+gasPrice)
	k.removeIndexes(ctx, task)

	// Finally remove the primary record from the `Tasks` map.
	return k.Tasks.Remove(ctx, id)
}

// SetParams sets the crontask module parameters
func (k Keeper) SetParams(ctx context.Context, params crontasktypes.Params) error {

	// Validate parameters before attempting to set them
	if err := params.Validate(); err != nil {
		k.Logger.Error("SetParams validation error", "error", err)
		return fmt.Errorf("invalid parameters: %w", err)
	}

	err := k.Params.Set(ctx, params)
	if err != nil {
		k.Logger.Error("SetParams error when setting params", "error", err)
		return err
	}

	return nil
}

// GetParams gets the crontask module parameters
func (k Keeper) GetParams(ctx context.Context) crontasktypes.Params {
	params, err := k.Params.Get(ctx)
	if err != nil {
		if errors.Is(err, collections.ErrNotFound) {
			k.Logger.Error("GetParams: params not found; returning defaults")
			return crontasktypes.DefaultParams()
		}
		k.Logger.Error("GetParams: failed to load params; returning defaults", "err", err)
		return crontasktypes.DefaultParams()
	}
	return params
}

// GetModuleParams returns the current module parameters
func (k Keeper) GetModuleParams(ctx context.Context) crontasktypes.Params {
	return crontasktypes.Params{
		BlockGasLimit:    k.config.BlockGasLimit,
		ExpiryLimit:      k.config.ExpiryLimit,
		MaxScheduledTime: k.config.MaxScheduledTime,
	}
}

// GetMetrics returns the current metrics singleton. If not set, returns zero-value metrics.
func (k Keeper) GetMetrics(ctx context.Context) (crontasktypes.Metrics, error) {
	metrics, err := k.Metrics.Get(ctx)
	if err != nil {
		if errors.Is(err, collections.ErrNotFound) {
			return crontasktypes.Metrics{}, nil
		}
		return crontasktypes.Metrics{}, err
	}
	return metrics, nil
}

// SetMetrics persists the metrics singleton.
func (k Keeper) SetMetrics(ctx context.Context, m crontasktypes.Metrics) error {
	return k.Metrics.Set(ctx, m)
}

// AddMetricsForTask updates the metrics singleton with one executed task's data.
func (k Keeper) AddMetricsForTask(ctx context.Context, t crontasktypes.Task) error {
	metrics, err := k.GetMetrics(ctx)
	if err != nil {
		return err
	}

	// total gas
	metrics.ExecutedTotalGas += t.TaskGasConsumed

	// accumulate fees using sdk.Coins helpers
	metrics.ExecutedTotalFees = sdk.Coins(metrics.ExecutedTotalFees).Add(t.TaskGasFee)

	// counts
	metrics.ExecutedTaskCount += 1

	return k.SetMetrics(ctx, metrics)
}

// bigEndian encodes uint64 big-endian
func bigEndian(u uint64) []byte {
	var b [8]byte
	binary.BigEndian.PutUint64(b[:], u)
	return b[:]
}

// addIndexes writes secondary-index entries for a task
func (k Keeper) addIndexes(ctx context.Context, t crontasktypes.Task) {
	store := k.storeService.OpenKVStore(ctx)

	// address index: prefix | creator | id
	keyAddr := append(append(indexAddrPrefix, []byte(t.Creator)...), bigEndian(t.TaskId)...)
	_ = store.Set(keyAddr, []byte{})

	// status+timestamp index
	// For SCHEDULED use scheduled time; for PENDING use creation time; for terminal statuses use execution/expiry
	var tsForIndex uint64
	switch t.Status {
	case crontasktypes.TaskStatus_SCHEDULED:
		tsForIndex = uint64(t.ScheduledTimestamp)
	case crontasktypes.TaskStatus_PENDING:
		tsForIndex = uint64(t.CreationTime)
	case crontasktypes.TaskStatus_DONE, crontasktypes.TaskStatus_FAILED:
		tsForIndex = uint64(t.ExecutionTimestamp)
	case crontasktypes.TaskStatus_EXPIRED:
		tsForIndex = uint64(t.ExpiryTimestamp)
	default:
		// fallback to creation time
		tsForIndex = uint64(t.CreationTime)
	}
	tsKey := append(indexStatusTsPrefix, []byte(t.Status)...)
	tsKey = append(tsKey, bigEndian(tsForIndex)...)
	tsKey = append(tsKey, bigEndian(t.TaskId)...)
	_ = store.Set(tsKey, []byte{})

	// status+gasPrice index: use scaled decimal gas price to preserve ordering
	scaled := t.TaskGasPrice.Amount.MulInt64(1_000_000_000_000).TruncateInt()
	var scaledU64 uint64
	if scaled.IsUint64() {
		scaledU64 = scaled.Uint64()
	} else {
		// Cap to max uint64 if it overflows; preserves monotonic ordering
		scaledU64 = ^uint64(0)
	}
	gpKey := append(indexStatusGasPrefix, []byte(t.Status)...)
	gpKey = append(gpKey, bigEndian(scaledU64)...)
	gpKey = append(gpKey, bigEndian(t.TaskId)...)
	_ = store.Set(gpKey, []byte{})
}

// removeIndexes deletes secondary-index entries for a task
func (k Keeper) removeIndexes(ctx context.Context, t crontasktypes.Task) {
	store := k.storeService.OpenKVStore(ctx)

	keyAddr := append(append(indexAddrPrefix, []byte(t.Creator)...), bigEndian(t.TaskId)...)
	_ = store.Delete(keyAddr)

	// status+timestamp index uses same timestamp selection logic as addIndexes
	var tsForIndex uint64
	switch t.Status {
	case crontasktypes.TaskStatus_SCHEDULED:
		tsForIndex = uint64(t.ScheduledTimestamp)
	case crontasktypes.TaskStatus_PENDING:
		tsForIndex = uint64(t.CreationTime)
	case crontasktypes.TaskStatus_DONE, crontasktypes.TaskStatus_FAILED:
		tsForIndex = uint64(t.ExecutionTimestamp)
	case crontasktypes.TaskStatus_EXPIRED:
		tsForIndex = uint64(t.ExpiryTimestamp)
	default:
		tsForIndex = uint64(t.CreationTime)
	}
	tsKey := append(indexStatusTsPrefix, []byte(t.Status)...)
	tsKey = append(tsKey, bigEndian(tsForIndex)...)
	tsKey = append(tsKey, bigEndian(t.TaskId)...)
	_ = store.Delete(tsKey)

	// Recompute scaled gas price key used for insertion to delete it
	scaled := t.TaskGasPrice.Amount.MulInt64(1_000_000_000_000).TruncateInt()
	var scaledU64 uint64
	if scaled.IsUint64() {
		scaledU64 = scaled.Uint64()
	} else {
		scaledU64 = ^uint64(0)
	}
	gpKey := append(indexStatusGasPrefix, []byte(t.Status)...)
	gpKey = append(gpKey, bigEndian(scaledU64)...)
	gpKey = append(gpKey, bigEndian(t.TaskId)...)
	_ = store.Delete(gpKey)
}

// Subscriptions are stored in an IndexedMap; secondary indexes are maintained automatically.

// kvStore returns module store adapter for iterator utils
func (k Keeper) kvStore(ctx context.Context) storetypes.KVStore {
	return runtime.KVStoreAdapter(k.storeService.OpenKVStore(ctx))
}

// iterateStatusTimestamp returns iterator over keys for given status, ordered asc/desc
func (k Keeper) iterateStatusTimestamp(ctx context.Context, status string, reverse bool) storetypes.Iterator {
	store := k.kvStore(ctx)
	prefix := append(indexStatusTsPrefix, []byte(status)...)
	if reverse {
		return storetypes.KVStoreReversePrefixIterator(store, prefix)
	}
	return storetypes.KVStorePrefixIterator(store, prefix)
}

// iterateStatusGas returns iterator over status+gasPrice index
func (k Keeper) iterateStatusGas(ctx context.Context, status string, reverse bool) storetypes.Iterator {
	store := k.kvStore(ctx)
	prefix := append(indexStatusGasPrefix, []byte(status)...)
	if reverse {
		return storetypes.KVStoreReversePrefixIterator(store, prefix)
	}
	return storetypes.KVStorePrefixIterator(store, prefix)
}

// iterateAddress returns iterator over address index
func (k Keeper) iterateAddress(ctx context.Context, addr string) storetypes.Iterator {
	store := k.kvStore(ctx)
	prefix := append(indexAddrPrefix, []byte(addr)...)
	return storetypes.KVStorePrefixIterator(store, prefix)
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

		// Preemptively expire subscriptions past their expiry_timestamp
		if sub.ExpiryTimestamp > 0 && sub.ExpiryTimestamp <= now {

			sub.Status = "expired"
			sub.StatusMessage = fmt.Sprintf("expired at [%d]", sub.ExpiryTimestamp)
			if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
				k.Logger.Error("failed to mark subscription expired", "id", id, "err", err)
			}
			continue
		}

		// Preemptively disable if creator lacks balance for fee
		creatorAddr, addrErr := sdk.AccAddressFromBech32(sub.Creator)
		if addrErr != nil {
			k.Logger.Error("invalid creator address in subscription; disabling", "id", id, "err", addrErr)

			sub.Status = "disabled"
			sub.StatusMessage = "invalid creator address"
			if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
				k.Logger.Error("failed to persist disabled subscription", "id", id, "err", err)
			}
			continue
		}
		if !k.bankKeeper.HasBalance(ctx, creatorAddr, sub.TaskGasFee) {
			k.Logger.Info("disabling subscription due to insufficient balance", "id", id)

			sub.Status = "disabled"
			sub.StatusMessage = fmt.Sprintf("insufficient funds for fee [%s]", sub.TaskGasFee.String())
			if err := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); err != nil {
				k.Logger.Error("failed to persist disabled subscription", "id", id, "err", err)
			}
			continue
		}

		// Apply subscription filter against array of normalized events; schedule for each match
		//k.Logger.Info("HandleBlockEvents", "sub.Filter", sub.Filter)
		res := gjson.GetBytes(jsonNormalized, sub.Filter)
		//k.Logger.Info("HandleBlockEvents", "res", res.String())
		if res.Exists() {
			var matches []gjson.Result
			if res.IsArray() {
				matches = res.Array()
			} else {
				matches = []gjson.Result{res}
			}
			for _, m := range matches {
				var matched map[string]any
				if err := json.Unmarshal([]byte(m.Raw), &matched); err != nil {
					k.Logger.Error("failed to unmarshal matched normalized event", "id", id, "err", err)
					continue
				}
				if err := k.createTaskForSubscriptionWithNormalized(ctx, sub, matched); err != nil {
					k.Logger.Error("failed to create task for subscription", "id", id, "err", err)
					// disable subscription on task creation failure

					sub.Status = "disabled"
					sub.StatusMessage = fmt.Sprintf("task creation error: %v", err)
					if setErr := k.Subscriptions.Set(ctx, sub.SubscriptionId, sub); setErr != nil {
						k.Logger.Error("failed to persist disabled subscription after task error", "id", id, "err", setErr)
					}
					break
				}
				sub.TriggerCount++
			}
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
