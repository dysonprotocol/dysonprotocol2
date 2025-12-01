package keeper

import (
	"fmt"
	"time"

	"cosmossdk.io/math"
)

// Consensus-safe constants for optimizer results.
// Using LegacyDec ensures deterministic behavior across all nodes.
var (
	// DecZero is the zero value for optimizer calculations.
	DecZero = math.LegacyZeroDec()
	// DecOne is used for unit calculations.
	DecOne = math.LegacyOneDec()
	// DecMinValue represents failure/invalid result (very negative).
	DecMinValue = math.LegacyNewDec(-1).MulInt64(1e18)
)

// OptimizationMetrics tracks statistics from an optimization run.
// Used for logging and debugging optimizer performance.
type OptimizationMetrics struct {
	// Algorithm is the name of the optimizer used (e.g., "TernarySearch", "NelderMead", "Grid")
	Algorithm string
	// Iterations is the number of main loop iterations performed
	Iterations int
	// Evaluations is the number of objective function calls
	Evaluations int
	// Dimensions is the number of active pool dimensions
	Dimensions int
	// Duration is how long the optimization took
	Duration time.Duration
	// BestValue is the best objective value found
	BestValue math.LegacyDec
	// BestIteration is the iteration number when BestValue was found (0 = initial guess)
	BestIteration int
	// Found indicates if a profitable solution was found
	Found bool
}

// OptimizationBounds holds the search bounds for each pool dimension.
// Using LegacyDec ensures consensus-safe arithmetic.
type OptimizationBounds struct {
	Lower []math.LegacyDec // minimum swap amounts (0 for all dimensions)
	Upper []math.LegacyDec // maximum swap amounts (pool reserves)
}

// ArbitrageOptimizer is the interface for a deterministic black-box optimizer.
// The optimizer must be deterministic to ensure consensus across all nodes.
// All arithmetic uses math.LegacyDec for consensus safety.
type ArbitrageOptimizer interface {
	// Optimize finds the optimal swap amounts to maximize profit.
	//
	// Parameters:
	//   - objective: function to maximize; takes []LegacyDec returns LegacyDec
	//   - bounds: lower and upper bounds for each variable
	//   - initialGuess: starting point for optimization
	//
	// Returns:
	//   - optimal: the optimal swap amounts found
	//   - value: the objective value at optimal point
	//   - found: true if a profitable solution was found
	Optimize(
		objective func([]math.LegacyDec) math.LegacyDec,
		bounds OptimizationBounds,
		initialGuess []math.LegacyDec,
	) (optimal []math.LegacyDec, value math.LegacyDec, found bool)

	// GetMetrics returns metrics from the last optimization run.
	// Returns nil if no optimization has been performed yet.
	GetMetrics() *OptimizationMetrics
}

// NelderMeadOptimizer implements Nelder-Mead simplex for deterministic optimization.
// More efficient than grid search for higher dimensions.
// Optimized for circular arbitrage: stops early when improvement plateaus.
type NelderMeadOptimizer struct {
	MaxIterations     int            // hard cap on iterations (default 15)
	Tolerance         math.LegacyDec // absolute convergence tolerance
	MaxPools          int            // limit active dimensions
	NoImproveLimit    int            // stop after N iterations without improvement (default 3)
	RelativeTolerance math.LegacyDec // stop when improvement < this fraction of best (default 0.0001 = 0.01%)

	// metrics stores results from the last optimization run
	metrics *OptimizationMetrics
}

// GetMetrics returns metrics from the last optimization run.
func (nm *NelderMeadOptimizer) GetMetrics() *OptimizationMetrics {
	return nm.metrics
}

