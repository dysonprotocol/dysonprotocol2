package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

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
