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
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

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
	// Only validate if storage_stake_multiple is non-zero (zero values like "0", "0.0" disable validation)
	stakeMultiple, err := math.LegacyNewDecFromStr(params.StorageStakeMultiple)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to parse storage_stake_multiple for validation check")
	}
	if !stakeMultiple.IsZero() {
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
			return nil, status.Errorf(
				codes.InvalidArgument,
				"failed to parse required stake amount: invalid integer string '%s'",
				requiredStakeStr,
			)
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

