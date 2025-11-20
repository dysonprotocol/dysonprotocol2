package keeper

import (
	"context"
	"fmt"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

// Trade queries a single trade by ID.
//
// Semantics:
//   - Retrieves complete trade data including participants, amounts, and operations.
//   - Returns the full Trade structure with all metadata and transaction details.
//
// Validation:
//   - Request can be nil but TradeId must be positive.
//   - TradeId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryTradeResponse containing the trade data.
//
// Errors are returned on invalid request parameters or when trade not found; no panics.
func (k Keeper) Trade(ctx context.Context, req *whaleswapv1.QueryTradeRequest) (*whaleswapv1.QueryTradeResponse, error) {
	if req == nil || req.TradeId == 0 {
		return nil, fmt.Errorf("trade_id required")
	}
	v, err := k.TradesMap.Get(ctx, req.TradeId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", req.TradeId)
	}
	vv := v
	return &whaleswapv1.QueryTradeResponse{Trade: &vv}, nil
}

