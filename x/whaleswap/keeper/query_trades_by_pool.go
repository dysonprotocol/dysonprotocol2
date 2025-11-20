package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// TradesByPool queries all trades involving a specific AMM pool.
//
// Semantics:
//   - Returns all trades where the specified pool_id appears as a participant.
//   - Uses TradesByPoolIndex with (pool_id, trade_id) keys for efficient lookup.
//   - Applies prefix filtering to iterate only trades for the specified pool.
//   - Supports pagination with consistent ordering by trade ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - PoolId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryTradesByPoolResponse with matching trades and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) TradesByPool(ctx context.Context, req *whaleswapv1.QueryTradesByPoolRequest) (*whaleswapv1.QueryTradesByPoolResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesByPoolRequest{}
	}
	if req.PoolId == 0 {
		return nil, fmt.Errorf("pool_id required")
	}
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.TradesByPoolIndex,
		req.Pagination,
		func(key collections.Pair[uint64, uint64], id uint64) (*whaleswapv1.Trade, error) {
			k1, _ := key.K1(), key.K2()
			if k1 != req.PoolId {
				return nil, nil
			}
			v, err := k.TradesMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", id)
			}
			vv := v
			return &vv, nil
		},
		// Iterate only keys with pool_id prefix to avoid scanning unrelated pairs and to
		// ensure next_key encodes a valid pair key for subsequent pages.
		query.WithCollectionPaginationPairPrefix[uint64, uint64](req.PoolId),
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades by pool failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesByPoolResponse{Trades: trades, Pagination: pageRes}, nil
}

