package keeper

import (
	"context"
	"errors"

	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// SimulateArbitrageInternal detects arbitrage opportunities.
// Used by both the query handler and the auto-arbitrage interceptor.
// Returns the response directly; caller can use Operations for execution.
func (k Keeper) SimulateArbitrageInternal(
	ctx sdk.Context,
	trader string,
	affectedDenoms []string,
	refDenom string,
) (*whaleswapv1.QuerySimulateArbitrageResponse, error) {
	params := k.GetParams(ctx)
	if params.ArbitrageMode == whaleswapv1.ArbitrageMode_ARBITRAGE_MODE_DISABLED {
		return &whaleswapv1.QuerySimulateArbitrageResponse{}, nil
	}

	// Use params.ArbitrageRefDenom as default
	if refDenom == "" {
		refDenom = params.ArbitrageRefDenom
	}
	if refDenom == "" {
		return &whaleswapv1.QuerySimulateArbitrageResponse{}, nil
	}

	ac, err := k.BuildArbitrageContext(ctx, trader, affectedDenoms, refDenom)
	if err != nil {
		return nil, err
	}

	// Build base response
	resp := &whaleswapv1.QuerySimulateArbitrageResponse{
		Trader:    trader,
		PoolCount: int32(len(ac.Pools)),
		Denoms:    ac.AllDenoms,
		PoolIds:   make([]uint64, len(ac.Pools)),
	}
	for i, pool := range ac.Pools {
		resp.PoolIds[i] = pool.PoolID
	}

	if len(ac.Pools) < 2 {
		return resp, nil
	}
	if _, ok := ac.DenomPools[refDenom]; !ok {
		return resp, nil
	}

	result := ac.FindArbitrage()
	if result == nil || !result.Success || !result.Profit.IsPositive() {
		return resp, nil
	}

	resp.Found = true
	resp.Profit = result.Profit.String()
	resp.TraderInputs = result.TraderInputs
	resp.TraderOutputs = result.TraderOutputs
	if result.Msg != nil {
		resp.Operations = result.Msg.Operations
	}
	return resp, nil
}

// SimulateArbitrage handles the SimulateArbitrage query.
func (k Keeper) SimulateArbitrage(
	goCtx context.Context,
	req *whaleswapv1.QuerySimulateArbitrageRequest,
) (*whaleswapv1.QuerySimulateArbitrageResponse, error) {
	if req == nil {
		return nil, errNilRequest
	}
	return k.SimulateArbitrageInternal(
		sdk.UnwrapSDKContext(goCtx),
		req.Trader,
		req.AffectedDenoms,
		req.RefDenom,
	)
}

var errNilRequest = errors.New("nil request")
