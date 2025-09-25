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

// Ensure Keeper implements QueryServer interface
var _ types.QueryServer = Keeper{}

// ComputeHash implements the Query/ComputeHash gRPC method
func (k Keeper) ComputeHash(c context.Context, req *types.QueryComputeHashRequest) (*types.QueryComputeHashResponse, error) {
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
		return nil, status.Error(codes.InvalidArgument, err.Error())
	}

	return &types.QueryResolveNameResponse{
		Address: address,
	}, nil
}

// Params implements the Query/Params gRPC method
func (k Keeper) Params(c context.Context, req *types.QueryParamsRequest) (*types.QueryParamsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	params := k.GetParams(c)

	return &types.QueryParamsResponse{Params: params}, nil
}

// QueryNamesByDestination implements the Query/QueryNamesByDestination gRPC method
func (k Keeper) QueryNamesByDestination(c context.Context, req *types.QueryNamesByDestinationRequest) (*types.QueryNamesByDestinationResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	if req.Destination == "" {
		return nil, status.Error(codes.InvalidArgument, "destination address cannot be empty")
	}

	// Validate destination: allow bech32 address or existing name
	if _, err := sdk.AccAddressFromBech32(req.Destination); err != nil {
		if _, found := k.nftKeeper.GetNFT(c, NamesClassID, req.Destination); !found {
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

// QueryNFTClassesByName implements the Query/QueryNFTClassesByName gRPC method
func (k Keeper) QueryNFTClassesByName(c context.Context, req *types.QueryNFTClassesByNameRequest) (*types.QueryNFTClassesByNameResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	if req.Name == "" {
		return nil, status.Error(codes.InvalidArgument, "name cannot be empty")
	}

	// Ensure the provided name exists as a Name NFT root
	// This verifies existence; does not require .dys suffix explicitly per spec
	if !k.nftKeeper.HasNFT(c, NamesClassID, req.Name) {
		return nil, status.Error(codes.NotFound, "root name NFT not found")
	}

	// Build pagination prefix: when subclass_prefix is provided, use full (name, subprefix) pair key prefix
	// otherwise prefix only by name (first element of pair)
	var opts []func(opt *query.CollectionsPaginateOptions[collections.Pair[string, string]])
	if req.SubclassPrefix != "" {
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

// QueryDenomByName implements the Query/QueryDenomByName gRPC method
func (k Keeper) QueryDenomByName(c context.Context, req *types.QueryDenomByNameRequest) (*types.QueryDenomByNameResponse, error) {
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

// QueryBidsByBidder implements listing bids by bidder with optional status filtering
func (k Keeper) QueryBidsByBidder(c context.Context, req *types.QueryBidsByBidderRequest) (*types.QueryBidsByBidderResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}
	if req.Bidder == "" {
		return nil, status.Error(codes.InvalidArgument, "bidder cannot be empty")
	}

	// Prepare optional status filter set
	wantFilter := len(req.StatusFilter) > 0
	statusSet := make(map[types.BidStatus]struct{})
	if wantFilter {
		for _, s := range req.StatusFilter {
			statusSet[s] = struct{}{}
		}
	}

	// Paginate over bidder index
	ids, pageRes, err := query.CollectionPaginate(
		c,
		k.bidsByBidder,
		req.Pagination,
		func(key collections.Pair[string, uint64], value uint64) (uint64, error) { return value, nil },
		query.WithCollectionPaginationPairPrefix[string, uint64](req.Bidder),
	)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	// Build response records
	results := make([]*types.BidWithNFTStatus, 0, len(ids))
	includeStatus := true // always include for now (proto3 bool lacks presence)

	// Cache per-NFT latest status to avoid repeated keeper calls
	type nftKey struct{ classID, nftID string }
	nftStatus := map[nftKey]struct {
		owner string
		data  types.NFTData
	}{}

	for _, id := range ids {
		rec, gErr := k.bids.Get(c, id)
		if gErr != nil {
			continue
		}
		if wantFilter {
			if _, ok := statusSet[rec.Status]; !ok {
				continue
			}
		}

		var owner string
		var data types.NFTData
		if includeStatus {
			key := nftKey{classID: rec.ClassId, nftID: rec.NftId}
			if cached, ok := nftStatus[key]; ok {
				owner = cached.owner
				data = cached.data
			} else {
				o := k.nftKeeper.GetOwner(c, rec.ClassId, rec.NftId)
				owner = o.String()
				d, _ := k.GetNFTData(c, rec.ClassId, rec.NftId)
				data = d
				nftStatus[key] = struct {
					owner string
					data  types.NFTData
				}{owner: owner, data: data}
			}
		}

		isCurrent := includeStatus && (data.CurrentBidder == rec.Bidder)
		b := &types.BidWithNFTStatus{Bid: rec, NftOwner: owner, Nft: data, IsCurrentHighest: isCurrent}
		results = append(results, b)
	}

	return &types.QueryBidsByBidderResponse{Bids: results, Pagination: pageRes}, nil
}

// QueryBidsForNFT implements listing all historical bids for an NFT
func (k Keeper) QueryBidsForNFT(c context.Context, req *types.QueryBidsForNFTRequest) (*types.QueryBidsForNFTResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}
	if req.ClassId == "" || req.NftId == "" {
		return nil, status.Error(codes.InvalidArgument, "class_id and nft_id are required")
	}

	ids, pageRes, err := query.CollectionFilteredPaginate(
		c,
		k.bidsByNFT,
		req.Pagination,
		func(key collections.Triple[string, string, uint64], _ uint64) (bool, error) {
			return key.K1() == req.ClassId && key.K2() == req.NftId, nil
		},
		func(_ collections.Triple[string, string, uint64], value uint64) (uint64, error) { return value, nil },
	)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	records := make([]*types.BidRecord, 0, len(ids))
	for _, id := range ids {
		rec, gErr := k.bids.Get(c, id)
		if gErr == nil {
			// preserve chronological order because ids are increasing
			r := rec
			records = append(records, &r)
		}
	}
	return &types.QueryBidsForNFTResponse{Bids: records, Pagination: pageRes}, nil
}
