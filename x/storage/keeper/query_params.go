package keeper

import (
	"context"

	storagetypes "dysonprotocol.com/x/storage/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Params returns the current x/storage module parameters.
//
// Semantics:
//   - Retrieves current parameter values from module state.
//   - Returns default parameters if none have been set (fresh chain state).
//
// Returns:
//   - *storagetypes.QueryParamsResponse containing current MaxStorageSize and StorageStakeMultiple values.
//
// Errors are returned on invalid request or state retrieval failures; no panics.
func (k Keeper) Params(ctx context.Context, req *storagetypes.QueryParamsRequest) (*storagetypes.QueryParamsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	params := k.GetParams(ctx)
	return &storagetypes.QueryParamsResponse{Params: params}, nil
}

