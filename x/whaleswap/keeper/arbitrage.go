package keeper

import (
	"context"
	"sort"

	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// ArbitragePool holds minimal pool info needed for building swap operations.
// We only store what's required to:
//  1. Build MsgMakeTrade operations (PoolID, denoms for direction)
//  2. Compute optimization bounds (reserves for max swap limits)
//
// Simulation uses actual MakeTrade with CacheContext, so AMM math uses
// live pool state, not these snapshots. Reserves here are only for bounds.
type ArbitragePool struct {
	PoolID   uint64
	Denom0   string // canonical order: denom0 < denom1
	Denom1   string
	Reserve0 math.Int // for bounds computation only
	Reserve1 math.Int // for bounds computation only
}

// ArbitrageContext holds the pool graph for arbitrage computation.
// Constructed once per triggering event; passed to optimizer.
type ArbitrageContext struct {
	Keeper     *Keeper          // keeper reference for MakeTrade calls
	Ctx        sdk.Context      // base context (will be cached for simulations)
	Trader     string           // address to use as trader for simulations
	Pools      []ArbitragePool  // ordered list of pools in the arbitrage graph
	PoolIndex  map[uint64]int   // pool_id -> index in Pools slice
	DenomPools map[string][]int // denom -> indices of pools containing it
	AllDenoms  []string         // all unique denoms in the graph
	RefDenom   string           // reference denom for profit measurement
}

// ArbitrageInput represents swap amounts for optimizer input.
// swapAmounts[i] corresponds to Pools[i]:
//   - positive: swap denom0 -> denom1 (sell denom0)
//   - negative: swap denom1 -> denom0 (sell denom1)
//   - zero: no swap on this pool
type ArbitrageInput struct {
	SwapAmounts []int64 // one per pool; signed to indicate direction
}

// ArbitrageResult holds the result of simulating swaps via MakeTrade.
type ArbitrageResult struct {
	Success       bool                              // true if MakeTrade succeeded
	TraderInputs  sdk.Coins                         // net debits from trader
	TraderOutputs sdk.Coins                         // net credits to trader
	Profit        math.Int                          // profit in RefDenom (outputs - inputs)
	Msg           *whaleswapv1.MsgMakeTrade         // the message used
	Response      *whaleswapv1.MsgMakeTradeResponse // response if successful
	Error         error                             // error if failed
}

// BuildArbitrageContext constructs the pool graph for arbitrage detection.
// Starting from the affected denoms (e.g., from a pool update), it expands
// the graph by `depth` hops to find related pools.
//
// depth=0: only pools directly containing the affected denoms
// depth=1: pools containing denoms from depth-0 pools, etc.
func (k *Keeper) BuildArbitrageContext(
	ctx sdk.Context,
	trader string,
	affectedDenoms []string,
	refDenom string,
	depth int,
) (*ArbitrageContext, error) {
	ac := &ArbitrageContext{
		Keeper:     k,
		Ctx:        ctx,
		Trader:     trader,
		Pools:      make([]ArbitragePool, 0),
		PoolIndex:  make(map[uint64]int),
		DenomPools: make(map[string][]int),
		AllDenoms:  make([]string, 0),
		RefDenom:   refDenom,
	}

	// BFS to expand the pool graph
	denomQueue := make([]string, len(affectedDenoms))
	copy(denomQueue, affectedDenoms)
	visitedDenoms := make(map[string]bool)
	visitedPools := make(map[uint64]bool)

	for d := 0; d <= depth; d++ {
		nextDenoms := make([]string, 0)

		for _, denom := range denomQueue {
			if visitedDenoms[denom] {
				continue
			}
			visitedDenoms[denom] = true
			ac.AllDenoms = append(ac.AllDenoms, denom)

			// Find all pools containing this denom
			pools, err := k.getPoolsByDenomInternal(ctx, denom)
			if err != nil {
				return nil, err
			}

			for _, pool := range pools {
				if visitedPools[pool.PoolId] {
					continue
				}
				visitedPools[pool.PoolId] = true

				ap, err := poolToArbitragePool(pool)
				if err != nil {
					continue // skip invalid pools
				}

				idx := len(ac.Pools)
				ac.Pools = append(ac.Pools, ap)
				ac.PoolIndex[pool.PoolId] = idx
				ac.DenomPools[ap.Denom0] = append(ac.DenomPools[ap.Denom0], idx)
				ac.DenomPools[ap.Denom1] = append(ac.DenomPools[ap.Denom1], idx)

				// Queue denoms for next depth iteration
				if !visitedDenoms[ap.Denom0] {
					nextDenoms = append(nextDenoms, ap.Denom0)
				}
				if !visitedDenoms[ap.Denom1] {
					nextDenoms = append(nextDenoms, ap.Denom1)
				}
			}
		}
		denomQueue = nextDenoms
	}

	// Prioritize pools for MaxPools selection
	prioritizePools(ac, affectedDenoms)

	return ac, nil
}

// getPoolsByDenomInternal retrieves all pools containing a denom (without pagination).
func (k *Keeper) getPoolsByDenomInternal(ctx context.Context, denom string) ([]whaleswapv1.Pool, error) {
	var results []whaleswapv1.Pool
	err := k.PoolsMap.Walk(ctx, nil, func(id uint64, pool whaleswapv1.Pool) (bool, error) {
		if len(pool.Coins) != 2 {
			return false, nil
		}
		if pool.Coins[0].Denom == denom || pool.Coins[1].Denom == denom {
			results = append(results, pool)
		}
		return false, nil
	})
	return results, err
}

// poolToArbitragePool converts a Pool to ArbitragePool snapshot.
func poolToArbitragePool(pool whaleswapv1.Pool) (ArbitragePool, error) {
	if len(pool.Coins) != 2 {
		return ArbitragePool{}, errInvalidPool
	}

	return ArbitragePool{
		PoolID:   pool.PoolId,
		Denom0:   pool.Coins[0].Denom,
		Denom1:   pool.Coins[1].Denom,
		Reserve0: pool.Coins[0].Amount,
		Reserve1: pool.Coins[1].Amount,
	}, nil
}

var errInvalidPool = &invalidPoolError{}

type invalidPoolError struct{}

func (e *invalidPoolError) Error() string { return "invalid pool" }

// poolScore holds a pool index and its priority score for sorting.
// Uses math.Int for consensus-safe arithmetic with large reserves.
type poolScore struct {
	idx   int
	score math.Int
}

// Score constants for pool prioritization (using math.Int for safety).
var (
	scoreAffectedDenom = math.NewInt(1000)
	scoreHubMultiplier = math.NewInt(10)
	scoreLiquidityCap  = math.NewInt(100)
	scoreLiquidityDiv  = math.NewInt(1_000_000)
)

// prioritizePools reorders pools by connectivity score for MaxPools selection.
// Priority (descending):
//  1. Pools containing affected denoms (price just moved → highest arb chance)
//  2. Pools with denoms appearing in multiple pools (hub denoms)
//  3. High liquidity (larger reserves = better execution)
//
// This is fully deterministic and consensus-safe using math.Int.
func prioritizePools(ac *ArbitrageContext, affectedDenoms []string) {
	if len(ac.Pools) <= 1 {
		return
	}

	// Build affected denom set for O(1) lookup
	affected := make(map[string]bool, len(affectedDenoms))
	for _, d := range affectedDenoms {
		affected[d] = true
	}

	// Precompute denom pool counts (how many pools each denom appears in)
	denomPoolCount := make(map[string]int)
	for _, p := range ac.Pools {
		denomPoolCount[p.Denom0]++
		denomPoolCount[p.Denom1]++
	}

	// Score each pool using math.Int for safe arithmetic
	scores := make([]poolScore, len(ac.Pools))
	for i, p := range ac.Pools {
		score := math.ZeroInt()

		// 1. Direct hit on affected denoms: highest priority (+1000)
		if affected[p.Denom0] || affected[p.Denom1] {
			score = score.Add(scoreAffectedDenom)
		}

		// 2. Hub bonus: denoms appearing in multiple pools (+10 per occurrence)
		count0 := denomPoolCount[p.Denom0]
		count1 := denomPoolCount[p.Denom1]
		if count0 > 1 {
			score = score.Add(scoreHubMultiplier.MulRaw(int64(count0)))
		}
		if count1 > 1 {
			score = score.Add(scoreHubMultiplier.MulRaw(int64(count1)))
		}

		// 3. Liquidity bonus: larger reserves (normalized, capped)
		totalReserve := p.Reserve0.Add(p.Reserve1)
		if totalReserve.IsPositive() {
			// Scale to reasonable range (divide by 1M, cap at 100)
			scaled := totalReserve.Quo(scoreLiquidityDiv)
			if scaled.GT(scoreLiquidityCap) {
				scaled = scoreLiquidityCap
			}
			score = score.Add(scaled)
		}

		// 4. Tiebreaker: use pool ID for determinism (lower ID = older pool)
		// Subtract pool ID / 1M (small adjustment for ordering)
		poolIdAdjust := math.NewInt(int64(p.PoolID)).Quo(scoreLiquidityDiv)
		score = score.Sub(poolIdAdjust)

		scores[i] = poolScore{idx: i, score: score}
	}

	// Sort by score descending (stable sort for determinism)
	sort.SliceStable(scores, func(i, j int) bool {
		return scores[i].score.GT(scores[j].score)
	})

	// Reorder pools according to priority
	newPools := make([]ArbitragePool, len(ac.Pools))
	for newIdx, ps := range scores {
		newPools[newIdx] = ac.Pools[ps.idx]
	}
	ac.Pools = newPools

	// Rebuild indices after reordering
	ac.PoolIndex = make(map[uint64]int, len(ac.Pools))
	ac.DenomPools = make(map[string][]int)
	for i, p := range ac.Pools {
		ac.PoolIndex[p.PoolID] = i
		ac.DenomPools[p.Denom0] = append(ac.DenomPools[p.Denom0], i)
		ac.DenomPools[p.Denom1] = append(ac.DenomPools[p.Denom1], i)
	}
}

// SimulateArbitrage runs MakeTrade with a CacheContext to evaluate swap amounts.
// Nothing is persisted; this is purely for objective function evaluation.
//
// swapAmounts[i] corresponds to ac.Pools[i]:
//   - positive: swap that many units of denom0 -> denom1
//   - negative: swap |amount| units of denom1 -> denom0
//   - zero: skip this pool
func (ac *ArbitrageContext) SimulateArbitrage(swapAmounts []int64) *ArbitrageResult {
	if len(swapAmounts) != len(ac.Pools) {
		return &ArbitrageResult{Success: false, Error: errInvalidInput}
	}

	// Build MsgMakeTrade from swap amounts
	msg := ac.buildMakeTradeMsg(swapAmounts)
	if msg == nil || len(msg.Operations) == 0 {
		return &ArbitrageResult{Success: false, Error: errNoOperations}
	}

	// Create cached context - changes will be discarded
	cacheCtx, _ := ac.Ctx.CacheContext()

	// Execute MakeTrade on cached context
	resp, err := ac.Keeper.MakeTrade(cacheCtx, msg)
	if err != nil {
		return &ArbitrageResult{
			Success: false,
			Msg:     msg,
			Error:   err,
		}
	}

	// Calculate profit in reference denom
	profit := resp.TraderOutputs.AmountOf(ac.RefDenom).Sub(resp.TraderInputs.AmountOf(ac.RefDenom))

	return &ArbitrageResult{
		Success:       true,
		TraderInputs:  resp.TraderInputs,
		TraderOutputs: resp.TraderOutputs,
		Profit:        profit,
		Msg:           msg,
		Response:      resp,
	}
}

// buildMakeTradeMsg constructs a MsgMakeTrade from swap amounts.
// During simulation, we use large MaxInput to allow trades to execute
// and then evaluate profitability from the response.
func (ac *ArbitrageContext) buildMakeTradeMsg(swapAmounts []int64) *whaleswapv1.MsgMakeTrade {
	operations := make([]whaleswapv1.TradeOperation, 0)
	maxInputs := sdk.NewCoins() // Use Coins to handle merging/sorting

	for i, amt := range swapAmounts {
		if amt == 0 {
			continue
		}

		pool := ac.Pools[i]
		var swapIn sdk.Coin

		if amt > 0 {
			// Sell denom0 for denom1
			swapIn = sdk.NewCoin(pool.Denom0, math.NewInt(amt))
		} else {
			// Sell denom1 for denom0
			swapIn = sdk.NewCoin(pool.Denom1, math.NewInt(-amt))
		}

		operations = append(operations, whaleswapv1.TradeOperation{
			Op: &whaleswapv1.TradeOperation_Swap{
				Swap: &whaleswapv1.SwapLeg{
					PoolId: pool.PoolID,
					SwapIn: swapIn,
				},
			},
		})

		// Accumulate max inputs (Coins handles merging same denom)
		maxInputs = maxInputs.Add(swapIn)
	}

	if len(operations) == 0 {
		return nil
	}

	// For simulation, allow all swap inputs as max debits.
	// Self-netting will cover most/all of these for circular trades.
	// The objective function evaluates net profit after.
	return &whaleswapv1.MsgMakeTrade{
		Trader:     ac.Trader,
		Operations: operations,
		MaxInput:   maxInputs,
		MinOutput:  []sdk.Coin{},
		Note:       "arb-simulation",
	}
}

var errInvalidInput = &simError{msg: "invalid input length"}
var errNoOperations = &simError{msg: "no operations generated"}

type simError struct{ msg string }

func (e *simError) Error() string { return e.msg }

// ObjectiveFunction returns a function suitable for a black-box optimizer.
// The optimizer should MAXIMIZE the returned value.
//
// Uses math.LegacyDec for consensus-safe arithmetic.
// Negative return values indicate unprofitable or failed swaps.
func (ac *ArbitrageContext) ObjectiveFunction() func([]math.LegacyDec) math.LegacyDec {
	// Cost penalty multiplier for non-circular arbitrage
	costPenalty := math.LegacyNewDec(1000)

	return func(amounts []math.LegacyDec) math.LegacyDec {
		if len(amounts) != len(ac.Pools) {
			return DecMinValue // invalid input
		}

		// Convert LegacyDec to int64 (truncate towards zero)
		intAmounts := make([]int64, len(amounts))
		for i, a := range amounts {
			intAmounts[i] = a.TruncateInt64()
		}

		result := ac.SimulateArbitrage(intAmounts)
		if result == nil || !result.Success {
			return DecMinValue
		}

		// For circular arbitrage, we expect:
		// - TraderInputs to be empty or zero (self-netting covers all)
		// - TraderOutputs to be positive in RefDenom (profit)

		profitDec := math.LegacyNewDecFromInt(result.Profit)

		// Penalize if there are any net inputs (trader has to pay)
		if !result.TraderInputs.IsZero() {
			// There are net debits - this isn't a pure circular arb
			// Return profit minus costs, heavily penalized
			totalCost := math.ZeroInt()
			for _, c := range result.TraderInputs {
				totalCost = totalCost.Add(c.Amount)
			}
			costDec := math.LegacyNewDecFromInt(totalCost)
			return profitDec.Sub(costDec.Mul(costPenalty))
		}

		return profitDec
	}
}

// GetAffectedDenomsFromPool extracts denoms from a pool that was updated.
func GetAffectedDenomsFromPool(pool *whaleswapv1.Pool) []string {
	if pool == nil || len(pool.Coins) != 2 {
		return nil
	}
	return []string{pool.Coins[0].Denom, pool.Coins[1].Denom}
}

// GetOptimizationBounds computes reasonable bounds for swap amounts.
// Uses math.LegacyDec for consensus-safe arithmetic.
// Limits to maxFraction of smaller reserve to avoid extreme price impact.
func (ac *ArbitrageContext) GetOptimizationBounds(maxFraction math.LegacyDec) OptimizationBounds {
	n := len(ac.Pools)
	bounds := OptimizationBounds{
		Lower: make([]math.LegacyDec, n),
		Upper: make([]math.LegacyDec, n),
	}

	for i, pool := range ac.Pools {
		// Max sell denom0: fraction of reserve0
		reserve0Dec := math.LegacyNewDecFromInt(pool.Reserve0)
		max0 := reserve0Dec.Mul(maxFraction)

		// Max sell denom1: fraction of reserve1
		reserve1Dec := math.LegacyNewDecFromInt(pool.Reserve1)
		max1 := reserve1Dec.Mul(maxFraction)

		bounds.Lower[i] = max1.Neg() // negative = sell denom1
		bounds.Upper[i] = max0       // positive = sell denom0
	}

	return bounds
}

// FindArbitrage runs the optimizer to find profitable arbitrage.
// Returns nil if no profitable arbitrage found.
// maxFraction should be a LegacyDec between 0 and 1 (e.g., 0.5 for 50%).
func (ac *ArbitrageContext) FindArbitrage(optimizer ArbitrageOptimizer, maxFraction math.LegacyDec) *ArbitrageResult {
	logger := ac.Keeper.Logger(ac.Ctx)

	if len(ac.Pools) == 0 {
		logger.Debug("arbitrage: no pools to optimize")
		return nil
	}

	// Collect pool IDs for logging
	poolIDs := make([]uint64, len(ac.Pools))
	for i, p := range ac.Pools {
		poolIDs[i] = p.PoolID
	}

	logger.Debug("arbitrage optimization starting",
		"pool_count", len(ac.Pools),
		"pool_ids", poolIDs,
		"denoms", ac.AllDenoms,
		"ref_denom", ac.RefDenom,
		"max_fraction", maxFraction.String(),
	)

	bounds := ac.GetOptimizationBounds(maxFraction)
	objective := ac.ObjectiveFunction()

	// Initial guess: all zeros (no swaps)
	initialGuess := make([]math.LegacyDec, len(ac.Pools))
	for i := range initialGuess {
		initialGuess[i] = DecZero
	}

	optimal, value, found := optimizer.Optimize(objective, bounds, initialGuess)

	// Log optimization metrics
	metrics := optimizer.GetMetrics()
	if metrics != nil {
		logger.Info("arbitrage optimization completed",
			"algorithm", metrics.Algorithm,
			"iterations", metrics.Iterations,
			"evaluations", metrics.Evaluations,
			"dimensions", metrics.Dimensions,
			"duration_ms", metrics.Duration.Milliseconds(),
			"best_value", metrics.BestValue.String(),
			"found", metrics.Found,
			"pool_ids", poolIDs,
			"denoms", ac.AllDenoms,
		)
	}

	if !found || !value.IsPositive() {
		logger.Debug("arbitrage: no profitable opportunity found",
			"found", found,
			"value", value.String(),
		)
		return nil
	}

	// Convert optimal LegacyDec to int64 and run final simulation
	intAmounts := make([]int64, len(optimal))
	for i, a := range optimal {
		intAmounts[i] = a.TruncateInt64()
	}

	result := ac.SimulateArbitrage(intAmounts)
	if result == nil || !result.Success || !result.Profit.IsPositive() {
		logger.Debug("arbitrage: final simulation failed or unprofitable",
			"success", result != nil && result.Success,
			"profit", func() string {
				if result != nil {
					return result.Profit.String()
				}
				return "nil"
			}(),
		)
		return nil
	}

	logger.Info("arbitrage opportunity found",
		"profit", result.Profit.String(),
		"ref_denom", ac.RefDenom,
		"trader_inputs", result.TraderInputs.String(),
		"trader_outputs", result.TraderOutputs.String(),
		"swap_amounts", intAmounts,
		"pool_ids", poolIDs,
	)

	return result
}

// BuildFinalMakeTradeMsg creates the MsgMakeTrade for execution with proper constraints.
// This should be called after FindArbitrage to create a msg with appropriate
// MaxInput and MinOutput based on the simulation result.
func (ac *ArbitrageContext) BuildFinalMakeTradeMsg(result *ArbitrageResult) *whaleswapv1.MsgMakeTrade {
	if result == nil || !result.Success || result.Msg == nil {
		return nil
	}

	// Copy operations from simulation msg
	msg := &whaleswapv1.MsgMakeTrade{
		Trader:     ac.Trader,
		Operations: result.Msg.Operations,
		Note:       "auto-arbitrage",
	}

	// For circular arbitrage, MaxInput should be empty (no net debits expected)
	// If the simulation showed inputs, include them as max (safety margin)
	if !result.TraderInputs.IsZero() {
		msg.MaxInput = result.TraderInputs
	}

	// MinOutput: require at least the profit we found (with small margin for rounding)
	if !result.TraderOutputs.IsZero() {
		// Apply 99% safety margin to account for any rounding differences
		minOut := make([]sdk.Coin, 0, len(result.TraderOutputs))
		for _, c := range result.TraderOutputs {
			reduced := c.Amount.MulRaw(99).QuoRaw(100)
			if reduced.IsPositive() {
				minOut = append(minOut, sdk.NewCoin(c.Denom, reduced))
			}
		}
		msg.MinOutput = minOut
	}

	return msg
}
