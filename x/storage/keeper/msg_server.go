package keeper

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"time"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	"dysonprotocol.com/x/storage"
	storagetypes "dysonprotocol.com/x/storage/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// We assume your keeper implements storagetypes.MsgServer
var _ storagetypes.MsgServer = Keeper{}

func isPrintableASCII(s string) bool {
	for _, r := range s {
		if r < ' ' || r > '~' {
			return false
		}
	}
	return true
}

// StorageSet sets a storage entry for the specified owner and index.
//
// Semantics:
//   - Stores JSON data under a composite key of owner/index, creating or updating the entry.
//   - Validates data size against module's MaxStorageSize parameter.
//   - Enforces stake requirements when StorageStakeMultiple > 0: requires owner to have sufficient delegated stake.
//   - Calculates data hash using SHA256 and stores metadata including block height and timestamp.
//   - Updates owner's storage metrics (total bytes) for stake validation and monitoring.
//
// Validation:
//   - Owner must be a valid bech32 address.
//   - Index must be non-empty and contain only printable ASCII characters.
//   - Data size must not exceed MaxStorageSize parameter.
//   - When stake validation is enabled, owner's delegated stake must meet minimum requirement.
//
// State Updates:
//   - Creates or updates StorageMap entry with owner/index key containing data, hash, and metadata.
//   - Updates StorageMetricsMap for the owner with new total byte count.
//   - Recalculates and updates minimum stake requirement based on new total bytes.
//
// Emits:
//   - EventStorageUpdated(address, index) upon successful storage operation.
//
// Returns:
//   - *storagetypes.MsgStorageSetResponse with empty body on success.
//
// Errors are returned on invalid owner address, empty/malformed index, data size limits,
// insufficient stake for storage requirements, or internal storage failures; no panics.
func (k Keeper) StorageSet(ctx context.Context, msg *storagetypes.MsgStorageSet) (*storagetypes.MsgStorageSetResponse, error) {
	// Validate the owner address is properly formatted
	if _, err := sdk.AccAddressFromBech32(msg.Owner); err != nil {
		return nil, err
	}

	if msg.Index == "" {
		return nil, status.Errorf(codes.InvalidArgument, "index cannot be empty")
	}

	if !isPrintableASCII(msg.Index) {
		return nil, status.Errorf(codes.InvalidArgument, "Invalid index, must be printable ASCII")
	}

	// Get current parameters to check max storage size
	params := k.GetParams(ctx)
	dataSize := uint64(len(msg.Data))

	if dataSize > params.MaxStorageSize {
		return nil, status.Errorf(codes.InvalidArgument, "data size %d bytes exceeds maximum allowed size %d bytes", dataSize, params.MaxStorageSize)
	}

	// Create the combined key
	key := msg.Owner + "/" + msg.Index

	// Check if entry already exists to calculate metrics delta
	var oldDataSize uint64
	existingEntry, err := k.StorageMap.Get(ctx, key)
	if err == nil {
		// Entry exists, record old size for metrics calculation
		oldDataSize = uint64(len(existingEntry.Data))
	} else if !cosmossdkerrors.IsOf(err, collections.ErrNotFound) {
		// Real error, not just "not found"
		return nil, err
	}
	// If err is ErrNotFound, oldDataSize remains 0

	// Stake validation: check if owner has sufficient delegated stake
	// Only validate if storage_stake_multiple is not "0" (which disables validation)
	if params.StorageStakeMultiple != "0" {
		// Get current total bytes for this owner
		currentMetrics, err := k.GetStorageMetrics(ctx, msg.Owner)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to get current storage metrics for stake validation")
		}

		// Calculate what the new total bytes would be after this operation
		newTotalBytes := currentMetrics.TotalBytes - oldDataSize + dataSize

		// Calculate required stake for the new total
		requiredStakeStr, err := k.CalculateMinStakeAmount(ctx, newTotalBytes)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to calculate required stake amount")
		}

		// Get current delegated stake for the owner
		currentStake, err := k.GetTotalDelegatedStake(ctx, msg.Owner)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to get current delegated stake")
		}

		// Parse required stake as integer for comparison
		requiredStake, ok := math.NewIntFromString(requiredStakeStr)
		if !ok {
			return nil, cosmossdkerrors.Wrap(err, "failed to parse required stake amount")
		}

		// Check if current stake is sufficient
		if currentStake.LT(requiredStake) {
			return nil, storage.NewInsufficientStakeError(msg.Owner, currentStake, requiredStake, newTotalBytes)
		}
	}

	blockHeight := uint64(sdk.UnwrapSDKContext(ctx).BlockHeight())
	blockTime := sdk.UnwrapSDKContext(ctx).BlockTime()
	hashBytes := sha256.Sum256([]byte(msg.Data))
	hashB64 := base64.StdEncoding.EncodeToString(hashBytes[:])
	entry := storagetypes.Storage{
		Owner:            msg.Owner,
		Data:             msg.Data,
		Index:            msg.Index,
		UpdatedHeight:    blockHeight,
		UpdatedTimestamp: blockTime.UTC().Format(time.RFC3339),
		Hash:             fmt.Sprintf("sha256-%s", hashB64),
	}

	if err := k.StorageMap.Set(ctx, key, entry); err != nil {
		return nil, err
	}

	// Update metrics after successful storage operation
	metricsDelta := int64(dataSize) - int64(oldDataSize)
	if err := k.UpdateStorageMetrics(ctx, msg.Owner, metricsDelta); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update storage metrics")
	}

	// Emit the StorageUpdated event
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	event := storagetypes.EventStorageUpdated{
		Address: msg.Owner,
		Index:   msg.Index,
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&event); err != nil {
		return nil, err
	}

	return &storagetypes.MsgStorageSetResponse{}, nil
}

