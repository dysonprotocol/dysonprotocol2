package keeper

import (
	"context"
	"fmt"
	"sort"

	"cosmossdk.io/log"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// ArbitragePool holds minimal pool info needed for building swap operations.
// We only store what's required to:
//  1. Build MsgMakeTrade operations (PoolID, denoms for direction)
//  2. Compute optimization bounds (reserves for max swap limits)
//  3. Compute closed-form arbitrage estimates (fee rates)
//
// Simulation uses actual MakeTrade with CacheContext, so AMM math uses
// live pool state, not these snapshots. Reserves here are only for bounds.
type ArbitragePool struct {
	PoolID   uint64
	Denom0   string // canonical order: denom0 < denom1
	Denom1   string
	Reserve0 math.Int       // for bounds computation only
	Reserve1 math.Int       // for bounds computation only
	Fee0     math.LegacyDec // fee rate when selling denom0 (typically 0.001-0.003)
	Fee1     math.LegacyDec // fee rate when selling denom1
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
	arbPath    []floodStep      // path from FLOOD for ordered operation generation
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

	// Log the built context
	logger := k.ArbitrageLogger(ctx)
	poolIDs := make([]uint64, len(ac.Pools))
	for i, p := range ac.Pools {
		poolIDs[i] = p.PoolID
	}
	logger.Debug("arbitrage context built",
		"pool_count", len(ac.Pools),
		"pool_ids", poolIDs,
		"all_denoms", ac.AllDenoms,
		"ref_denom", refDenom,
		"affected_denoms", affectedDenoms,
		"depth", depth,
	)

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

	// Default fee rate if not specified (0.1% = 0.001)
	defaultFee := math.LegacyNewDecWithPrec(1, 3)
	fee0, fee1 := defaultFee, defaultFee

	// Extract fee rates from pool config
	for _, fr := range pool.FeeRate {
		if fr.Denom == pool.Coins[0].Denom {
			fee0 = fr.Amount
		} else if fr.Denom == pool.Coins[1].Denom {
			fee1 = fr.Amount
		}
	}

	return ArbitragePool{
		PoolID:   pool.PoolId,
		Denom0:   pool.Coins[0].Denom,
		Denom1:   pool.Coins[1].Denom,
		Reserve0: pool.Coins[0].Amount,
		Reserve1: pool.Coins[1].Amount,
		Fee0:     fee0,
		Fee1:     fee1,
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
// swapAmounts has 2*len(Pools) elements (2 per pool):
//   - swapAmounts[2*i]:   amount of denom0 to sell on pool i (buy denom1)
//   - swapAmounts[2*i+1]: amount of denom1 to sell on pool i (buy denom0)
//
// Both directions can be non-zero for the same pool - MakeTrade handles
// multiple operations and nets them at the end.
func (ac *ArbitrageContext) SimulateArbitrage(swapAmounts []int64) *ArbitrageResult {
	expectedLen := len(ac.Pools) * 2
	if len(swapAmounts) != expectedLen {
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
		logger := ac.Keeper.Logger(ac.Ctx)
		logger.Debug("SimulateArbitrage MakeTrade failed",
			"error", err.Error(),
			"trader", msg.Trader,
			"operations_count", len(msg.Operations),
			"feature", "arbitrage",
		)
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
// If arbPath is set (from FLOOD), operations are generated in path order for proper
// sequential execution. Otherwise, falls back to pool-index order.
// swapAmounts has 2 entries per pool: [sell_denom0, sell_denom1].
func (ac *ArbitrageContext) buildMakeTradeMsg(swapAmounts []int64) *whaleswapv1.MsgMakeTrade {
	logger := ac.Keeper.ArbitrageLogger(ac.Ctx)
	operations := make([]whaleswapv1.TradeOperation, 0)

	// If we have a path from FLOOD, generate operations in path order
	// Must recompute cascading amounts using TRUNCATED values to avoid rounding shortfalls
	if len(ac.arbPath) > 0 {
		logger.Debug("buildMakeTradeMsg using path order", "path_len", len(ac.arbPath))

		// Start with the first step's amount
		currentAmount := ac.arbPath[0].amount
		if currentAmount.IsNil() || currentAmount.LTE(DecZero) {
			currentAmount = math.LegacyNewDec(100)
		}

		for i, step := range ac.arbPath {
			if step.poolIdx < 0 || step.poolIdx >= len(ac.Pools) {
				continue
			}
			pool := ac.Pools[step.poolIdx]

			// Truncate BEFORE creating the swap operation
			swapInAmt := currentAmount.TruncateInt()
			if !swapInAmt.IsPositive() {
				continue
			}

			var swapIn sdk.Coin
			var rIn, rOut, fee math.LegacyDec

			if step.sellDenom0 {
				swapIn = sdk.NewCoin(pool.Denom0, swapInAmt)
				rIn = math.LegacyNewDecFromInt(pool.Reserve0)
				rOut = math.LegacyNewDecFromInt(pool.Reserve1)
				if !pool.Fee0.IsNil() {
					fee = pool.Fee0
				} else {
					fee = DecZero
				}
			} else {
				swapIn = sdk.NewCoin(pool.Denom1, swapInAmt)
				rIn = math.LegacyNewDecFromInt(pool.Reserve1)
				rOut = math.LegacyNewDecFromInt(pool.Reserve0)
				if !pool.Fee1.IsNil() {
					fee = pool.Fee1
				} else {
					fee = DecZero
				}
			}

			operations = append(operations, whaleswapv1.TradeOperation{
				Op: &whaleswapv1.TradeOperation_Swap{
					Swap: &whaleswapv1.SwapLeg{
						PoolId: pool.PoolID,
						SwapIn: swapIn,
					},
				},
			})

			logger.Debug("buildMakeTradeMsg path step",
				"step", i,
				"pool_id", pool.PoolID,
				"sell_denom0", step.sellDenom0,
				"swap_in", swapIn.String(),
			)

			// Compute output for next step using the TRUNCATED input amount
			if i < len(ac.arbPath)-1 && !rIn.IsZero() && !rOut.IsZero() {
				truncatedIn := math.LegacyNewDecFromInt(swapInAmt)
				gamma := DecOne.Sub(fee)
				effectiveIn := truncatedIn.Mul(gamma)
				currentAmount = rOut.Mul(effectiveIn).Quo(rIn.Add(effectiveIn))
			}
		}

		// Keep path for subsequent simulations (cleared by FindArbitrage after final execution)
	} else {
		// Fallback: pool-index order (for optimizer probes)
		for i, pool := range ac.Pools {
			sellDenom0 := swapAmounts[2*i]
			sellDenom1 := swapAmounts[2*i+1]

			if sellDenom0 > 0 {
				swapIn := sdk.NewCoin(pool.Denom0, math.NewInt(sellDenom0))
				operations = append(operations, whaleswapv1.TradeOperation{
					Op: &whaleswapv1.TradeOperation_Swap{
						Swap: &whaleswapv1.SwapLeg{
							PoolId: pool.PoolID,
							SwapIn: swapIn,
						},
					},
				})
			}
			if sellDenom1 > 0 {
				swapIn := sdk.NewCoin(pool.Denom1, math.NewInt(sellDenom1))
				operations = append(operations, whaleswapv1.TradeOperation{
					Op: &whaleswapv1.TradeOperation_Swap{
						Swap: &whaleswapv1.SwapLeg{
							PoolId: pool.PoolID,
							SwapIn: swapIn,
						},
					},
				})
			}
		}
	}

	if len(operations) == 0 {
		return nil
	}

	// For circular arbitrage: MaxInput=nil enforces that net debits must be zero.
	// Self-netting handles intermediate tokens - a true circular trade has no net inputs.
	return &whaleswapv1.MsgMakeTrade{
		Trader:     ac.Trader,
		Operations: operations,
		MaxInput:   nil, // Enforce circularity: only zero net-input trades succeed
		MinOutput:  []sdk.Coin{},
		Note:       "",
	}
}

var errInvalidInput = &simError{msg: "invalid input length"}
var errNoOperations = &simError{msg: "no operations generated"}

type simError struct{ msg string }

func (e *simError) Error() string { return e.msg }

// ObjectiveFunction returns a function suitable for a black-box optimizer.
// The optimizer should MAXIMIZE the returned value.
//
// Input has 2*N dimensions (2 per pool):
//   - amounts[2*i]:   amount of denom0 to sell on pool i
//   - amounts[2*i+1]: amount of denom1 to sell on pool i
//
// Uses math.LegacyDec for consensus-safe arithmetic.
// Negative return values indicate unprofitable or failed swaps.
func (ac *ArbitrageContext) ObjectiveFunction() func([]math.LegacyDec) math.LegacyDec {
	expectedLen := len(ac.Pools) * 2

	return func(amounts []math.LegacyDec) math.LegacyDec {
		if len(amounts) != expectedLen {
			return DecMinValue // invalid input
		}

		// Convert LegacyDec to int64 (truncate towards zero, ensure non-negative)
		intAmounts := make([]int64, len(amounts))
		for i, a := range amounts {
			val := a.TruncateInt64()
			if val < 0 {
				val = 0 // bounds should prevent this, but be safe
			}
			intAmounts[i] = val
		}

		result := ac.SimulateArbitrage(intAmounts)
		if result == nil || !result.Success {
			return DecMinValue
		}

		// For circular arbitrage, we expect:
		// - TraderInputs to be empty or zero (self-netting covers all)
		// - TraderOutputs to be positive in RefDenom (profit)

		// Return raw profit — no penalty for non-circular solutions.
		// This gives Nelder-Mead a smooth, honest profit landscape.
		// Circularity is enforced later in BuildFinalMakeTradeMsg.
		// Net inputs are subtracted from profit in SimulateTrade already,
		// so this naturally penalizes non-circular trades without cliffs.
		return math.LegacyNewDecFromInt(result.Profit)
	}
}

// GetAffectedDenomsFromPool extracts denoms from a pool that was updated.
func GetAffectedDenomsFromPool(pool *whaleswapv1.Pool) []string {
	if pool == nil || len(pool.Coins) != 2 {
		return nil
	}
	return []string{pool.Coins[0].Denom, pool.Coins[1].Denom}
}

// GetOptimizationBounds computes bounds for swap amounts based on pool reserves.
// Returns 2*N bounds (2 per pool):
//   - bounds[2*i]:   [0, reserve0] for selling denom0 on pool i
//   - bounds[2*i+1]: [0, reserve1] for selling denom1 on pool i
//
// Uses full reserves as bounds - MakeTrade will naturally reject impossible swaps,
// and the constant product formula handles slippage.
func (ac *ArbitrageContext) GetOptimizationBounds() OptimizationBounds {
	n := len(ac.Pools) * 2
	bounds := OptimizationBounds{
		Lower: make([]math.LegacyDec, n),
		Upper: make([]math.LegacyDec, n),
	}

	for i, pool := range ac.Pools {
		// Handle nil reserves safely
		var reserve0Dec, reserve1Dec math.LegacyDec
		if pool.Reserve0.IsNil() {
			reserve0Dec = DecZero
		} else {
			reserve0Dec = math.LegacyNewDecFromInt(pool.Reserve0)
		}
		if pool.Reserve1.IsNil() {
			reserve1Dec = DecZero
		} else {
			reserve1Dec = math.LegacyNewDecFromInt(pool.Reserve1)
		}

		// Dimension 2*i: amount of denom0 to sell [0, reserve0]
		bounds.Lower[2*i] = DecZero
		bounds.Upper[2*i] = reserve0Dec

		// Dimension 2*i+1: amount of denom1 to sell [0, reserve1]
		bounds.Lower[2*i+1] = DecZero
		bounds.Upper[2*i+1] = reserve1Dec
	}

	return bounds
}

// ComputeClosedFormEstimate uses FLOOD-style (MMBF) flow optimization.
// Production-grade algorithm:
// 1. Always starts and ends at refDenom (base token)
// 2. Multi-path order splitting for AMM convexity
// 3. Early exit on profit detection
// 4. Returns flows for Nelder-Mead refinement
func (ac *ArbitrageContext) ComputeClosedFormEstimate() []math.LegacyDec {
	n := len(ac.Pools) * 2
	best := make([]math.LegacyDec, n)
	for i := range best {
		best[i] = DecZero
	}

	if len(ac.Pools) < 2 || ac.Keeper == nil {
		return best
	}

	logger := ac.Keeper.ArbitrageLogger(ac.Ctx)

	// Build token index for fast lookup
	tokenIdx := make(map[string]int)
	var tokens []string
	idx := 0
	tokenIdx[ac.RefDenom] = idx
	tokens = append(tokens, ac.RefDenom)
	idx++

	for _, pool := range ac.Pools {
		if _, ok := tokenIdx[pool.Denom0]; !ok {
			tokenIdx[pool.Denom0] = idx
			tokens = append(tokens, pool.Denom0)
			idx++
		}
		if _, ok := tokenIdx[pool.Denom1]; !ok {
			tokenIdx[pool.Denom1] = idx
			tokens = append(tokens, pool.Denom1)
			idx++
		}
	}

	baseIdx := tokenIdx[ac.RefDenom]
	numTokens := len(tokens)

	// Log token mapping
	logger.Debug("FLOOD token mapping",
		"ref_denom", ac.RefDenom,
		"base_idx", baseIdx,
		"num_tokens", numTokens,
		"tokens", tokens,
		"token_idx", tokenIdx,
	)

	// Find minimum reserve for scaling
	minReserve := math.LegacyNewDec(1 << 60)
	for _, pool := range ac.Pools {
		if pool.Reserve0.IsNil() || pool.Reserve1.IsNil() {
			logger.Debug("FLOOD skipping pool with nil reserves", "pool_id", pool.PoolID)
			continue
		}
		r0 := math.LegacyNewDecFromInt(pool.Reserve0)
		r1 := math.LegacyNewDecFromInt(pool.Reserve1)
		if r0.GT(DecZero) && r0.LT(minReserve) {
			minReserve = r0
		}
		if r1.GT(DecZero) && r1.LT(minReserve) {
			minReserve = r1
		}
	}

	logger.Debug("FLOOD min_reserve", "min_reserve", minReserve.TruncateInt().String())

	// Try different starting amounts and split counts
	bestProfit := DecZero
	var bestPath []floodStep

	maxDepth := 6
	maxSplits := 5

	for splits := 1; splits <= maxSplits; splits++ {
		// Try different fractions of min reserve
		for _, fracPct := range []int64{1, 5, 10, 25} {
			startAmt := minReserve.MulInt64(fracPct).QuoInt64(100)
			if startAmt.LT(DecOne) {
				startAmt = DecOne
			}

			logger.Debug("FLOOD trying",
				"splits", splits,
				"frac_pct", fracPct,
				"start_amt", startAmt.TruncateInt().String(),
			)

			profit, path := ac.floodSearch(tokens, tokenIdx, baseIdx, numTokens, startAmt, splits, maxDepth, logger)

			logger.Debug("FLOOD search result",
				"splits", splits,
				"frac_pct", fracPct,
				"profit", profit.TruncateInt().String(),
				"path_len", len(path),
			)

			if profit.GT(bestProfit) {
				bestProfit = profit
				bestPath = path
				logger.Debug("FLOOD found better profit",
					"splits", splits,
					"start_amt", startAmt.TruncateInt().String(),
					"profit", profit.TruncateInt().String(),
					"path_len", len(path),
				)

				// Early exit on significant profit (5%+)
				if profit.GT(startAmt.MulInt64(5).QuoInt64(100)) {
					break
				}
			}
		}
	}

	if bestProfit.GT(DecZero) && len(bestPath) > 0 {
		logger.Debug("FLOOD arbitrage found",
			"profit", bestProfit.TruncateInt().String(),
			"path_len", len(bestPath),
		)
		// Store path for direct operation generation (preserves order)
		ac.arbPath = bestPath
		// Convert path to flows for optimizer compatibility
		flows := ac.pathToFlows(bestPath, n)
		logger.Debug("FLOOD flows generated", "flows", formatFlows(flows))
		return flows
	}

	logger.Debug("FLOOD: no profitable path found",
		"best_profit", bestProfit.String(),
		"pools_checked", len(ac.Pools),
	)
	return best
}

// floodStep represents one step in an arbitrage path
type floodStep struct {
	poolIdx    int
	sellDenom0 bool
	amount     math.LegacyDec
}

// floodSearch runs FLOOD algorithm and returns (profit, path)
func (ac *ArbitrageContext) floodSearch(
	tokens []string,
	tokenIdx map[string]int,
	baseIdx, numTokens int,
	startAmt math.LegacyDec,
	splits, maxDepth int,
	logger log.Logger,
) (math.LegacyDec, []floodStep) {

	// dist[i] = max reachable amount of token i starting from base
	dist := make([]math.LegacyDec, numTokens)
	for i := range dist {
		dist[i] = DecZero
	}
	dist[baseIdx] = startAmt

	// parent[i] = how we reached token i (for path reconstruction)
	parent := make([]floodStep, numTokens)
	for i := range parent {
		parent[i] = floodStep{poolIdx: -1}
	}

	splitsDec := math.LegacyNewDec(int64(splits))

	logger.Debug("FLOOD search starting",
		"base_idx", baseIdx,
		"start_amt", startAmt.TruncateInt().String(),
		"splits", splits,
		"max_depth", maxDepth,
		"num_pools", len(ac.Pools),
	)

	for iter := 0; iter < maxDepth*splits; iter++ {
		updated := false
		newDist := make([]math.LegacyDec, numTokens)
		copy(newDist, dist)

		// Relax all edges
		for poolIdx, pool := range ac.Pools {
			if pool.Reserve0.IsNil() || pool.Reserve1.IsNil() {
				continue
			}
			if pool.Fee0.IsNil() || pool.Fee1.IsNil() {
				continue
			}

			// Try both directions
			for _, sellDenom0 := range []bool{true, false} {
				var tin, tout string
				var rIn, rOut, fee math.LegacyDec

				if sellDenom0 {
					tin, tout = pool.Denom0, pool.Denom1
					rIn = math.LegacyNewDecFromInt(pool.Reserve0)
					rOut = math.LegacyNewDecFromInt(pool.Reserve1)
					fee = pool.Fee0
				} else {
					tin, tout = pool.Denom1, pool.Denom0
					rIn = math.LegacyNewDecFromInt(pool.Reserve1)
					rOut = math.LegacyNewDecFromInt(pool.Reserve0)
					fee = pool.Fee1
				}

				srcIdx, srcOk := tokenIdx[tin]
				dstIdx, dstOk := tokenIdx[tout]

				if !srcOk || !dstOk {
					logger.Debug("FLOOD edge skip: token not in index",
						"tin", tin,
						"tout", tout,
						"src_ok", srcOk,
						"dst_ok", dstOk,
					)
					continue
				}

				if dist[srcIdx].LT(DecOne) {
					continue
				}

				// Split input for better AMM rates
				stepIn := dist[srcIdx].Quo(splitsDec)
				gamma := DecOne.Sub(fee)

				totalOut := DecZero
				virtualRIn, virtualROut := rIn, rOut

				for s := 0; s < splits; s++ {
					effectiveIn := stepIn.Mul(gamma)
					out := virtualROut.Mul(effectiveIn).Quo(virtualRIn.Add(effectiveIn))
					totalOut = totalOut.Add(out)
					// Update virtual reserves
					virtualRIn = virtualRIn.Add(stepIn)
					virtualROut = virtualROut.Sub(out)
				}

				if totalOut.GT(newDist[dstIdx]) {
					logger.Debug("FLOOD edge relax",
						"iter", iter,
						"pool_id", pool.PoolID,
						"tin", tin,
						"tout", tout,
						"src_idx", srcIdx,
						"dst_idx", dstIdx,
						"dist_src", dist[srcIdx].TruncateInt().String(),
						"total_out", totalOut.TruncateInt().String(),
						"prev_dist_dst", newDist[dstIdx].TruncateInt().String(),
					)
					newDist[dstIdx] = totalOut
					parent[dstIdx] = floodStep{
						poolIdx:    poolIdx,
						sellDenom0: sellDenom0,
						amount:     dist[srcIdx],
					}
					updated = true
				}
			}
		}

		dist = newDist

		// Log dist state
		distStrs := make([]string, numTokens)
		for i := 0; i < numTokens; i++ {
			distStrs[i] = dist[i].TruncateInt().String()
		}
		logger.Debug("FLOOD iter complete",
			"iter", iter,
			"updated", updated,
			"dist_base", dist[baseIdx].TruncateInt().String(),
			"start_amt", startAmt.TruncateInt().String(),
			"dist", distStrs,
		)

		// Early profit detection (>0.1%)
		if dist[baseIdx].GT(startAmt.MulInt64(1001).QuoInt64(1000)) {
			profit := dist[baseIdx].Sub(startAmt)
			logger.Debug("FLOOD early profit detected",
				"iter", iter,
				"dist_base", dist[baseIdx].TruncateInt().String(),
				"profit", profit.TruncateInt().String(),
			)
			path := ac.reconstructPath(parent, tokens, tokenIdx, baseIdx, startAmt, logger)
			return profit, path
		}

		if !updated {
			logger.Debug("FLOOD no updates, stopping", "iter", iter)
			break
		}
	}

	// Final profit check
	profit := dist[baseIdx].Sub(startAmt)

	// Log parent array state
	parentInfo := make([]string, numTokens)
	for i := 0; i < numTokens; i++ {
		if parent[i].poolIdx >= 0 {
			pool := ac.Pools[parent[i].poolIdx]
			parentInfo[i] = fmt.Sprintf("%s←P%d", tokens[i], pool.PoolID)
		} else {
			parentInfo[i] = tokens[i] + "←nil"
		}
	}
	logger.Debug("FLOOD final check",
		"dist_base", dist[baseIdx].TruncateInt().String(),
		"start_amt", startAmt.TruncateInt().String(),
		"profit", profit.TruncateInt().String(),
		"parent_info", parentInfo,
	)

	if profit.GT(DecZero) {
		path := ac.reconstructPath(parent, tokens, tokenIdx, baseIdx, startAmt, logger)
		return profit, path
	}

	return DecZero, nil
}

// reconstructPath finds a profitable cycle from base back to base using DFS.
// Since parent pointers in FLOOD get overwritten, we do a fresh DFS to find
// an actual valid cycle with computed swap amounts.
func (ac *ArbitrageContext) reconstructPath(
	parent []floodStep,
	tokens []string,
	tokenIdx map[string]int,
	baseIdx int,
	startAmt math.LegacyDec,
	logger log.Logger,
) []floodStep {
	logger.Debug("FLOOD reconstructPath starting DFS",
		"base_idx", baseIdx,
		"base_token", tokens[baseIdx],
		"start_amt", startAmt.TruncateInt().String(),
		"num_pools", len(ac.Pools),
	)

	// Build adjacency: for each token, list (poolIdx, sellDenom0, dstTokenIdx)
	type edge struct {
		poolIdx    int
		sellDenom0 bool
		dstIdx     int
	}
	adj := make(map[int][]edge)

	for poolIdx, pool := range ac.Pools {
		if pool.Reserve0.IsNil() || pool.Reserve1.IsNil() {
			continue
		}
		if pool.Reserve0.IsZero() || pool.Reserve1.IsZero() {
			continue
		}

		srcIdx0, ok0 := tokenIdx[pool.Denom0]
		srcIdx1, ok1 := tokenIdx[pool.Denom1]
		if !ok0 || !ok1 {
			continue
		}

		// Denom0 → Denom1
		adj[srcIdx0] = append(adj[srcIdx0], edge{poolIdx, true, srcIdx1})
		// Denom1 → Denom0
		adj[srcIdx1] = append(adj[srcIdx1], edge{poolIdx, false, srcIdx0})
	}

	// DFS to find profitable cycle starting and ending at baseIdx
	// Track: current token, current amount, path taken, used pools
	type dfsState struct {
		tokenIdx int
		amount   math.LegacyDec
		path     []floodStep
		usedDir  map[int]bool // pool_idx * 2 + (1 if sellDenom0 else 0) -> used
	}

	var bestPath []floodStep
	bestProfit := DecZero
	maxDepth := 6

	var dfs func(state dfsState, depth int)
	dfs = func(state dfsState, depth int) {
		if depth > maxDepth {
			return
		}

		// Check if we can return to base
		if depth > 0 && state.tokenIdx == baseIdx {
			profit := state.amount.Sub(startAmt)
			if profit.GT(bestProfit) {
				logger.Debug("FLOOD DFS found cycle",
					"depth", depth,
					"profit", profit.TruncateInt().String(),
					"path_len", len(state.path),
				)
				bestProfit = profit
				bestPath = make([]floodStep, len(state.path))
				copy(bestPath, state.path)
			}
			return
		}

		// Explore edges
		for _, e := range adj[state.tokenIdx] {
			dirKey := e.poolIdx*2 + func() int {
				if e.sellDenom0 {
					return 1
				}
				return 0
			}()

			// Skip if already used this direction
			if state.usedDir[dirKey] {
				continue
			}

			// Compute output
			pool := ac.Pools[e.poolIdx]
			var rIn, rOut, fee math.LegacyDec
			if e.sellDenom0 {
				rIn = math.LegacyNewDecFromInt(pool.Reserve0)
				rOut = math.LegacyNewDecFromInt(pool.Reserve1)
				if !pool.Fee0.IsNil() {
					fee = pool.Fee0
				} else {
					fee = DecZero
				}
			} else {
				rIn = math.LegacyNewDecFromInt(pool.Reserve1)
				rOut = math.LegacyNewDecFromInt(pool.Reserve0)
				if !pool.Fee1.IsNil() {
					fee = pool.Fee1
				} else {
					fee = DecZero
				}
			}

			if rIn.IsZero() || rOut.IsZero() {
				continue
			}

			gamma := DecOne.Sub(fee)
			effectiveIn := state.amount.Mul(gamma)
			out := rOut.Mul(effectiveIn).Quo(rIn.Add(effectiveIn))

			if out.LTE(DecZero) {
				continue
			}

			// Recurse
			newUsedDir := make(map[int]bool)
			for k, v := range state.usedDir {
				newUsedDir[k] = v
			}
			newUsedDir[dirKey] = true

			newPath := make([]floodStep, len(state.path)+1)
			copy(newPath, state.path)
			newPath[len(state.path)] = floodStep{
				poolIdx:    e.poolIdx,
				sellDenom0: e.sellDenom0,
				amount:     state.amount,
			}

			dfs(dfsState{
				tokenIdx: e.dstIdx,
				amount:   out,
				path:     newPath,
				usedDir:  newUsedDir,
			}, depth+1)
		}
	}

	// Start DFS from base
	dfs(dfsState{
		tokenIdx: baseIdx,
		amount:   startAmt,
		path:     nil,
		usedDir:  make(map[int]bool),
	}, 0)

	logger.Debug("FLOOD reconstructPath DFS result",
		"path_len", len(bestPath),
		"profit", bestProfit.TruncateInt().String(),
	)

	return bestPath
}

// pathToFlows converts a path to the 2N flows vector with proper cascading amounts.
// The path represents edges traversed in FORWARD order (from base to base).
// We compute sequential trade amounts where each trade's output is next trade's input.
func (ac *ArbitrageContext) pathToFlows(path []floodStep, n int) []math.LegacyDec {
	logger := ac.Keeper.ArbitrageLogger(ac.Ctx)

	flows := make([]math.LegacyDec, n)
	for i := range flows {
		flows[i] = DecZero
	}

	if len(path) == 0 {
		logger.Debug("pathToFlows: empty path")
		return flows
	}

	// The first step's amount is how much we start with
	// For subsequent steps, we compute output of previous trade
	currentAmount := path[0].amount
	if currentAmount.IsNil() || currentAmount.LTE(DecZero) {
		// Use a reasonable starting amount if not set
		currentAmount = math.LegacyNewDec(100)
	}

	logger.Debug("pathToFlows starting",
		"path_len", len(path),
		"initial_amount", currentAmount.TruncateInt().String(),
	)

	for i, step := range path {
		if step.poolIdx < 0 || step.poolIdx >= len(ac.Pools) {
			logger.Debug("pathToFlows: invalid pool index", "idx", step.poolIdx)
			continue
		}

		pool := ac.Pools[step.poolIdx]

		// Set the flow for this step
		// Convention (from buildMakeTradeMsg):
		//   sellDenom0 (swap denom0 in) → flows[2*idx]
		//   sellDenom1 (swap denom1 in) → flows[2*idx+1]
		dirKey := step.poolIdx * 2
		if !step.sellDenom0 {
			dirKey++
		}
		flows[dirKey] = currentAmount

		logger.Debug("pathToFlows step",
			"step", i,
			"pool_id", pool.PoolID,
			"sell_denom0", step.sellDenom0,
			"dir_key", dirKey,
			"amount", currentAmount.TruncateInt().String(),
		)

		// Compute output for next step (if not last)
		if i < len(path)-1 {
			var rIn, rOut, fee math.LegacyDec
			if step.sellDenom0 {
				if pool.Reserve0.IsNil() || pool.Reserve1.IsNil() || pool.Fee0.IsNil() {
					break
				}
				rIn = math.LegacyNewDecFromInt(pool.Reserve0)
				rOut = math.LegacyNewDecFromInt(pool.Reserve1)
				fee = pool.Fee0
			} else {
				if pool.Reserve0.IsNil() || pool.Reserve1.IsNil() || pool.Fee1.IsNil() {
					break
				}
				rIn = math.LegacyNewDecFromInt(pool.Reserve1)
				rOut = math.LegacyNewDecFromInt(pool.Reserve0)
				fee = pool.Fee1
			}

			gamma := DecOne.Sub(fee)
			effectiveIn := currentAmount.Mul(gamma)
			outputAmount := rOut.Mul(effectiveIn).Quo(rIn.Add(effectiveIn))

			logger.Debug("pathToFlows compute output",
				"step", i,
				"input", currentAmount.TruncateInt().String(),
				"output", outputAmount.TruncateInt().String(),
			)

			currentAmount = outputAmount
		}
	}

	logger.Debug("pathToFlows result", "flows", formatFlows(flows))
	return flows
}

// formatFlows formats flow amounts for logging
func formatFlows(flows []math.LegacyDec) string {
	result := "["
	for i, f := range flows {
		if i > 0 {
			result += ","
		}
		result += f.String()
	}
	result += "]"
	return result
}

// FindArbitrage runs the optimizer to find profitable arbitrage.
// Returns nil if no profitable arbitrage found.
// Uses 2N dimensions (2 per pool) to allow bidirectional trading on each pool.
func (ac *ArbitrageContext) FindArbitrage(optimizer ArbitrageOptimizer) *ArbitrageResult {
	logger := ac.Keeper.ArbitrageLogger(ac.Ctx)

	if len(ac.Pools) == 0 {
		logger.Debug("arbitrage: no pools to optimize")
		return nil
	}

	numDimensions := len(ac.Pools) * 2

	logger.Debug("arbitrage optimization starting",
		"pool_count", len(ac.Pools),
		"dimensions", numDimensions,
		"pools", ac.Pools,
		"ref_denom", ac.RefDenom,
	)

	bounds := ac.GetOptimizationBounds()
	objective := ac.ObjectiveFunction()

	// Compute closed-form estimate as initial guess
	initialGuess := ac.ComputeClosedFormEstimate()

	// Check if closed-form found something
	hasClosedForm := false
	for _, v := range initialGuess {
		if !v.IsZero() {
			hasClosedForm = true
			break
		}
	}

	if hasClosedForm {
		// Evaluate the closed-form estimate
		closedFormProfit := objective(initialGuess)
		logger.Debug("closed-form arbitrage estimate",
			"profit", closedFormProfit.TruncateInt().String(),
			"amounts", initialGuess,
		)
	}

	optimal, value, found := optimizer.Optimize(objective, bounds, initialGuess)

	// Log optimization metrics
	metrics := optimizer.GetMetrics()
	if metrics != nil {
		logger.Debug("arbitrage optimization completed",
			"algorithm", metrics.Algorithm,
			"iterations", metrics.Iterations,
			"best_iteration", metrics.BestIteration, // 0 = initial/CF, >0 = NM improved
			"evaluations", metrics.Evaluations,
			"dimensions", metrics.Dimensions,
			"duration_ms", metrics.Duration.Milliseconds(),
			"best_value", metrics.BestValue.String(),
			"found", metrics.Found,
			"pools", ac.Pools,
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
		val := a.TruncateInt64()
		if val < 0 {
			val = 0
		}
		intAmounts[i] = val
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

	// Format swap amounts for logging: [pool0_sell0, pool0_sell1, pool1_sell0, ...]
	logger.Debug("arbitrage opportunity found",
		"profit", result.Profit.String(),
		"ref_denom", ac.RefDenom,
		"trader_inputs", result.TraderInputs.String(),
		"trader_outputs", result.TraderOutputs.String(),
		"swap_amounts", intAmounts,
		"pools", ac.Pools,
	)

	return result
}

// BuildFinalMakeTradeMsg creates the MsgMakeTrade for execution with proper constraints.
// This should be called after FindArbitrage to create a msg with appropriate
// MaxInput and MinOutput based on the simulation result.
//
// Returns nil if the arbitrage is not purely circular (has any net inputs).
func (ac *ArbitrageContext) BuildFinalMakeTradeMsg(result *ArbitrageResult) *whaleswapv1.MsgMakeTrade {
	if result == nil || !result.Success || result.Msg == nil {
		return nil
	}

	// Arbitrage must be purely circular — reject if there are any net inputs
	if !result.TraderInputs.IsZero() {
		return nil
	}

	// Copy operations from simulation msg
	msg := &whaleswapv1.MsgMakeTrade{
		Trader:     ac.Trader,
		Operations: result.Msg.Operations,
		Note:       "",
		MaxInput:   nil, // Circular arb: no inputs allowed
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
