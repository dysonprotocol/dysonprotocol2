package keeper

import (
	"cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// ArbitrageRunner handles detection and execution of arbitrage opportunities.
// Uses the LIGHTNING algorithm which handles multi-path optimization internally.
type ArbitrageRunner struct {
	keeper *Keeper
	// Config
	MaxDepth       int   // how many hops to expand pool graph
	MinProfitBasis int64 // minimum profit in basis points (1/10000) to execute
}

// NewArbitrageRunner creates an ArbitrageRunner with default settings.
func NewArbitrageRunner(keeper *Keeper) *ArbitrageRunner {
	return &ArbitrageRunner{
		keeper:         keeper,
		MaxDepth:       1,  // include pools 1 hop away from affected denoms
		MinProfitBasis: 10, // require at least 0.1% profit relative to trade size
	}
}

// CheckAndExecuteArbitrage is the main entry point.
// Called after a pool-affecting message succeeds.
// Uses LIGHTNING algorithm to find and execute multi-path arbitrage.
//
// Returns:
//   - totalProfit: profit from arbitrage
//   - execCount: number of trades executed (0 or 1)
//   - error only for unexpected failures
func (ar *ArbitrageRunner) CheckAndExecuteArbitrage(
	ctx sdk.Context,
	trader string,
	affectedDenoms []string,
	refDenom string,
) (totalProfit math.Int, execCount int, err error) {
	logger := ar.keeper.ArbitrageLogger(ctx)
	totalProfit = math.ZeroInt()

	logger.Debug("arbitrage check starting",
		"affected_denoms", affectedDenoms,
		"ref_denom", refDenom,
	)

	// Build the pool graph
	ac, err := ar.keeper.BuildArbitrageContext(ctx, trader, affectedDenoms, refDenom, ar.MaxDepth)
	if err != nil {
		logger.Error("failed to build arbitrage context", "error", err)
		return totalProfit, execCount, err
	}

	if len(ac.Pools) < 2 {
		logger.Debug("not enough pools for arbitrage", "pool_count", len(ac.Pools))
		return totalProfit, execCount, nil
	}

	logger.Debug("arbitrage context built",
		"pool_count", len(ac.Pools),
		"denom_count", len(ac.AllDenoms),
	)

	// LIGHTNING finds all profitable paths and returns combined result
	result := ac.FindArbitrage()
	if result == nil {
		logger.Debug("no arbitrage opportunity found")
		return totalProfit, execCount, nil
	}

	if !result.Success || !result.Profit.IsPositive() {
		logger.Debug("arbitrage not profitable",
			"success", result.Success,
			"profit", result.Profit.String(),
		)
		return totalProfit, execCount, nil
	}

	// Check minimum profit threshold
	if !ar.meetsMinProfit(result) {
		logger.Debug("arbitrage below minimum profit threshold",
			"profit", result.Profit.String(),
		)
		return totalProfit, execCount, nil
	}

	// Execute the arbitrage trade
	resp, execErr := ar.keeper.MakeTrade(ctx, result.Msg)
	if execErr != nil {
		logger.Error("arbitrage execution failed", "error", execErr)
		return totalProfit, execCount, nil
	}

	profit := resp.TraderOutputs.AmountOf(refDenom).Sub(resp.TraderInputs.AmountOf(refDenom))
	totalProfit = profit
	execCount = 1

	logger.Debug("arbitrage executed",
		"trade_id", resp.TradeId,
		"profit", profit.String(),
		"operations", len(result.Msg.Operations),
		"swaps", FormatSwaps(result.Msg.Operations),
	)

	return totalProfit, execCount, nil
}

// meetsMinProfit checks if the arbitrage meets minimum profit threshold.
func (ar *ArbitrageRunner) meetsMinProfit(result *ArbitrageResult) bool {
	if result == nil || !result.Success || !result.Profit.IsPositive() {
		return false
	}

	// Calculate total trade volume
	totalVolume := math.ZeroInt()
	for _, c := range result.TraderOutputs {
		totalVolume = totalVolume.Add(c.Amount)
	}

	if !totalVolume.IsPositive() {
		return false
	}

	// Profit must be at least MinProfitBasis/10000 of volume
	minProfit := totalVolume.MulRaw(ar.MinProfitBasis).QuoRaw(10000)

	return result.Profit.GTE(minProfit)
}
