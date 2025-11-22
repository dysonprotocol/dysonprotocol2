package keeper

import (
	"context"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"cosmossdk.io/collections"
	"dysonprotocol.com/x/nameservice/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// BidsForNFT implements listing all historical bids for an NFT
func (k Keeper) BidsForNFT(c context.Context, req *types.QueryBidsForNFTRequest) (*types.QueryBidsForNFTResponse, error) {
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

