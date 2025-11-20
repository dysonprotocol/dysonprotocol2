package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// Trades lists trades with optional denom filters and pagination.
//
// Semantics:
//   - Returns trades filtered by sent_denom and/or received_denom if specified.
//   - Uses filtered pagination over primary TradesMap for flexibility.
//   - Checks TotalSent and TotalReceived coin arrays for denom presence.
//   - Supports pagination with consistent ordering by trade ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Denom filters are optional but must be valid denomination strings if provided.
//
// Returns:
//   - *whaleswapv1.QueryTradesResponse with matching trades and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) Trades(ctx context.Context, req *whaleswapv1.QueryTradesRequest) (*whaleswapv1.QueryTradesResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesRequest{}
	}
	sentDenom := req.SentDenom
	receivedDenom := req.ReceivedDenom
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		k.TradesMap,
		req.Pagination,
		func(_ uint64, value whaleswapv1.Trade) (bool, error) {
			if sentDenom != "" && value.TotalSent.AmountOf(sentDenom).IsZero() {
				return false, nil
			}
			if receivedDenom != "" && value.TotalReceived.AmountOf(receivedDenom).IsZero() {
				return false, nil
			}
			return true, nil
		},
		func(_ uint64, value whaleswapv1.Trade) (*whaleswapv1.Trade, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesResponse{Trades: trades, Pagination: pageRes}, nil
}

