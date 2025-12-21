package keeper

import (
	"context"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"cosmossdk.io/collections"
	"dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// NamesByDestination implements the Query/NamesByDestination gRPC method
func (k Keeper) NamesByDestination(c context.Context, req *types.QueryNamesByDestinationRequest) (*types.QueryNamesByDestinationResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	if req.Destination == "" {
		return nil, status.Error(codes.InvalidArgument, "destination address cannot be empty")
	}

	// Validate destination: allow bech32 address or existing name
	if _, err := sdk.AccAddressFromBech32(req.Destination); err != nil {
		if _, found := k.nftKeeper.GetNFT(c, k.NamesClassID(c), req.Destination); !found {
			return nil, status.Error(codes.InvalidArgument, "destination must be a valid bech32 address or existing name")
		}
	}

	// Fetch the name strings for each matching entry
	nameResults, pageRes, err := query.CollectionPaginate(
		c,
		k.nameDestinations,
		req.Pagination,
		func(key collections.Pair[string, string], value string) (string, error) {
			// Return the source name (which is the value)
			return value, nil
		},
		query.WithCollectionPaginationPairPrefix[string, string](req.Destination),
	)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &types.QueryNamesByDestinationResponse{
		Names:      nameResults,
		Pagination: pageRes,
	}, nil
}

