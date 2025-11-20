package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// Pools lists all AMM pools with pagination.
//
// Behavior:
//   - Returns all pools in the system with no filtering.
//   - Uses direct pagination over the primary PoolsMap.
//   - Results ordered by pool ID ascending.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//
// Returns:
//   - *whaleswapv1.QueryPoolsResponse with pool list and pagination metadata.
//
// Errors are returned on pagination failures; no panics.
func (k Keeper) Pools(ctx context.Context, req *whaleswapv1.QueryPoolsRequest) (*whaleswapv1.QueryPoolsResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolsRequest{}
	}
	results, pageRes, err := query.CollectionPaginate(ctx, k.PoolsMap, req.Pagination, func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
		v := value
		return &v, nil
	})
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate pools failed")
	}
	return &whaleswapv1.QueryPoolsResponse{Pools: results, Pagination: pageRes}, nil
}

