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

	// Cache per-NFT latest status to avoid repeated keeper calls
	type nftKey struct{ classID, nftID string }
	nftStatus := map[nftKey]struct {
		owner string
		data  types.NFTData
	}{}

	for _, id := range ids {
		rec, gErr := k.bids.Get(c, id)
		if gErr != nil {
			k.Logger.Error("BidsByBidder: Failed to get bid record",
				"bid_id", id,
				"bidder", req.Bidder,
				"error", gErr)
			return nil, status.Error(codes.Internal, "failed to retrieve bid record")
		}
		if wantFilter {
			if _, ok := statusSet[rec.Status]; !ok {
				continue
			}
		}

		key := nftKey{classID: rec.ClassId, nftID: rec.NftId}
		var owner string
		var data types.NFTData
		if cached, ok := nftStatus[key]; ok {
			owner = cached.owner
			data = cached.data
		} else {
			if !k.nftKeeper.HasNFT(c, rec.ClassId, rec.NftId) {
				k.Logger.Error("BidsByBidder: NFT not found for bid",
					"bid_id", id,
					"class_id", rec.ClassId,
					"nft_id", rec.NftId,
					"bidder", req.Bidder)
				return nil, status.Error(codes.NotFound, "NFT not found for bid")
			}
			o := k.nftKeeper.GetOwner(c, rec.ClassId, rec.NftId)
			owner = o.String()
			d, err := k.GetNFTData(c, rec.ClassId, rec.NftId)
			if err != nil {
				k.Logger.Error("BidsByBidder: Failed to get NFT data for bid",
					"bid_id", id,
					"class_id", rec.ClassId,
					"nft_id", rec.NftId,
					"bidder", req.Bidder,
					"error", err)
				return nil, status.Error(codes.Internal, "failed to retrieve NFT data for bid")
			}
			data = d
			nftStatus[key] = struct {
				owner string
				data  types.NFTData
			}{owner: owner, data: data}
		}

		// Fixed: IsCurrentHighest calculation now correctly checks bid status
		// A bid is current highest only if:
		// 1. The bid status is BID_ACTIVE, AND
		// 2. The bidder matches the current highest bidder
		// This ensures outbid bids always have IsCurrentHighest=false
		isCurrent := rec.Status == types.BidStatus_BID_ACTIVE && data.CurrentBidder == rec.Bidder
		b := &types.BidWithNFTStatus{Bid: rec, NftOwner: owner, Nft: data, IsCurrentHighest: isCurrent}
		results = append(results, b)
	}

	return &types.QueryBidsByBidderResponse{Bids: results, Pagination: pageRes}, nil
}
