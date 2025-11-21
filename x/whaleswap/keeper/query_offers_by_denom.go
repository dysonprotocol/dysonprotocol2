package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// OffersByDenom queries offers that reference a specific denom either as have or want side.
//
// Semantics:
//   - Returns offers where the specified denom appears in either have_denom or want_denom.
//   - Uses role filter to restrict to "have" side, "want" side, or both (when empty).
//   - Leverages OffersByHave and OffersByWant indices when role is specified for efficiency.
//   - Falls back to filtered scan over primary OffersMap when role is unspecified.
//   - Supports pagination with consistent ordering by offer ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Denom must be non-empty.
//   - Role must be "have", "want", or empty if specified.
//
// Returns:
//   - *whaleswapv1.QueryOffersByDenomResponse with matching offers and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) OffersByDenom(ctx context.Context, req *whaleswapv1.QueryOffersByDenomRequest) (*whaleswapv1.QueryOffersByDenomResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryOffersByDenomRequest{}
	}
	if req.Denom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "denom required")
	}
	role := req.Role
	if role == "have" {
		results, pageRes, err := query.CollectionFilteredPaginate(
			ctx,
			k.OffersByHave,
			req.Pagination,
			func(key collections.Pair[string, uint64], _ uint64) (bool, error) {
				k1, _ := key.K1(), key.K2()
				return k1 == req.Denom, nil
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
			return nil, cosmossdkerrors.Wrap(err, "paginate offers by have failed")
		}
		return &whaleswapv1.QueryOffersByDenomResponse{Offers: results, Pagination: pageRes}, nil
	}
	if role == "want" {
		results, pageRes, err := query.CollectionFilteredPaginate(
			ctx,
			k.OffersByWant,
			req.Pagination,
			func(key collections.Pair[string, uint64], _ uint64) (bool, error) {
				k1, _ := key.K1(), key.K2()
				return k1 == req.Denom, nil
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
			return nil, cosmossdkerrors.Wrap(err, "paginate offers by want failed")
		}
		return &whaleswapv1.QueryOffersByDenomResponse{Offers: results, Pagination: pageRes}, nil
	}
	// role empty -> either side: fallback to filtered scan
	results, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		k.OffersMap,
		req.Pagination,
		func(_ uint64, value whaleswapv1.OfferData) (bool, error) {
			return value.RemainingHave.Denom == req.Denom || value.RemainingWant.Denom == req.Denom, nil
		},
		func(_ uint64, value whaleswapv1.OfferData) (*whaleswapv1.OfferData, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate offers by denom failed")
	}
	return &whaleswapv1.QueryOffersByDenomResponse{Offers: results, Pagination: pageRes}, nil
}
