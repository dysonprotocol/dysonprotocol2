package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// AddressMetrics retrieves lifetime activity metrics for a specific address.
//
// Semantics:
//   - Reads pre-aggregated metrics from the address metrics store.
//   - Metrics are updated incrementally as transactions occur.
//   - Only coins with registered denom metadata are tracked.
//   - Returns zero values for addresses with no activity.
//
// Validation:
//   - Request must be non-nil.
//   - Address must be valid and non-empty.
//
// Returns:
//   - *whaleswapv1.QueryAddressMetricsResponse with stored AddressMetrics.
//
// Errors are returned on invalid request parameters; no panics.
func (k Keeper) AddressMetrics(ctx context.Context, req *whaleswapv1.QueryAddressMetricsRequest) (*whaleswapv1.QueryAddressMetricsResponse, error) {
	if req == nil || req.Address == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "address required")
	}

	// Validate address
	if _, err := sdk.AccAddressFromBech32(req.Address); err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid address: %s", req.Address)
	}

	// Get metrics from store (returns zero-value if not found)
	metrics, err := k.getOrCreateMetrics(ctx, req.Address)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "get metrics")
	}

	return &whaleswapv1.QueryAddressMetricsResponse{Metrics: metrics}, nil
}
