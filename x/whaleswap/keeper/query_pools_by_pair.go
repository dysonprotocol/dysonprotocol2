package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
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

