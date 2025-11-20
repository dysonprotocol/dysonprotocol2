package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// TradesByTaker queries all trades executed by a specific taker address.
//
// Semantics:
//   - Returns all trades where the specified address appears as the taker (trader).
//   - Uses TradesByTraderIndex with (trader_address, trade_id) keys for efficient lookup.
//   - Applies prefix filtering to iterate only trades for the specified trader.
//   - Supports pagination with consistent ordering by trade ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Taker address must be non-empty.
//
// Returns:
//   - *whaleswapv1.QueryTradesByTakerResponse with matching trades and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) TradesByTaker(ctx context.Context, req *whaleswapv1.QueryTradesByTakerRequest) (*whaleswapv1.QueryTradesByTakerResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesByTakerRequest{}
	}
	if req.Taker == "" {
		return nil, fmt.Errorf("taker required")
	}
	trader := req.Taker
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.TradesByTraderIndex,
		req.Pagination,
		func(key collections.Pair[string, uint64], id uint64) (*whaleswapv1.Trade, error) {
			k1, _ := key.K1(), key.K2()
			if k1 != trader {
				return nil, nil
			}
			v, err := k.TradesMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", id)
			}
			vv := v
			return &vv, nil
		},
		query.WithCollectionPaginationPairPrefix[string, uint64](trader),
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades by trader failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesByTakerResponse{Trades: trades, Pagination: pageRes}, nil
}

