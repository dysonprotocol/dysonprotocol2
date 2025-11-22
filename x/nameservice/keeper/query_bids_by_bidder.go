package keeper

import (
	"context"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"cosmossdk.io/collections"
	"dysonprotocol.com/x/nameservice/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// BidsByBidder implements listing bids by bidder with optional status filtering
func (k Keeper) BidsByBidder(c context.Context, req *types.QueryBidsByBidderRequest) (*types.QueryBidsByBidderResponse, error) {
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

