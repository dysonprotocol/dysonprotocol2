package keeper

import (
	"context"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"cosmossdk.io/collections"
	"dysonprotocol.com/x/nameservice/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// DenomByName implements the Query/DenomByName gRPC method
func (k Keeper) DenomByName(c context.Context, req *types.QueryDenomByNameRequest) (*types.QueryDenomByNameResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	if req.Name == "" {
		return nil, status.Error(codes.InvalidArgument, "name cannot be empty")
	}

	// Ensure the provided name exists as a Name NFT root
	if !k.nftKeeper.HasNFT(c, NamesClassID, req.Name) {
		return nil, status.Error(codes.NotFound, "root name NFT not found")
	}

	// Build pagination prefix: when subdenom_prefix is provided, use full (name, subprefix) key prefix
	// otherwise prefix only by name (first element of pair)
	var opts []func(opt *query.CollectionsPaginateOptions[collections.Pair[string, string]])
	if req.SubdenomPrefix != "" {
		// The second key in (root_name, denom) is the full denom starting with root_name.
		// Prefix it with root_name+subdenom_prefix for filtering.
		secondPrefix := req.Name + req.SubdenomPrefix
		pk := collections.Join(req.Name, secondPrefix)
		opts = append(opts, func(o *query.CollectionsPaginateOptions[collections.Pair[string, string]]) {
			o.Prefix = &pk
		})
	} else {
		opts = append(opts, query.WithCollectionPaginationPairPrefix[string, string](req.Name))
	}

	results, pageRes, err := query.CollectionPaginate(
		c,
		k.denomsByRootName,
		req.Pagination,
		func(key collections.Pair[string, string], _ string) (*types.DenomDetails, error) {
			return &types.DenomDetails{Denom: key.K2()}, nil
		},
		opts...,
	)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	if results == nil {
		results = make([]*types.DenomDetails, 0)
	}
	return &types.QueryDenomByNameResponse{Denoms: results, Pagination: pageRes}, nil
}

