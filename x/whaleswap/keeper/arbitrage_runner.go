package keeper

import (
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// ArbitrageRunner handles detection and execution of arbitrage opportunities.
type ArbitrageRunner struct {
	keeper    *Keeper
	optimizer ArbitrageOptimizer
	// Config
	MaxDepth       int   // how many hops to expand pool graph
	MinProfitBasis int64 // minimum profit in basis points (1/10000) to execute
}

// NewArbitrageRunner creates an ArbitrageRunner with default settings.
func NewArbitrageRunner(keeper *Keeper) *ArbitrageRunner {
	return &ArbitrageRunner{
		keeper:         keeper,
		optimizer:      NewHybridOptimizer(),
		MaxDepth:       1,  // include pools 1 hop away from affected denoms
		MinProfitBasis: 10, // require at least 0.1% profit relative to trade size
	}
}

// WithOptimizer sets a custom optimizer.
func (ar *ArbitrageRunner) WithOptimizer(opt ArbitrageOptimizer) *ArbitrageRunner {
	ar.optimizer = opt
	return ar
}

// CheckAndExecuteArbitrage is the main entry point.
// Called after a pool-affecting message succeeds.
//
// Parameters:
//   - ctx: SDK context (will use CacheContext for simulations)
//   - trader: address to use for arbitrage trades
//   - affectedDenoms: denoms affected by the triggering event
//   - refDenom: denom to measure profit in (typically the chain's base denom)
//
// Returns:
//   - *ArbitrageResult if profitable arbitrage was found and executed
//   - nil if no profitable arbitrage found
//   - error only for unexpected failures (not for "no arb found")
func (ar *ArbitrageRunner) CheckAndExecuteArbitrage(
	ctx sdk.Context,
	trader string,
	affectedDenoms []string,
	refDenom string,
) (*ArbitrageResult, error) {
	logger := ar.keeper.ArbitrageLogger(ctx)
	logger.Debug("arbitrage check starting",
		"affected_denoms", affectedDenoms,
		"ref_denom", refDenom,
	)

	// Build the pool graph
	ac, err := ar.keeper.BuildArbitrageContext(ctx, trader, affectedDenoms, refDenom, ar.MaxDepth)
	if err != nil {
		logger.Error("failed to build arbitrage context", "error", err)
		return nil, err
	}

	if len(ac.Pools) < 2 {
		logger.Debug("not enough pools for arbitrage", "pool_count", len(ac.Pools))
		return nil, nil
	}

	logger.Debug("arbitrage context built",
		"pool_count", len(ac.Pools),
		"denom_count", len(ac.AllDenoms),
	)

	// Find arbitrage opportunity
	result := ac.FindArbitrage(ar.optimizer)
	if result == nil {
		logger.Debug("no profitable arbitrage found")
		return nil, nil
	}

	logger.Debug("arbitrage opportunity found",
		"profit", result.Profit.String(),
		"ref_denom", refDenom,
		"inputs", result.TraderInputs.String(),
		"outputs", result.TraderOutputs.String(),
	)

	// Validate minimum profit threshold
	if !ar.meetsMinProfit(result) {
		logger.Debug("arbitrage profit below threshold",
			"profit", result.Profit.String(),
			"threshold_basis", ar.MinProfitBasis,
		)
		return nil, nil
	}

	// Build final message with proper constraints
	finalMsg := ac.BuildFinalMakeTradeMsg(result)
	if finalMsg == nil {
		logger.Error("failed to build final arbitrage message")
		return nil, nil
	}

	// Execute the arbitrage (on real context, not cached)
	resp, err := ar.keeper.MakeTrade(ctx, finalMsg)
	if err != nil {
		logger.Error("arbitrage execution failed", "error", err)
		// Don't return error - arbitrage failure shouldn't fail the original tx
		return nil, nil
	}

	logger.Debug("arbitrage executed successfully",
		"trade_id", resp.TradeId,
		"trader_inputs", resp.TraderInputs.String(),
		"trader_outputs", resp.TraderOutputs.String(),
	)

	return &ArbitrageResult{
		Success:       true,
		TraderInputs:  resp.TraderInputs,
		TraderOutputs: resp.TraderOutputs,
		Profit:        resp.TraderOutputs.AmountOf(refDenom).Sub(resp.TraderInputs.AmountOf(refDenom)),
		Response:      resp,
	}, nil
}

// meetsMinProfit checks if the arbitrage meets minimum profit threshold.
// Uses math.Int for consensus-safe arithmetic.
func (ar *ArbitrageRunner) meetsMinProfit(result *ArbitrageResult) bool {
	if result == nil || !result.Success || !result.Profit.IsPositive() {
		return false
	}

	// Calculate total trade volume (sum of all outputs) using math.Int
	totalVolume := math.ZeroInt()
	for _, c := range result.TraderOutputs {
		totalVolume = totalVolume.Add(c.Amount)
	}

	if !totalVolume.IsPositive() {
		return false
	}

	// Profit must be at least MinProfitBasis/10000 of volume
	// minProfit = totalVolume * MinProfitBasis / 10000
	minProfit := totalVolume.MulRaw(ar.MinProfitBasis).QuoRaw(10000)
	return result.Profit.GTE(minProfit)
}

// SimulateOnly runs arbitrage detection without execution.
// Useful for queries or testing.
func (ar *ArbitrageRunner) SimulateOnly(
	ctx sdk.Context,
	trader string,
	affectedDenoms []string,
	refDenom string,
) (*ArbitrageResult, error) {
	ac, err := ar.keeper.BuildArbitrageContext(ctx, trader, affectedDenoms, refDenom, ar.MaxDepth)
	if err != nil {
		return nil, err
	}

	if len(ac.Pools) < 2 {
		return nil, nil
	}

	return ac.FindArbitrage(ar.optimizer), nil
}

// GetPoolDenomsFromMsg extracts affected denoms from a message if it affects pools.
// Returns nil if the message type doesn't affect pools.
func GetPoolDenomsFromMsg(msg sdk.Msg) []string {
	switch m := msg.(type) {
	case *whaleswapv1.MsgMakeTrade:
		// Extract all denoms from swap operations
		denoms := make(map[string]bool)
		for _, op := range m.Operations {
			if swap := op.GetSwap(); swap != nil {
				// SwapIn and SwapOut are value types; check if denom is set
				if swap.SwapIn.Denom != "" {
					denoms[swap.SwapIn.Denom] = true
				}
				if swap.SwapOut.Denom != "" {
					denoms[swap.SwapOut.Denom] = true
				}
			}
		}
		result := make([]string, 0, len(denoms))
		for d := range denoms {
			result = append(result, d)
		}
		return result

	case *whaleswapv1.MsgAddLiquidity:
		denoms := make([]string, 0, len(m.Amounts))
		for _, c := range m.Amounts {
			denoms = append(denoms, c.Denom)
		}
		return denoms

	case *whaleswapv1.MsgRemoveLiquidity:
		// Need to look up pool to get denoms - return nil for now
		// The caller can look up the pool if needed
		return nil

	case *whaleswapv1.MsgCreatePool:
		denoms := make([]string, 0, len(m.Coins))
		for _, c := range m.Coins {
			denoms = append(denoms, c.Denom)
		}
		return denoms

	default:
		return nil
	}
}

// ShouldCheckArbitrage returns true if the message type could create arbitrage opportunities.
func ShouldCheckArbitrage(msg sdk.Msg) bool {
	switch msg.(type) {
	case *whaleswapv1.MsgMakeTrade,
		*whaleswapv1.MsgAddLiquidity,
		*whaleswapv1.MsgCreatePool:
		return true
	default:
		return false
	}
}
