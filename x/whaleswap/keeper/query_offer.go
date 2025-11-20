package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// Offer queries a single offer by ID.
//
// Semantics:
//   - Retrieves offer data from the offers map using the provided offer_id.
//   - Returns the complete OfferData including maker, amounts, status, and timestamps.
//
// Validation:
//   - Request must be non-nil.
//   - OfferId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryOfferResponse containing the offer data.
//
// Errors are returned on invalid request parameters or when offer not found; no panics.
func (k Keeper) Offer(ctx context.Context, req *whaleswapv1.QueryOfferRequest) (*whaleswapv1.QueryOfferResponse, error) {
	if req == nil || req.OfferId == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "offer_id required")
	}
	offer, err := k.OffersMap.Get(ctx, req.OfferId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", req.OfferId)
	}
	return &whaleswapv1.QueryOfferResponse{Offer: &offer}, nil
}