// StorageDelete removes specified storage entries owned by the requesting account.
//
// Semantics:
//   - Deletes multiple storage entries by index for the specified owner.
//   - Verifies ownership of each entry before deletion to prevent unauthorized removal.
//   - Updates owner's storage metrics by subtracting deleted bytes from total.
//   - Returns list of successfully deleted indexes for transparency.
//
// Validation:
//   - Owner must be a valid bech32 address.
//   - At least one index must be specified for deletion.
//   - Each specified index must exist and be owned by the requesting account.
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
// Errors are returned on invalid owner address, empty index list, non-existent entries,
// ownership mismatches, or internal storage failures; no panics.
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

	// Check if any entries were actually deleted
	if len(deletedIndexes) == 0 {
		return nil, status.Errorf(codes.NotFound, "no entries were deleted")
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

// UpdateParams updates the x/storage module parameters via governance proposal.
//
// Semantics:
//   - Validates that the signer has authority to update module parameters (typically governance module).
//   - Validates that all provided parameters are valid according to parameter constraints.
//   - Updates the module's parameter state with the new values.
//
// Validation:
//   - Authority must match the module's configured authority address.
//   - All parameter values must pass individual validation (MaxStorageSize, StorageStakeMultiple).
//
// State Updates:
//   - Updates the module's Params in state with the new parameter values.
//
// Emits:
//   - No events emitted for parameter updates.
//
// Returns:
//   - *storagetypes.MsgUpdateParamsResponse with empty body on success.
//
// Errors are returned on invalid authority, parameter validation failures, or state update failures; no panics.
func (k Keeper) UpdateParams(ctx context.Context, msg *storagetypes.MsgUpdateParams) (*storagetypes.MsgUpdateParamsResponse, error) {
	// Check authority - this should be the governance module account or a dedicated module admin
	if msg.Authority != k.GetAuthority() {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"invalid authority; expected %s, got %s",
			k.GetAuthority(),
			msg.Authority,
		)
	}

	// Validate the parameters
	if err := msg.Params.Validate(); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invalid parameters")
	}

	// Set the parameters
	if err := k.SetParams(ctx, msg.Params); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update parameters")
	}

	return &storagetypes.MsgUpdateParamsResponse{}, nil
}
