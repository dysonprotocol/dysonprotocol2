package keeper

import (
	"context"

	scripttypes "dysonprotocol.com/x/script/types"
)

// Params queries the parameters of the script module.
//
// Semantics:
//   - Retrieves current script module parameters from the parameter store.
//   - No validation or complex logic required.
//
// Returns:
//   - *scripttypes.QueryParamsResponse with current module parameters.
//
// Errors are returned on parameter retrieval failures; no panics.
func (k Keeper) Params(ctx context.Context, req *scripttypes.QueryParamsRequest) (*scripttypes.QueryParamsResponse, error) {
	params := k.GetParams(ctx)
	return &scripttypes.QueryParamsResponse{Params: params}, nil
}
