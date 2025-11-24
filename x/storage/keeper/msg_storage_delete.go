package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	storagetypes "dysonprotocol.com/x/storage/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// StorageDelete removes specified storage entries owned by the requesting account.
//
// Semantics:
//   - Deletes multiple storage entries by index for the specified owner.
//   - Verifies ownership of each entry before deletion to prevent unauthorized removal.
//   - Updates owner's storage metrics by subtracting deleted bytes from total.
//   - Returns list of successfully deleted indexes for transparency.
//   - Succeeds even if no entries were deleted (idempotent operation).
//
// Validation:
//   - Owner must be a valid bech32 address.
//   - At least one index must be specified for deletion.
//   - Each specified index must exist and be owned by the requesting account to be deleted.
//
// State Updates:
//   - Removes entries from StorageMap for each successfully deleted index.
//   - Updates StorageMetricsMap for the owner by reducing total byte count.
//
// Emits:
//   - EventStorageDelete(owner, deleted_indexes) with list of successfully deleted indexes.
//
// Returns:
//   - *storagetypes.MsgStorageDeleteResponse containing list of deleted_indexes.
//
// Errors are returned on invalid owner address, empty index list, ownership mismatches,
// or internal storage failures; no panics. Non-existent entries are silently skipped.
func (k Keeper) StorageDelete(ctx context.Context, msg *storagetypes.MsgStorageDelete) (*storagetypes.MsgStorageDeleteResponse, error) {
	// Validate the owner address is properly formatted
	if _, err := sdk.AccAddressFromBech32(msg.Owner); err != nil {
		return nil, err
	}

	// Validate that indexes are provided
	if len(msg.Indexes) == 0 {
		return nil, status.Errorf(codes.InvalidArgument, "must specify at least one index to delete")
	}

	// Track the indexes that were deleted and total bytes deleted for metrics
	var deletedIndexes []string
	var totalBytesDeleted uint64

	// Delete specific indexes
	for _, index := range msg.Indexes {
		// Create the key for this index
		key := msg.Owner + "/" + index

		// Check if the entry exists first
		exists, err := k.StorageMap.Has(ctx, key)
		if err != nil {
			return nil, err
		}

		// Only try to delete if it exists AND belongs to the requesting user
		if exists {
			// Double-check ownership by reading the entry
			entry, err := k.StorageMap.Get(ctx, key)
			if err != nil {
				return nil, err
			}

			// Verify the entry owner matches the message sender
			if entry.Owner != msg.Owner {
				return nil, status.Errorf(codes.PermissionDenied, "cannot delete index [%s] owned by [%s]", index, entry.Owner)
			}

			// Track bytes for metrics before deletion
			totalBytesDeleted += uint64(len(entry.Data))

			if err := k.StorageMap.Remove(ctx, key); err != nil {
				return nil, err
			}
			deletedIndexes = append(deletedIndexes, index)
		}
	}

	// Update metrics after successful deletion
	if totalBytesDeleted > 0 {
		metricsDelta := -int64(totalBytesDeleted) // Negative because we're removing bytes
		if err := k.UpdateStorageMetrics(ctx, msg.Owner, metricsDelta); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to update storage metrics")
		}
	}

	// Emit the StorageDelete event
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	event := storagetypes.EventStorageDelete{
		Owner:          msg.Owner,
		DeletedIndexes: deletedIndexes,
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&event); err != nil {
		return nil, err
	}
	return &storagetypes.MsgStorageDeleteResponse{
		DeletedIndexes: deletedIndexes,
	}, nil
}