// Optimize implements ArbitrageOptimizer using Nelder-Mead.
// Note: We negate the objective since Nelder-Mead typically minimizes.
func (nm *NelderMeadOptimizer) Optimize(
	objective func([]math.LegacyDec) math.LegacyDec,
	bounds OptimizationBounds,
	initialGuess []math.LegacyDec,
) (optimal []math.LegacyDec, value math.LegacyDec, found bool) {
	startTime := time.Now()
	evaluations := 0

	totalDims := len(bounds.Lower)
	if totalDims == 0 {
		nm.metrics = &OptimizationMetrics{
			Algorithm:   "NelderMead",
			Iterations:  0,
			Evaluations: 0,
			Dimensions:  0,
			Duration:    time.Since(startTime),
			BestValue:   DecZero,
			Found:       false,
		}
		return nil, DecZero, false
	}

	// Limit active dimensions
	n := totalDims
	if n > nm.MaxPools {
		n = nm.MaxPools
	}

	// Nelder-Mead parameters (as LegacyDec) - standard values to avoid overshoot
	alpha := DecOne                          // reflection (1.0)
	gamma := math.LegacyNewDec(2)            // expansion (2.0 - standard, avoids overshoot)
	rho := math.LegacyNewDecWithPrec(5, 1)   // contraction (0.5)
	sigma := math.LegacyNewDecWithPrec(1, 1) // shrink (0.1 - better collapse)

	// Wrapper to handle full dimension vector (tracks evaluations)
	evalFull := func(partial []math.LegacyDec) math.LegacyDec {
		evaluations++
		full := make([]math.LegacyDec, totalDims)
		for i := range full {
			if i < len(partial) {
				full[i] = partial[i]
			} else {
				full[i] = DecZero
			}
		}
		return objective(full)
	}

	// Initialize simplex with n+1 vertices
	simplex := make([][]math.LegacyDec, n+1)
	values := make([]math.LegacyDec, n+1)

	// First vertex: initial guess or center of bounds
	simplex[0] = make([]math.LegacyDec, n)
	if len(initialGuess) >= n {
		copy(simplex[0], initialGuess[:n])
	} else {
		two := math.LegacyNewDec(2)
		for i := 0; i < n; i++ {
			simplex[0][i] = bounds.Lower[i].Add(bounds.Upper[i]).Quo(two)
		}
	}

	// Remaining vertices: offset along each axis
	// Use 10% of range for simplex - typical arb amounts are small
	simplexScale := math.LegacyNewDecWithPrec(1, 1) // 10%

	for i := 1; i <= n; i++ {
		simplex[i] = make([]math.LegacyDec, n)
		copy(simplex[i], simplex[0])
		// Offset by 10% of range
		delta := bounds.Upper[i-1].Sub(bounds.Lower[i-1]).Mul(simplexScale)
		if delta.LT(DecOne) {
			delta = DecOne
		}
		simplex[i][i-1] = simplex[i][i-1].Add(delta)
		// Clamp to bounds
		if simplex[i][i-1].GT(bounds.Upper[i-1]) {
			simplex[i][i-1] = bounds.Upper[i-1]
		}
	}

	// Evaluate initial simplex (negate for minimization)
	for i := 0; i <= n; i++ {
		values[i] = evalFull(simplex[i]).Neg()
	}

	// Track best value and which iteration found it
	bestNegVal := values[0] // will be updated after sort
	bestIteration := 0      // 0 = initial simplex
	noImproveCount := 0     // count iterations without improvement

	// Early stopping parameters (use defaults if not set)
	noImproveLimit := nm.NoImproveLimit
	if noImproveLimit <= 0 {
		noImproveLimit = 3 // stop after 3 iterations without improvement
	}
	relTol := nm.RelativeTolerance
	if relTol.IsNil() || relTol.IsZero() {
		relTol = math.LegacyNewDecWithPrec(1, 4) // 0.0001 = 0.01%
	}

	// Main loop
	actualIters := 0
	for iter := 0; iter < nm.MaxIterations; iter++ {
		actualIters = iter + 1
		// Sort vertices by value (ascending = best to worst for minimization)
		for i := 0; i <= n; i++ {
			for j := i + 1; j <= n; j++ {
				if values[j].LT(values[i]) {
					simplex[i], simplex[j] = simplex[j], simplex[i]
					values[i], values[j] = values[j], values[i]
				}
			}
		}

		// Track if this iteration improved the best value
		prevBest := bestNegVal
		if values[0].LT(bestNegVal) {
			bestNegVal = values[0]
			bestIteration = iter + 1
			noImproveCount = 0
		} else {
			noImproveCount++
		}

		// Early stopping: no improvement for N iterations
		if noImproveCount >= noImproveLimit {
			break
		}

		// Early stopping: relative improvement too small (< 0.01% of best)
		if !prevBest.IsZero() && prevBest.IsNegative() {
			improvement := prevBest.Sub(values[0])  // positive if improved
			threshold := prevBest.Neg().Mul(relTol) // relTol * |best|
			if improvement.IsPositive() && improvement.LT(threshold) {
				noImproveCount++ // count as no significant improvement
			}
		}

		// Check convergence (simplex collapsed)
		if values[n].Sub(values[0]).LT(nm.Tolerance) {
			break
		}

		// Compute centroid of all but worst
		centroid := make([]math.LegacyDec, n)
		nDec := math.LegacyNewDec(int64(n))
		for i := 0; i < n; i++ {
			sum := DecZero
			for j := 0; j < n; j++ {
				sum = sum.Add(simplex[j][i])
			}
			centroid[i] = sum.Quo(nDec)
		}

		// Reflection
		reflected := make([]math.LegacyDec, n)
		for i := 0; i < n; i++ {
			// reflected[i] = centroid[i] + alpha * (centroid[i] - simplex[n][i])
			reflected[i] = centroid[i].Add(alpha.Mul(centroid[i].Sub(simplex[n][i])))
			// Clamp to bounds
			if reflected[i].LT(bounds.Lower[i]) {
				reflected[i] = bounds.Lower[i]
			}
			if reflected[i].GT(bounds.Upper[i]) {
				reflected[i] = bounds.Upper[i]
			}
		}
		reflectedVal := evalFull(reflected).Neg()

		// Accept reflection if better than worst
		if reflectedVal.LT(values[n]) {
			// Check if we should try expansion (reflected is best so far)
			if reflectedVal.LT(values[0]) {
				// Try expansion
				expanded := make([]math.LegacyDec, n)
				for i := 0; i < n; i++ {
					// expanded[i] = centroid[i] + gamma * (reflected[i] - centroid[i])
					expanded[i] = centroid[i].Add(gamma.Mul(reflected[i].Sub(centroid[i])))
					if expanded[i].LT(bounds.Lower[i]) {
						expanded[i] = bounds.Lower[i]
					}
					if expanded[i].GT(bounds.Upper[i]) {
						expanded[i] = bounds.Upper[i]
					}
				}
				expandedVal := evalFull(expanded).Neg()
				if expandedVal.LT(reflectedVal) {
					copy(simplex[n], expanded)
					values[n] = expandedVal
				} else {
					copy(simplex[n], reflected)
					values[n] = reflectedVal
				}
				continue
			}
			// Accept reflection (better than worst but not best)
			copy(simplex[n], reflected)
			values[n] = reflectedVal
			continue
		}

		// Contraction (reflection was not better than worst)
		contracted := make([]math.LegacyDec, n)
		for i := 0; i < n; i++ {
			// contracted[i] = centroid[i] + rho * (simplex[n][i] - centroid[i])
			contracted[i] = centroid[i].Add(rho.Mul(simplex[n][i].Sub(centroid[i])))
			if contracted[i].LT(bounds.Lower[i]) {
				contracted[i] = bounds.Lower[i]
			}
			if contracted[i].GT(bounds.Upper[i]) {
				contracted[i] = bounds.Upper[i]
			}
		}
		contractedVal := evalFull(contracted).Neg()
		if contractedVal.LT(values[n]) {
			copy(simplex[n], contracted)
			values[n] = contractedVal
			continue
		}

		// Shrink
		for i := 1; i <= n; i++ {
			for j := 0; j < n; j++ {
				// simplex[i][j] = simplex[0][j] + sigma * (simplex[i][j] - simplex[0][j])
				simplex[i][j] = simplex[0][j].Add(sigma.Mul(simplex[i][j].Sub(simplex[0][j])))
			}
			values[i] = evalFull(simplex[i]).Neg()
		}
	}

	// Build full result vector
	result := make([]math.LegacyDec, totalDims)
	for i := range result {
		if i < len(simplex[0]) {
			result[i] = simplex[0][i]
		} else {
			result[i] = DecZero
		}
	}

	// Return best found (negate back to original objective scale)
	bestValue := values[0].Neg()
	foundProfit := bestValue.IsPositive()

	nm.metrics = &OptimizationMetrics{
		Algorithm:     "NelderMead",
		Iterations:    actualIters,
		Evaluations:   evaluations,
		Dimensions:    n,
		Duration:      time.Since(startTime),
		BestValue:     bestValue,
		BestIteration: bestIteration,
		Found:         foundProfit,
	}

	if !foundProfit {
		return nil, bestValue, false
	}

	return result, bestValue, true
}

