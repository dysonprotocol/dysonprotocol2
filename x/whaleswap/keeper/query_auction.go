package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// Auction queries a single auction by ID.
//
// Semantics:
//   - Retrieves complete auction data including escrow details, bids, and NFT markers.
//   - Returns the full AuctionRecord structure with all metadata and current state.
//
// Validation:
//   - Request must be non-nil.
//   - AuctionId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryAuctionResponse containing the auction data.
//
// Errors are returned on invalid request parameters or when auction not found; no panics.
func (k Keeper) Auction(ctx context.Context, req *whaleswapv1.QueryAuctionRequest) (*whaleswapv1.QueryAuctionResponse, error) {
	if req == nil || req.AuctionId == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "auction_id required")
	}
	rec, err := k.AuctionsMap.Get(ctx, req.AuctionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "auction not found: %d", req.AuctionId)
	}
	return &whaleswapv1.QueryAuctionResponse{Auction: &rec}, nil
}
