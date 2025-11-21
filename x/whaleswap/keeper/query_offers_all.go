package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// Offers provides unified offer listing with optional denom filters and pagination.
//
// Semantics:
//   - Supports multiple query patterns based on provided filters:
//   - Both have_denom and want_denom: uses OffersByPairPrice index with canonical pair keys
//   - Only have_denom: uses OffersByHave index for efficient prefix scanning
//   - Only want_denom: uses OffersByWant index for efficient prefix scanning
//   - No filters: direct pagination over primary OffersMap
//   - Canonicalizes pairs (low|high) for consistent indexing.
//   - Supports pagination with consistent ordering by offer ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Denom filters are optional but must be valid denomination strings if provided.
//
// Returns:
//   - *whaleswapv1.QueryOffersResponse with matching offers and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) Offers(ctx context.Context, req *whaleswapv1.QueryOffersRequest) (*whaleswapv1.QueryOffersResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryOffersRequest{}
	}
	have := req.HaveDenom
	want := req.WantDenom

	// Case 1: both filters → pair+price index (pair key only; price ignored by predicate)
	if have != "" && want != "" {
		pairKey := k.obPairKey(have, want)
		pageReq := req.Pagination
		if shouldReversePairOrder(have, want) {
			if pageReq == nil {
				pageReq = &query.PageRequest{}
			}
			pageReq.Reverse = !pageReq.Reverse
		}
		offers, pageRes, err := query.CollectionFilteredPaginate(
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
				if v.RemainingHave.Denom != have || v.RemainingWant.Denom != want {
					return false, nil
				}
				return true, nil
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
			return nil, cosmossdkerrors.Wrapf(err, "paginate offers by pair failed: %s", pairKey)
		}
		return &whaleswapv1.QueryOffersResponse{Offers: offers, Pagination: pageRes}, nil
	}

	// Case 2: single filter by have
	if have != "" {
		offers, pageRes, err := query.CollectionFilteredPaginate(
			ctx,
			k.OffersByHave,
			req.Pagination,
			func(key collections.Pair[string, uint64], id uint64) (bool, error) {
				// Case 2 only executes when have != "" && want == ""
				// (Case 1 matches when both are non-empty), so want is always empty here.
				k1, _ := key.K1(), key.K2()
				return k1 == have, nil
			},
			func(_ collections.Pair[string, uint64], id uint64) (*whaleswapv1.OfferData, error) {
				v, err := k.OffersMap.Get(ctx, id)
				if err != nil {
					return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", id)
				}
				return &v, nil
			},
		)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "paginate offers by have failed: %s", have)
		}
		return &whaleswapv1.QueryOffersResponse{Offers: offers, Pagination: pageRes}, nil
	}

	// Case 3: single filter by want
	if want != "" {
		offers, pageRes, err := query.CollectionFilteredPaginate(
			ctx,
			k.OffersByWant,
			req.Pagination,
			func(key collections.Pair[string, uint64], id uint64) (bool, error) {
				// Case 3 only executes when want != "" && have == ""
				// (Cases 1 and 2 match when have is non-empty), so have is always empty here.
				k1, _ := key.K1(), key.K2()
				return k1 == want, nil
			},
			func(_ collections.Pair[string, uint64], id uint64) (*whaleswapv1.OfferData, error) {
				v, err := k.OffersMap.Get(ctx, id)
				if err != nil {
					return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", id)
				}
				return &v, nil
			},
		)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "paginate offers by want failed: %s", want)
		}
		return &whaleswapv1.QueryOffersResponse{Offers: offers, Pagination: pageRes}, nil
	}

	// Case 4: no filters → full scan
	offers, pageRes, err := query.CollectionPaginate(
		ctx,
		k.OffersMap,
		req.Pagination,
		func(key uint64, value whaleswapv1.OfferData) (*whaleswapv1.OfferData, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate offers failed")
	}
	return &whaleswapv1.QueryOffersResponse{Offers: offers, Pagination: pageRes}, nil
}
