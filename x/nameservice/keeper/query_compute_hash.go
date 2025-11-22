package keeper

import (
	"context"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"dysonprotocol.com/x/nameservice/types"
)

// ComputeHash implements the Query/ComputeHash gRPC method
func (k Keeper) ComputeHash(c context.Context, req *types.QueryComputeHashRequest) (*types.QueryComputeHashResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	if req.Name == "" {
		return nil, status.Error(codes.InvalidArgument, "name cannot be empty")
	}

	if req.Salt == "" {
		return nil, status.Error(codes.InvalidArgument, "salt cannot be empty")
	}

	if req.Committer == "" {
		return nil, status.Error(codes.InvalidArgument, "committer address cannot be empty")
	}

	// Use the common hash function
	hexhash := k.ComputeNameRegistrationHash(req.Name, req.Committer, req.Salt)

	return &types.QueryComputeHashResponse{
		HexHash: hexhash,
	}, nil
}

