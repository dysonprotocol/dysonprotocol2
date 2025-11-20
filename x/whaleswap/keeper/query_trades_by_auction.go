package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// TradesByAuction queries all trades involving auction redemptions for a specific auction.
//
// Semantics:
//   - Returns all trades where the specified auction_id appears as a participant.
//   - Uses TradesByAuctionIndex with (auction_id, trade_id) keys for efficient lookup.
//   - Applies prefix filtering to iterate only trades for the specified auction.
//   - Supports pagination with consistent ordering by trade ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - AuctionId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryTradesByAuctionResponse with matching trades and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) TradesByAuction(ctx context.Context, req *whaleswapv1.QueryTradesByAuctionRequest) (*whaleswapv1.QueryTradesByAuctionResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesByAuctionRequest{}
	}
	if req.AuctionId == 0 {
		return nil, fmt.Errorf("auction_id required")
	}
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.TradesByAuctionIndex,
		req.Pagination,
		func(key collections.Pair[uint64, uint64], id uint64) (*whaleswapv1.Trade, error) {
			k1, _ := key.K1(), key.K2()
			if k1 != req.AuctionId {
				return nil, nil
			}
			v, err := k.TradesMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", id)
			}
			vv := v
			return &vv, nil
		},
		query.WithCollectionPaginationPairPrefix[uint64, uint64](req.AuctionId),
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades by auction failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesByAuctionResponse{Trades: trades, Pagination: pageRes}, nil
}