// HybridOptimizer uses combinatorial probe to find profitable region,
// then Nelder-Mead to refine to local maximum.
// This is the optimal strategy for whaleswap arbitrage.
type HybridOptimizer struct {
	NelderMead *NelderMeadOptimizer
	MaxPools   int // limit active dimensions for probe

	// metrics aggregates results from optimization
	metrics *OptimizationMetrics
}

// NewHybridOptimizer creates a hybrid optimizer.
// Note: With 2N dimensions (2 per pool), MaxPools should be 2x the number of pools.
// Optimized for arbitrage: closed-form finds 99%+, NelderMead polishes in ~5 iterations.
func NewHybridOptimizer() *HybridOptimizer {
	return &HybridOptimizer{
		MaxPools: 20, // supports up to 10 pools (20 dimensions)
		NelderMead: &NelderMeadOptimizer{
			MaxIterations:     12,                              // hard cap (CF finds most profit)
			Tolerance:         math.LegacyNewDecWithPrec(1, 2), // 0.01 absolute
			MaxPools:          20,                              // 10 pools
			NoImproveLimit:    3,                               // stop after 3 iters without improvement
			RelativeTolerance: math.LegacyNewDecWithPrec(5, 5), // 0.005% relative improvement threshold
		},
	}
}

// GetMetrics returns metrics from the last optimization run.
func (h *HybridOptimizer) GetMetrics() *OptimizationMetrics {
	return h.metrics
}

