package keeper

import (
	"context"

	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// SimulateArbitrage handles the SimulateArbitrage query.
// It builds an arbitrage context, runs the optimizer, and returns the simulated result.
func (k Keeper) SimulateArbitrage(
	goCtx context.Context,
	req *whaleswapv1.QuerySimulateArbitrageRequest,
) (*whaleswapv1.QuerySimulateArbitrageResponse, error) {
	if req == nil {
		return nil, errNilRequest
	}

	ctx := sdk.UnwrapSDKContext(goCtx)

	// Check ArbitrageMode param - if DISABLED, return empty result immediately
	params := k.GetParams(ctx)
	if params.ArbitrageMode == whaleswapv1.ArbitrageMode_ARBITRAGE_MODE_DISABLED {
		k.Logger(ctx).Info("arbitrage mode is disabled, returning empty result", "arbitrage_mode", params.ArbitrageMode)
		return &whaleswapv1.QuerySimulateArbitrageResponse{
			Found: false,
		}, nil
	}

	// Default depth to 1 if not specified
	depth := int(req.Depth)
	if depth < 0 {
		depth = 0
	}

	// Build arbitrage context
	ac, err := k.BuildArbitrageContext(ctx, req.Trader, req.AffectedDenoms, req.RefDenom, depth)
	if err != nil {
		return nil, err
	}

	// Build response with context info
	resp := &whaleswapv1.QuerySimulateArbitrageResponse{
		Found:     false,
		PoolCount: int32(len(ac.Pools)),
		Denoms:    ac.AllDenoms,
		PoolIds:   make([]uint64, len(ac.Pools)),
	}

	// Copy pool IDs
	for i, pool := range ac.Pools {
		resp.PoolIds[i] = pool.PoolID
	}

	// Need at least 2 pools for arbitrage
	if len(ac.Pools) < 2 {
		return resp, nil
	}

	// Find arbitrage using default optimizer
	optimizer := NewHybridOptimizer()
	result := ac.FindArbitrage(optimizer)

	if result == nil || !result.Success || !result.Profit.IsPositive() {
		return resp, nil
	}

	// Populate successful result
	resp.Found = true
	resp.Profit = result.Profit.String()
	resp.TraderInputs = result.TraderInputs
	resp.TraderOutputs = result.TraderOutputs

	// Extract swap amounts from the result message
	// Format: 2 values per pool [sell_denom0, sell_denom1, ...]
	if result.Msg != nil {
		swapAmounts := make([]int64, len(ac.Pools)*2)
		for _, op := range result.Msg.Operations {
			if swap := op.GetSwap(); swap != nil {
				// Find pool index
				if idx, ok := ac.PoolIndex[swap.PoolId]; ok {
					pool := ac.Pools[idx]
					// Determine which dimension based on SwapIn denom
					if swap.SwapIn.Denom == pool.Denom0 {
						// Selling denom0 → dimension 2*idx
						swapAmounts[2*idx] += swap.SwapIn.Amount.Int64()
					} else {
						// Selling denom1 → dimension 2*idx+1
						swapAmounts[2*idx+1] += swap.SwapIn.Amount.Int64()
					}
				}
			}
		}
		resp.SwapAmounts = swapAmounts
	}

	return resp, nil
}

var errNilRequest = &simError{msg: "nil request"}
