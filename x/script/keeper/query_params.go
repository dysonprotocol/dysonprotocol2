package keeper

import (
	"context"

	scripttypes "dysonprotocol.com/x/script/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
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
func (k Keeper) Params(ctx context.Context, req *scripttypes.QueryParamsRequest) (*scripttypes.QueryParamsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "request cannot be nil")
	}

	params := k.GetParams(ctx)
	return &scripttypes.QueryParamsResponse{Params: params}, nil
}
