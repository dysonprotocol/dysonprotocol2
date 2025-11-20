package keeper

import (
	"context"

	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

// Params queries the current whaleswap module parameters.
//
// Behavior:
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

