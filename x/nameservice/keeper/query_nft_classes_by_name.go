package keeper

import (
	"context"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"cosmossdk.io/collections"
	"dysonprotocol.com/x/nameservice/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// NFTClassesByName implements the Query/NFTClassesByName gRPC method
func (k Keeper) NFTClassesByName(c context.Context, req *types.QueryNFTClassesByNameRequest) (*types.QueryNFTClassesByNameResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	if req.Name == "" {
		return nil, status.Error(codes.InvalidArgument, "name cannot be empty")
	}

	// Ensure the provided name exists as a Name NFT root
	// This verifies existence; does not require .dys suffix explicitly per spec
	if !k.nftKeeper.HasNFT(c, k.NamesClassID(c), req.Name) {
		return nil, status.Error(codes.NotFound, "root name NFT not found")
	}

	// Build pagination prefix: when subclass_prefix is provided, use full (name, subprefix) pair key prefix
	// otherwise prefix only by name (first element of pair)
	var opts []func(opt *query.CollectionsPaginateOptions[collections.Pair[string, string]])
	if req.SubclassPrefix != "" {
		// The second key in the (root_name, class_id) pair is the full class_id (which starts with root_name).
		// To filter by a subclass path prefix like "/foo", we prefix K2 with root_name+subclass_prefix.
		// collections.Join with a prefix correctly matches all class IDs starting with the prefix,
		// as verified by test_nft_classes_by_name_subclass_prefix_deep_nested which passes.
		// The second key in the (root_name, class_id) pair is the full class_id (which starts with root_name).
		// To filter by a subclass path prefix like "/foo", we must prefix K2 with root_name+subclass_prefix.
		secondPrefix := req.Name + req.SubclassPrefix
		pk := collections.Join(req.Name, secondPrefix)
		opts = append(opts, func(o *query.CollectionsPaginateOptions[collections.Pair[string, string]]) {
			o.Prefix = &pk
		})
	} else {
		opts = append(opts, query.WithCollectionPaginationPairPrefix[string, string](req.Name))
	}

	// Iterate the reverse index with the computed prefix and collect class IDs
	classIDs, pageRes, err := query.CollectionPaginate(
		c,
		k.classesByRootName,
		req.Pagination,
		func(key collections.Pair[string, string], value string) (string, error) { return value, nil },
		opts...,
	)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	if classIDs == nil {
		classIDs = make([]string, 0)
	}
	return &types.QueryNFTClassesByNameResponse{ClassIds: classIDs, Pagination: pageRes}, nil
}
