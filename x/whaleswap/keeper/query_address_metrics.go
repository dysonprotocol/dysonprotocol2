package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
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

// AddressMetricsAll paginates over every stored address metrics record.
// Results are ordered lexicographically by address and should only be used for
// analytics or administrative tooling because the dataset can be large.
func (k Keeper) AddressMetricsAll(ctx context.Context, req *whaleswapv1.QueryAddressMetricsAllRequest) (*whaleswapv1.QueryAddressMetricsAllResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryAddressMetricsAllRequest{}
	}

	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.AddressMetricsMap,
		req.Pagination,
		func(_ string, value whaleswapv1.AddressMetrics) (*whaleswapv1.AddressMetrics, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate address metrics")
	}
	if results == nil {
		results = make([]*whaleswapv1.AddressMetrics, 0)
	}

	return &whaleswapv1.QueryAddressMetricsAllResponse{
		Metrics:    results,
		Pagination: pageRes,
	}, nil
}

// shouldTrackDenom returns true if the denom should be tracked in metrics.
// Tracks denoms with metadata to prevent spam.
func (k Keeper) shouldTrackDenom(ctx context.Context, denom string) bool {
	_, found := k.bank.GetDenomMetaData(ctx, denom)
	return found
}

// filterCoinsWithMetadata returns only coins that have denom metadata registered.
func (k Keeper) filterCoinsWithMetadata(ctx context.Context, coins sdk.Coins) sdk.Coins {
	filtered := sdk.NewCoins()
	for _, coin := range coins {
		if k.shouldTrackDenom(ctx, coin.Denom) {
			filtered = filtered.Add(coin)
		}
	}
	return filtered
}
