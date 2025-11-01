package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	cosmossdk_math "cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// PoolsByPair queries all pools matching a denom pair with pagination.
//
// Semantics:
//   - Returns pools containing exactly the specified denom pair, regardless of order.
//   - Canonicalizes the pair internally for consistent lookup.
//   - Uses filtered pagination over the primary PoolsMap.
//   - Results ordered by pool ID ascending.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Both base_denom and quote_denom must be non-empty.
//
// Returns:
//   - *whaleswapv1.QueryPoolsByPairResponse with matching pools and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) PoolsByPair(ctx context.Context, req *whaleswapv1.QueryPoolsByPairRequest) (*whaleswapv1.QueryPoolsByPairResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolsByPairRequest{}
	}
	if req.BaseDenom == "" || req.QuoteDenom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "base_denom and quote_denom required")
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("PoolsByPair start", "base_denom", req.BaseDenom, "quote_denom", req.QuoteDenom)
	// Pre-scan map to aid debugging
	total := 0
	_ = k.PoolsMap.Walk(ctx, nil, func(id uint64, p whaleswapv1.Pool) (bool, error) {
		denA := ""
		denB := ""
		if len(p.Coins) == 2 {
			denA = p.Coins[0].Denom
			denB = p.Coins[1].Denom
		}
		logger.Info("PoolsByPair pre-scan", "pool_id", id, "denoms", []string{denA, denB})
		total++
		return false, nil
	})
	logger.Info("PoolsByPair map summary", "total_pools", total)
	base, quote := req.BaseDenom, req.QuoteDenom
	results, pageRes, err := query.CollectionFilteredPaginate(ctx, k.PoolsMap, req.Pagination,
		func(key uint64, value whaleswapv1.Pool) (bool, error) {
			if len(value.Coins) != 2 {
				return false, nil
			}
			match := (value.Coins[0].Denom == base && value.Coins[1].Denom == quote) || (value.Coins[0].Denom == quote && value.Coins[1].Denom == base)
			logger.Info("PoolsByPair eval", "pool_id", key, "denoms", []string{value.Coins[0].Denom, value.Coins[1].Denom}, "match", match)
			return match, nil
		},
		func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "PoolsByPair paginate failed")
	}
	logger.Info("PoolsByPair result", "count", len(results), "next_key", pageRes.GetNextKey() != nil, "total", pageRes.GetTotal())
	return &whaleswapv1.QueryPoolsByPairResponse{Pools: results, Pagination: pageRes}, nil
}

// PoolsByDenom queries all pools that include a specific denom on either side.
//
// Semantics:
//   - Returns pools where the specified denom appears in either coin position.
//   - Uses filtered pagination over the primary PoolsMap.
//   - Results ordered by pool ID ascending.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Denom must be non-empty.
//
// Returns:
//   - *whaleswapv1.QueryPoolsByDenomResponse with matching pools and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) PoolsByDenom(ctx context.Context, req *whaleswapv1.QueryPoolsByDenomRequest) (*whaleswapv1.QueryPoolsByDenomResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolsByDenomRequest{}
	}
	if req.Denom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "denom required")
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("PoolsByDenom start", "denom", req.Denom)
	// Pre-scan map to aid debugging
	total := 0
	_ = k.PoolsMap.Walk(ctx, nil, func(id uint64, p whaleswapv1.Pool) (bool, error) {
		denA := ""
		denB := ""
		if len(p.Coins) == 2 {
			denA = p.Coins[0].Denom
			denB = p.Coins[1].Denom
		}
		logger.Info("PoolsByDenom pre-scan", "pool_id", id, "denoms", []string{denA, denB})
		total++
		return false, nil
	})
	logger.Info("PoolsByDenom map summary", "total_pools", total)
	results, pageRes, err := query.CollectionFilteredPaginate(ctx, k.PoolsMap, req.Pagination,
		func(key uint64, value whaleswapv1.Pool) (bool, error) {
			if len(value.Coins) != 2 {
				return false, nil
			}
			match := value.Coins[0].Denom == req.Denom || value.Coins[1].Denom == req.Denom
			logger.Info("PoolsByDenom eval", "pool_id", key, "denoms", []string{value.Coins[0].Denom, value.Coins[1].Denom}, "match", match)
			return match, nil
		},
		func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "PoolsByDenom paginate failed")
	}
	logger.Info("PoolsByDenom result", "count", len(results), "next_key", pageRes.GetNextKey() != nil, "total", pageRes.GetTotal())
	return &whaleswapv1.QueryPoolsByDenomResponse{Pools: results, Pagination: pageRes}, nil
}

// PoolBySharesDenom queries the pool that mints a specific shares denom.
//
// Semantics:
//   - Scans pools to find the one with matching shares_denom.
//   - Returns the first (and should be only) matching pool.
//   - Uses unpaginated scan since shares denoms are expected to be unique.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - SharesDenom must be non-empty.
//
// Returns:
//   - *whaleswapv1.QueryPoolBySharesDenomResponse with the matching pool.
//
// Errors are returned on invalid parameters, pagination failures, or when no matching pool found; no panics.
func (k Keeper) PoolBySharesDenom(ctx context.Context, req *whaleswapv1.QueryPoolBySharesDenomRequest) (*whaleswapv1.QueryPoolBySharesDenomResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolBySharesDenomRequest{}
	}
	if req.SharesDenom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "shares_denom required")
	}
	var matched *whaleswapv1.Pool
	_, _, err := query.CollectionPaginate(ctx, k.PoolsMap, nil, func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
		if value.SharesDenom == req.SharesDenom {
			v := value
			matched = &v
			return &v, nil
		}
		return nil, nil
	})
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "PoolBySharesDenom paginate failed")
	}
	if matched == nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "pool not found for shares denom %s", req.SharesDenom)
	}
	return &whaleswapv1.QueryPoolBySharesDenomResponse{Pool: matched}, nil
}

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

// PoolsByOwner queries pools where the owner holds non-zero shares balance.
//
// Semantics:
//   - Returns pools where the specified owner has a positive balance of pool shares.
//   - Uses bank module balance checks for each pool's shares denom.
//   - Falls back to filtered scan when no dedicated index exists.
//   - Results ordered by pool ID ascending.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Owner must be non-empty and a valid address.
//
// Returns:
//   - *whaleswapv1.QueryPoolsByOwnerResponse with matching pools and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) PoolsByOwner(ctx context.Context, req *whaleswapv1.QueryPoolsByOwnerRequest) (*whaleswapv1.QueryPoolsByOwnerResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolsByOwnerRequest{}
	}
	if req.Owner == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "owner required")
	}
	addrBz, err := k.accKeeper.AddressCodec().StringToBytes(req.Owner)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid owner: %s", req.Owner)
	}
	results, pageRes, perr := query.CollectionFilteredPaginate(ctx, k.PoolsMap, req.Pagination,
		func(key uint64, value whaleswapv1.Pool) (bool, error) {
			bal := k.bank.GetBalance(ctx, addrBz, value.SharesDenom).Amount
			return bal.IsPositive(), nil
		},
		func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
			v := value
			return &v, nil
		},
	)
	if perr != nil {
		return nil, cosmossdkerrors.Wrap(perr, "PoolsByOwner paginate failed")
	}
	return &whaleswapv1.QueryPoolsByOwnerResponse{Pools: results, Pagination: pageRes}, nil
}
