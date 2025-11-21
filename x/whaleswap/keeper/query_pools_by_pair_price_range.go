package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	cosmossdk_math "cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// PoolsByPairPriceRange queries pools for a pair whose instantaneous price falls within optional bounds.
//
// Semantics:
//   - Filters pools by denom pair and price range (quote/base ratio from reserves).
//   - Price calculated as coin_b/coin_a where the pair matches requested denoms.
//   - Bounds are inclusive and optional; omitting both returns all matching pairs.
//   - Uses filtered pagination over the primary PoolsMap.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Both base_denom and quote_denom must be non-empty.
//   - Min/max prices must be valid decimal strings if provided.
//
// Returns:
//   - *whaleswapv1.QueryPoolsByPairPriceRangeResponse with matching pools and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) PoolsByPairPriceRange(ctx context.Context, req *whaleswapv1.QueryPoolsByPairPriceRangeRequest) (*whaleswapv1.QueryPoolsByPairPriceRangeResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolsByPairPriceRangeRequest{}
	}
	if req.BaseDenom == "" || req.QuoteDenom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "base_denom and quote_denom required")
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
	results, pageRes, perr := query.CollectionFilteredPaginate(ctx, k.PoolsMap, req.Pagination,
		func(key uint64, value whaleswapv1.Pool) (bool, error) {
			if len(value.Coins) != 2 {
				return false, nil
			}
			rBase := value.Coins.AmountOf(req.BaseDenom)
			rQuote := value.Coins.AmountOf(req.QuoteDenom)
			if rBase.IsZero() || rQuote.IsZero() {
				return false, nil
			}
			if req.MinPrice != "" {
				minThresh := minDec.MulInt(rBase).Ceil().TruncateInt()
				if rQuote.LT(minThresh) {
					return false, nil
				}
			}
			if req.MaxPrice != "" {
				maxThresh := maxDec.MulInt(rBase).TruncateInt()
				if rQuote.GT(maxThresh) {
					return false, nil
				}
			}
			return true, nil
		},
		func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
			v := value
			return &v, nil
		},
	)
	if perr != nil {
		return nil, cosmossdkerrors.Wrap(perr, "PoolsByPairPriceRange paginate failed")
	}
	return &whaleswapv1.QueryPoolsByPairPriceRangeResponse{Pools: results, Pagination: pageRes}, nil
}
