package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// OffersBest returns up to limit best-priced offers for a pair (convenience endpoint).
//
// Semantics:
//   - Returns top offers for a pair sorted by price (want-per-have, ascending = best for takers).
//   - Canonicalizes pair to consistent internal key for indexing.
//   - Uses OffersByPairPrice index for efficient ordered retrieval.
//   - Applies limit (defaulting to 10) via pagination parameters.
//   - Filters to ensure offers match the requested orientation (have/want denoms).
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Both have_denom and want_denom must be non-empty.
//   - Limit defaults to 10 if zero or negative.
//
// Returns:
//   - *whaleswapv1.QueryOffersBestResponse with up to limit best offers (price-ordered).
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) OffersBest(ctx context.Context, req *whaleswapv1.QueryOffersBestRequest) (*whaleswapv1.QueryOffersBestResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryOffersBestRequest{}
	}
	if req.HaveDenom == "" || req.WantDenom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "have_denom and want_denom required")
	}
	limit := int(req.Limit)
	if limit <= 0 {
		limit = 10
	}
	pairKey := k.obPairKey(req.HaveDenom, req.WantDenom)
	// Use filtered paginate with limit via PageRequest
	pageReq := &query.PageRequest{Limit: uint64(limit)}
	if shouldReversePairOrder(req.HaveDenom, req.WantDenom) {
		pageReq.Reverse = true
	}
	offers, _, err := query.CollectionFilteredPaginate(
		ctx,
		k.OffersByPairPrice,
		pageReq,
		func(key collections.Triple[string, string, uint64], id uint64) (bool, error) {
			k1, _, _ := key.K1(), key.K2(), key.K3()
			if k1 != pairKey {
				return false, nil
			}
			v, err := k.OffersMap.Get(ctx, id)
			if err != nil {
				return false, cosmossdkerrors.Wrapf(err, "offer not found: %d", id)
			}
			return v.RemainingHave.Denom == req.HaveDenom && v.RemainingWant.Denom == req.WantDenom, nil
		},
		func(_ collections.Triple[string, string, uint64], id uint64) (*whaleswapv1.OfferData, error) {
			v, err := k.OffersMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", id)
			}
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "OffersBest paginate failed")
	}
	return &whaleswapv1.QueryOffersBestResponse{Offers: offers}, nil
}
