package keeper

import (
	"context"

	errorsmod "cosmossdk.io/errors"
	crontasktypes "dysonprotocol.com/x/crontask/types"
)

// Metrics returns the last-block crontask metrics singleton
func (q queryServer) Metrics(ctx context.Context, req *crontasktypes.QueryMetricsRequest) (*crontasktypes.QueryMetricsResponse, error) {
	metrics, err := q.k.GetMetrics(ctx)
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to get metrics")
	}
	return &crontasktypes.QueryMetricsResponse{Metrics: &metrics}, nil
}
