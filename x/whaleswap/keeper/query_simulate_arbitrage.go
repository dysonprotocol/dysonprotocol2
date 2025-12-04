package keeper

import (
	"context"
	"time"

	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// SimulateArbitrage handles the SimulateArbitrage query.
// Uses LIGHTNING algorithm to find multi-path arbitrage opportunities.
func (k Keeper) SimulateArbitrage(
	goCtx context.Context,
	req *whaleswapv1.QuerySimulateArbitrageRequest,
) (*whaleswapv1.QuerySimulateArbitrageResponse, error) {
	startTime := time.Now()

	if req == nil {
		return nil, errNilRequest
	}

	ctx := sdk.UnwrapSDKContext(goCtx)
	logger := k.ArbitrageLogger(ctx)

	// Check ArbitrageMode param - if DISABLED, return empty result
	params := k.GetParams(ctx)
	if params.ArbitrageMode == whaleswapv1.ArbitrageMode_ARBITRAGE_MODE_DISABLED {
		logger.Info("arbitrage mode is disabled")
		return &whaleswapv1.QuerySimulateArbitrageResponse{Found: false}, nil
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

	// Apply max_depth from request
	if req.MaxDepth > 0 {
		ac.MaxDepth = int(req.MaxDepth)
	}

	// Build response with context info
	resp := &whaleswapv1.QuerySimulateArbitrageResponse{
		Found:     false,
		PoolCount: int32(len(ac.Pools)),
		Denoms:    ac.AllDenoms,
		PoolIds:   make([]uint64, len(ac.Pools)),
	}

	for i, pool := range ac.Pools {
		resp.PoolIds[i] = pool.PoolID
	}

	if len(ac.Pools) < 2 {
		logger.Debug("SimulateArbitrage: not enough pools",
			"pool_count", len(ac.Pools),
			"duration_ms", time.Since(startTime).Milliseconds(),
		)
		return resp, nil
	}

	// Find arbitrage using LIGHTNING
	result := ac.FindArbitrage()

	if result == nil || !result.Success || !result.Profit.IsPositive() {
		logger.Debug("SimulateArbitrage: no profitable arbitrage",
			"duration_ms", time.Since(startTime).Milliseconds(),
		)
		return resp, nil
	}

	// Populate successful result
	resp.Found = true
	resp.Profit = result.Profit.String()
	resp.TraderInputs = result.TraderInputs
	resp.TraderOutputs = result.TraderOutputs

	// Extract swap amounts from the result message
	if result.Msg != nil {
		swapAmounts := make([]int64, len(ac.Pools)*2)
		for _, op := range result.Msg.Operations {
			if swap := op.GetSwap(); swap != nil {
				if idx, ok := ac.PoolIndex[swap.PoolId]; ok {
					pool := ac.Pools[idx]
					if swap.SwapIn.Denom == pool.Denom0 {
						swapAmounts[2*idx] += swap.SwapIn.Amount.Int64()
					} else {
						swapAmounts[2*idx+1] += swap.SwapIn.Amount.Int64()
					}
				}
			}
		}
		resp.SwapAmounts = swapAmounts
	}

	logger.Debug("SimulateArbitrage: found",
		"profit", resp.Profit,
		"ops", len(result.Msg.Operations),
		"duration_ms", time.Since(startTime).Milliseconds(),
	)

	return resp, nil
}

var errNilRequest = &simError{msg: "nil request"}
