package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// Params queries the current whaleswap module parameters.
//
// Semantics:
//   - Retrieves all module parameters from the parameter store.
//   - Returns configuration values including fees, limits, and module settings.
//
// Validation:
//   - No validation required (empty request accepted).
//
// Returns:
//   - *whaleswapv1.QueryParamsResponse containing the current module parameters.
//
// Errors are returned on parameter retrieval failures; no panics.
func (k Keeper) Params(ctx context.Context, _ *whaleswapv1.QueryParamsRequest) (*whaleswapv1.QueryParamsResponse, error) {
	p := k.GetParams(ctx)
	return &whaleswapv1.QueryParamsResponse{Params: p}, nil
}

// Pool queries a single AMM pool by ID.
//
// Semantics:
//   - Retrieves complete pool data including reserves, shares denom, and configuration.
//   - Returns the full Pool structure with all metadata and current state.
//
// Validation:
//   - Request must be non-nil.
//   - PoolId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryPoolResponse containing the pool data.
//
// Errors are returned on invalid request parameters or when pool not found; no panics.
func (k Keeper) Pool(ctx context.Context, req *whaleswapv1.QueryPoolRequest) (*whaleswapv1.QueryPoolResponse, error) {
	if req == nil || req.PoolId == 0 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "pool_id required")
	}
	p, err := k.PoolsMap.Get(ctx, req.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", req.PoolId)
	}
	return &whaleswapv1.QueryPoolResponse{Pool: &p}, nil
}

// Pools lists all AMM pools with pagination.
//
// Semantics:
//   - Returns all pools in the system with no filtering.
//   - Uses direct pagination over the primary PoolsMap.
//   - Results ordered by pool ID ascending.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//
// Returns:
//   - *whaleswapv1.QueryPoolsResponse with pool list and pagination metadata.
//
// Errors are returned on pagination failures; no panics.
func (k Keeper) Pools(ctx context.Context, req *whaleswapv1.QueryPoolsRequest) (*whaleswapv1.QueryPoolsResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolsRequest{}
	}
	results, pageRes, err := query.CollectionPaginate(ctx, k.PoolsMap, req.Pagination, func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
		v := value
		return &v, nil
	})
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate pools failed")
	}
	return &whaleswapv1.QueryPoolsResponse{Pools: results, Pagination: pageRes}, nil
}
