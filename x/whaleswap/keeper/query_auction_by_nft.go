package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// AuctionByNFT queries the auction associated with specific NFT escrow markers.
//
// Semantics:
//   - Returns the auction where the specified class_id and nft_id appear as escrow markers.
//   - Scans auctions to find matching NFT identifiers (expected to be unique).
//   - Uses unpaginated scan since NFT markers should be unique per auction.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Both class_id and nft_id must be non-empty.
//
// Returns:
//   - *whaleswapv1.QueryAuctionByNFTResponse with the matching auction.
//
// Errors are returned on invalid parameters, pagination failures, or when no matching auction found; no panics.
func (k Keeper) AuctionByNFT(ctx context.Context, req *whaleswapv1.QueryAuctionByNFTRequest) (*whaleswapv1.QueryAuctionByNFTResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryAuctionByNFTRequest{}
	}
	if req.ClassId == "" || req.NftId == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "class_id and nft_id required")
	}
	var matched *whaleswapv1.AuctionRecord
	_, _, err := query.CollectionPaginate(ctx, k.AuctionsMap, nil, func(key uint64, value whaleswapv1.AuctionRecord) (*whaleswapv1.AuctionRecord, error) {
		if value.ClassId == req.ClassId && value.NftId == req.NftId {
			v := value
			matched = &v
			return &v, nil
		}
		return nil, nil
	})
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AuctionByNFT paginate failed")
	}
	if matched == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrNotFound, "auction not found for NFT")
	}
	return &whaleswapv1.QueryAuctionByNFTResponse{Auction: matched}, nil
}

