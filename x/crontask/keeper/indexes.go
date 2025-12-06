package keeper

import (
	"context"
	"encoding/binary"
	"fmt"

	"cosmossdk.io/collections/indexes"
	storetypes "cosmossdk.io/store/types"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	"github.com/cosmos/cosmos-sdk/runtime"
)

// RebuildIndexes iterates primary data to rebuild raw KV secondary indexes for tasks.
// Subscriptions use collections.IndexedMap and do not need manual rebuild.
func (k Keeper) RebuildIndexes(ctx context.Context) error {
	// Clear and rebuild per-task raw KV indexes by walking all tasks
	// Note: deletion of all possible old index keys is expensive; instead we remove per-task entries using current values
	// This is sufficient on a fresh import as the KV store is empty before writes.
	// If running in-place, callers should clear old prefixes beforehand if needed.
	if err := k.Tasks.Walk(ctx, nil, func(_ uint64, task crontasktypes.Task) (bool, error) {
		// Ensure indexes exist for current task state
		if err := k.addIndexes(ctx, task); err != nil {
			return true, err
		}
		return false, nil
	}); err != nil {
		return err
	}
	return nil
}

// SubscriptionIndexes defines secondary indexes for subscriptions.
// - ByStatus: maps status string -> subscription_id (multi)
// - ByCreator: maps creator address string -> subscription_id (multi)
type SubscriptionIndexes struct {
	ByStatus  *indexes.Multi[string, uint64, crontasktypes.Subscription]
	ByCreator *indexes.Multi[string, uint64, crontasktypes.Subscription]
}

// bigEndian encodes uint64 big-endian
func bigEndian(u uint64) []byte {
	var b [8]byte
	binary.BigEndian.PutUint64(b[:], u)
	return b[:]
}

// addIndexes writes secondary-index entries for a task.
// Returns an error if any index write fails.
func (k Keeper) addIndexes(ctx context.Context, t crontasktypes.Task) error {
	store := k.storeService.OpenKVStore(ctx)

	// address index: prefix | creator | id
	keyAddr := append(append(indexAddrPrefix, []byte(t.Creator)...), bigEndian(t.TaskId)...)
	if err := store.Set(keyAddr, []byte{}); err != nil {
		return fmt.Errorf("failed to set address index for task %d: %w", t.TaskId, err)
	}

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
	if err := store.Set(tsKey, []byte{}); err != nil {
		return fmt.Errorf("failed to set status+timestamp index for task %d: %w", t.TaskId, err)
	}

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
	if err := store.Set(gpKey, []byte{}); err != nil {
		return fmt.Errorf("failed to set status+gas price index for task %d: %w", t.TaskId, err)
	}

	return nil
}

// removeIndexes deletes secondary-index entries for a task.
// Returns an error if any index delete fails.
func (k Keeper) removeIndexes(ctx context.Context, t crontasktypes.Task) error {
	store := k.storeService.OpenKVStore(ctx)

	keyAddr := append(append(indexAddrPrefix, []byte(t.Creator)...), bigEndian(t.TaskId)...)
	if err := store.Delete(keyAddr); err != nil {
		return fmt.Errorf("failed to delete address index for task %d: %w", t.TaskId, err)
	}

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
	if err := store.Delete(tsKey); err != nil {
		return fmt.Errorf("failed to delete status+timestamp index for task %d: %w", t.TaskId, err)
	}

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
	if err := store.Delete(gpKey); err != nil {
		return fmt.Errorf("failed to delete status+gas price index for task %d: %w", t.TaskId, err)
	}

	return nil
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
