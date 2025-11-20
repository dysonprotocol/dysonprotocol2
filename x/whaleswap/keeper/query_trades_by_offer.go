package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// TradesByOffer queries all trades involving a specific offer.
//
// Semantics:
//   - Returns all trades where the specified offer_id appears as a participant.
//   - Uses TradesByOfferIndex with (offer_id, trade_id) keys for efficient lookup.
//   - Applies prefix filtering to iterate only trades for the specified offer.
//   - Supports pagination with consistent ordering by trade ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - OfferId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryTradesByOfferResponse with matching trades and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) TradesByOffer(ctx context.Context, req *whaleswapv1.QueryTradesByOfferRequest) (*whaleswapv1.QueryTradesByOfferResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesByOfferRequest{}
	}
	if req.OfferId == 0 {
		return nil, fmt.Errorf("offer_id required")
	}
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.TradesByOfferIndex,
		req.Pagination,
		func(key collections.Pair[uint64, uint64], id uint64) (*whaleswapv1.Trade, error) {
			k1, _ := key.K1(), key.K2()
			if k1 != req.OfferId {
				return nil, nil
			}
			v, err := k.TradesMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", id)
			}
			vv := v
			return &vv, nil
		},
		query.WithCollectionPaginationPairPrefix[uint64, uint64](req.OfferId),
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades by offer failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesByOfferResponse{Trades: trades, Pagination: pageRes}, nil
}

