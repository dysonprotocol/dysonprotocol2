package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// OffersByOwner queries offers by owner address with optional status filter.
//
// Semantics:
//   - Returns offers owned by the specified address, optionally filtered by status.
//   - Uses indexed queries on OffersByOwnerStatus when both owner and status provided for optimal performance.
//   - Falls back to filtered scans over primary OffersMap for partial filters.
//   - Supports pagination with consistent ordering by offer ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Owner must be non-empty.
//   - Status must be valid ("open", "closed", "cancelled") if provided.
//
// Returns:
//   - *whaleswapv1.QueryOffersByOwnerResponse with matching offers and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) OffersByOwner(ctx context.Context, req *whaleswapv1.QueryOffersByOwnerRequest) (*whaleswapv1.QueryOffersByOwnerResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryOffersByOwnerRequest{}
	}
	owner := req.Owner
	status := req.Status
	if owner == "" {
		return nil, fmt.Errorf("owner required")
	}
	// If status provided, validate it and use owner+status index; else fall back to filtered scan
	if owner != "" && status != "" {
		if status != whaleswapv1.OfferStatusOpen && status != whaleswapv1.OfferStatusClosed && status != whaleswapv1.OfferStatusCancelled {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid status: %s", status)
		}
		results, pageRes, err := query.CollectionFilteredPaginate(
			ctx,
			k.OffersByOwnerStatus,
			req.Pagination,
			func(key collections.Triple[string, string, uint64], _ uint64) (bool, error) {
				k1, k2, _ := key.K1(), key.K2(), key.K3()
				return k1 == owner && k2 == status, nil
			},
			func(_ collections.Triple[string, string, uint64], value uint64) (*whaleswapv1.OfferData, error) {
				v, err := k.OffersMap.Get(ctx, value)
				if err != nil {
					return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", value)
				}
				return &v, nil
			},
		)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "paginate offers by owner/status failed: %s/%s", owner, status)
		}
		return &whaleswapv1.QueryOffersByOwnerResponse{Offers: results, Pagination: pageRes}, nil
	}
	// filtered scan fallback using predicate to avoid nil entries
	results, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		k.OffersMap,
		req.Pagination,
		func(_ uint64, value whaleswapv1.OfferData) (bool, error) {
			if owner != "" && value.Maker != owner {
				return false, nil
			}
			if status != "" && value.Status != status {
				return false, nil
			}
			return true, nil
		},
		func(_ uint64, value whaleswapv1.OfferData) (*whaleswapv1.OfferData, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate offers failed")
	}
	return &whaleswapv1.QueryOffersByOwnerResponse{Offers: results, Pagination: pageRes}, nil
}

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
		low, high := have, want
		if low > high {
			low, high = high, low
		}
		pairKey := low + "|" + high
		offers, pageRes, err := query.CollectionFilteredPaginate(
			ctx,
			k.OffersByPairPrice,
			req.Pagination,
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
