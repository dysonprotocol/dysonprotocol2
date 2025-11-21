package keeper

import (
	"context"

	storagetypes "dysonprotocol.com/x/storage/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Metrics returns storage usage metrics and stake requirements for a given owner.
//
// Semantics:
//   - Resolves owner identifier (supports both nameservice names and bech32 addresses).
//   - Retrieves total bytes stored by the owner across all entries.
//   - Calculates minimum stake amount required based on StorageStakeMultiple parameter.
//   - Returns current stake amount from staking module for comparison.
//   - Returns zero metrics if owner has no storage entries.
//
// Validation:
//   - Owner must be resolvable to a valid account address.
//
// Returns:
//   - *storagetypes.QueryMetricsResponse containing total bytes, minimum stake requirement, and current stake.
//
// Errors are returned on unresolvable owner or internal failures; no panics.
func (k Keeper) Metrics(ctx context.Context, req *storagetypes.QueryMetricsRequest) (*storagetypes.QueryMetricsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	// Resolve owner (accepts nameservice name or address)
	resolvedOwner, err := k.namesvcKeeper.ResolveNameOrAddress(ctx, req.Owner)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "failed to resolve owner: %v", err)
	}

	// Get storage metrics for the owner
	metrics, err := k.GetStorageMetrics(ctx, resolvedOwner)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get storage metrics: %v", err)
	}

	// Get current stake amount from staking module
	currentStake, err := k.GetTotalDelegatedStake(ctx, resolvedOwner)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get current stake amount: %v", err)
	}

	return &storagetypes.QueryMetricsResponse{
		Owner:              metrics.Owner,
		TotalBytes:         metrics.TotalBytes,
		MinStakeAmount:     metrics.MinStakeAmount,
		CurrentStakeAmount: currentStake.String(),
	}, nil
}