// Optimize implements ArbitrageOptimizer using two-phase approach:
// 1. Closed-form estimate (Newton's method on cycles, provided in initialGuess)
// 2. NelderMead refinement to polish and consolidate extras
//
// The closed-form typically finds 99%+ of optimal profit in 1 evaluation.
// NelderMead adds the final 1% in ~10-15 evaluations.
func (h *HybridOptimizer) Optimize(
	objective func([]math.LegacyDec) math.LegacyDec,
	bounds OptimizationBounds,
	initialGuess []math.LegacyDec,
) (optimal []math.LegacyDec, value math.LegacyDec, found bool) {
	startTime := time.Now()
	evaluations := 0

	n := len(bounds.Lower)
	if n == 0 {
		h.metrics = &OptimizationMetrics{
			Algorithm:     "CF+NM(NoPool)",
			Evaluations:   0,
			Dimensions:    0,
			Duration:      time.Since(startTime),
			BestValue:     DecZero,
			BestIteration: 0,
			Found:         false,
		}
		return nil, DecZero, false
	}

	// === PHASE 1: Evaluate closed-form estimate ===
	x := make([]math.LegacyDec, n)
	for i := range x {
		x[i] = DecZero
	}
	bestVal := DecMinValue

	// Check if closed-form found a profitable cycle
	hasClosedForm := false
	if len(initialGuess) == n {
		for _, v := range initialGuess {
			if !v.IsZero() {
				hasClosedForm = true
				break
			}
		}
	}

	if hasClosedForm {
		evaluations++
		closedFormVal := objective(initialGuess)
		if closedFormVal.GT(bestVal) {
			bestVal = closedFormVal
			copy(x, initialGuess)
		}
	}

	// If closed-form didn't find profit, exit early
	if !bestVal.IsPositive() {
		h.metrics = &OptimizationMetrics{
			Algorithm:     "CF+NM(NoProfit)",
			Evaluations:   evaluations,
			Dimensions:    n,
			Duration:      time.Since(startTime),
			BestValue:     bestVal,
			BestIteration: 0, // closed-form was evaluated but not profitable
			Found:         false,
		}
		return nil, bestVal, false
	}

	cfVal := bestVal

	// === PHASE 2: NelderMead refinement ===
	// Polish the closed-form estimate and consolidate extras to ref_denom
	refined, refinedVal, refinedOk := h.NelderMead.Optimize(objective, bounds, x)
	evaluations += h.NelderMead.metrics.Evaluations

	if refinedOk && refinedVal.GT(cfVal) {
		improvement := refinedVal.Sub(cfVal)
		// NelderMead improved, report its best iteration
		h.metrics = &OptimizationMetrics{
			Algorithm:     fmt.Sprintf("CF:%s→NM:+%s", cfVal.TruncateInt().String(), improvement.TruncateInt().String()),
			Iterations:    h.NelderMead.metrics.Iterations,
			Evaluations:   evaluations,
			Dimensions:    n,
			Duration:      time.Since(startTime),
			BestValue:     refinedVal,
			BestIteration: h.NelderMead.metrics.BestIteration, // iteration within NM that found best
			Found:         true,
		}
		return refined, refinedVal, true
	}

	// NelderMead didn't improve - closed-form was best (iteration 0)
	h.metrics = &OptimizationMetrics{
		Algorithm:     fmt.Sprintf("CF:%s(NM:NoImprove)", cfVal.TruncateInt().String()),
		Iterations:    h.NelderMead.metrics.Iterations,
		Evaluations:   evaluations,
		Dimensions:    n,
		Duration:      time.Since(startTime),
		BestValue:     cfVal,
		BestIteration: 0, // closed-form was best
		Found:         true,
	}
	return x, cfVal, true
}
