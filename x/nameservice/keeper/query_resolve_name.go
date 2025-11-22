package keeper

import (
	"context"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"dysonprotocol.com/x/nameservice/types"
)

// ResolveName implements the Query/ResolveName gRPC method
func (k Keeper) ResolveName(c context.Context, req *types.QueryResolveNameRequest) (*types.QueryResolveNameResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	if req.NameOrAddress == "" {
		return nil, status.Error(codes.InvalidArgument, "name_or_address cannot be empty")
	}

	// Use the ResolveNameOrAddress method from the keeper
	address, err := k.ResolveNameOrAddress(c, req.NameOrAddress)
	if err != nil {
		// Note: ResolveNameOrAddress can return ErrNotFound or ErrInvalidRequest,
		// but we always return InvalidArgument here for consistency with query API design.
		// The error message still contains the original error information.
		return nil, status.Error(codes.InvalidArgument, err.Error())
	}

	return &types.QueryResolveNameResponse{
		Address: address,
	}, nil
}

