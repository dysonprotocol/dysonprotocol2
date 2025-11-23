package keeper

import (
	"context"

	crontasktypes "dysonprotocol.com/x/crontask/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Params returns the module parameters
func (q queryServer) Params(ctx context.Context, req *crontasktypes.QueryParamsRequest) (*crontasktypes.QueryParamsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	params := q.k.GetParams(ctx)
	return &crontasktypes.QueryParamsResponse{Params: &params}, nil
}
