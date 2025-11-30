package keeper

import (
	"context"

	"cosmossdk.io/math"
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

	// Parse max_fraction (default to 0.1 if not specified)
	maxFraction := 0.1
	if req.MaxFraction != "" {
		dec, err := math.LegacyNewDecFromStr(req.MaxFraction)
		if err != nil {
			return nil, err
		}
		f, _ := dec.Float64()
		maxFraction = f
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
	result := ac.FindArbitrage(optimizer, maxFraction)

	if result == nil || !result.Success || !result.Profit.IsPositive() {
		return resp, nil
	}

	// Populate successful result
	resp.Found = true
	resp.Profit = result.Profit.String()
	resp.TraderInputs = result.TraderInputs
	resp.TraderOutputs = result.TraderOutputs

	// Extract swap amounts from the result message
	if result.Msg != nil {
		swapAmounts := make([]int64, len(ac.Pools))
		for _, op := range result.Msg.Operations {
			if swap := op.GetSwap(); swap != nil {
				// Find pool index
				if idx, ok := ac.PoolIndex[swap.PoolId]; ok {
					pool := ac.Pools[idx]
					// Determine direction from SwapIn denom
					if swap.SwapIn.Denom == pool.Denom0 {
						swapAmounts[idx] = swap.SwapIn.Amount.Int64()
					} else {
						swapAmounts[idx] = -swap.SwapIn.Amount.Int64()
					}
				}
			}
		}
		resp.SwapAmounts = swapAmounts
	}

	return resp, nil
}

var errNilRequest = &simError{msg: "nil request"}
