package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

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

