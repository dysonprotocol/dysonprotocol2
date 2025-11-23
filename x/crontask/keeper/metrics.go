package keeper

import (
	"context"
	"errors"

	"cosmossdk.io/collections"
	sdk "github.com/cosmos/cosmos-sdk/types"
	crontasktypes "dysonprotocol.com/x/crontask/types"
)

// GetMetrics returns the current metrics singleton. If not set, returns zero-value metrics.
func (k Keeper) GetMetrics(ctx context.Context) (crontasktypes.Metrics, error) {
	metrics, err := k.Metrics.Get(ctx)
	if err != nil {
		if errors.Is(err, collections.ErrNotFound) {
			return crontasktypes.Metrics{}, nil
		}
		return crontasktypes.Metrics{}, err
	}
	return metrics, nil
}

// SetMetrics persists the metrics singleton.
func (k Keeper) SetMetrics(ctx context.Context, m crontasktypes.Metrics) error {
	return k.Metrics.Set(ctx, m)
}

// AddMetricsForTask updates the metrics singleton with one executed task's data.
func (k Keeper) AddMetricsForTask(ctx context.Context, t crontasktypes.Task) error {
	metrics, err := k.GetMetrics(ctx)
	if err != nil {
		return err
	}

	// total gas
	metrics.ExecutedTotalGas += t.TaskGasConsumed

	// accumulate fees using sdk.Coins helpers
	metrics.ExecutedTotalFees = sdk.Coins(metrics.ExecutedTotalFees).Add(t.TaskGasFee)

	// counts
	metrics.ExecutedTaskCount += 1

	return k.SetMetrics(ctx, metrics)
}
