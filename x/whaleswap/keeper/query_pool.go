package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// Pool queries a single AMM pool by ID.
//
// Behavior:
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

