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
	low, high := req.HaveDenom, req.WantDenom
	if low > high {
		low, high = high, low
	}
	pairKey := low + "|" + high
	results, pageRes, perr := query.CollectionFilteredPaginate(
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
	low, high := req.HaveDenom, req.WantDenom
	if low > high {
		low, high = high, low
	}
	pairKey := low + "|" + high
	// Use filtered paginate with limit via PageRequest
	pageReq := &query.PageRequest{Limit: uint64(limit)}
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
