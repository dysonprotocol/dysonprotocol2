package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	cosmossdk_math "cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// OffersByPairPriceRange queries offers for a pair whose price lies within optional bounds.
//
// Semantics:
//   - Filters offers by denom pair and price range (want-per-have ratio).
//   - Canonicalizes pair to consistent internal key (low|high) for indexing.
//   - Calculates price as want_amount/have_amount for each offer in the pair.
//   - Bounds are inclusive and optional; omitting both returns all offers for the pair.
//   - Uses OffersByPairPrice index for efficient ordered scanning.
//   - Supports pagination with ordering by price (ascending, best offers first).
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Both have_denom and want_denom must be non-empty.
//   - Min/max prices must be valid decimal strings if provided.
//
// Returns:
//   - *whaleswapv1.QueryOffersByPairPriceRangeResponse with matching offers and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) OffersByPairPriceRange(ctx context.Context, req *whaleswapv1.QueryOffersByPairPriceRangeRequest) (*whaleswapv1.QueryOffersByPairPriceRangeResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryOffersByPairPriceRangeRequest{}
	}
	if req.HaveDenom == "" || req.WantDenom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "have_denom and want_denom required")
	}
	var minDec, maxDec cosmossdk_math.LegacyDec
	var err error
	if req.MinPrice != "" {
		minDec, err = cosmossdk_math.LegacyNewDecFromStr(req.MinPrice)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid min_price: %s", req.MinPrice)
		}
	}
	if req.MaxPrice != "" {
		maxDec, err = cosmossdk_math.LegacyNewDecFromStr(req.MaxPrice)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid max_price: %s", req.MaxPrice)
		}
	}
	// Scan using pair+price index for ordering, but filter by requested orientation (want-per-have)
	pairKey := k.obPairKey(req.HaveDenom, req.WantDenom)
	pageReq := req.Pagination
	if shouldReversePairOrder(req.HaveDenom, req.WantDenom) {
		if pageReq == nil {
			pageReq = &query.PageRequest{}
		}
		pageReq.Reverse = !pageReq.Reverse
	}
	results, pageRes, perr := query.CollectionFilteredPaginate(
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
				return false, err
			}
			if v.RemainingHave.Denom != req.HaveDenom || v.RemainingWant.Denom != req.WantDenom {
				return false, nil
			}
			price := cosmossdk_math.LegacyNewDecFromInt(v.RemainingWant.Amount).Quo(cosmossdk_math.LegacyNewDecFromInt(v.RemainingHave.Amount))
			if req.MinPrice != "" && price.LT(minDec) {
				return false, nil
			}
			if req.MaxPrice != "" && price.GT(maxDec) {
				return false, nil
			}
			return true, nil
		},
		func(_ collections.Triple[string, string, uint64], id uint64) (*whaleswapv1.OfferData, error) {
			v, err := k.OffersMap.Get(ctx, id)
			if err != nil {
				return nil, err
			}
			return &v, nil
		},
	)
	if perr != nil {
		return nil, cosmossdkerrors.Wrap(perr, "OffersByPairPriceRange paginate failed")
	}
	return &whaleswapv1.QueryOffersByPairPriceRangeResponse{Offers: results, Pagination: pageRes}, nil
}
