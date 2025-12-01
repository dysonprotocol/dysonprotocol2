package keeper

import (
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
	// Found indicates if a profitable solution was found
	Found bool
}

// OptimizationBounds holds the search bounds for each pool dimension.
// Using LegacyDec ensures consensus-safe arithmetic.
type OptimizationBounds struct {
	Lower []math.LegacyDec // minimum swap amounts (negative = sell denom1)
	Upper []math.LegacyDec // maximum swap amounts (positive = sell denom0)
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

// GridSearchOptimizer implements a simple deterministic grid search.
// This is a baseline implementation; works well for small pool counts.
type GridSearchOptimizer struct {
	// GridPoints is the number of points to sample per dimension.
	// Total evaluations = GridPoints^N where N is number of pools.
	// Keep small for many pools (e.g., 5-10).
	GridPoints int

	// MaxPools limits how many pools to include in optimization.
	// Pools beyond this limit are set to zero swap amount.
	MaxPools int

	// metrics stores results from the last optimization run
	metrics *OptimizationMetrics
}

// GetMetrics returns metrics from the last optimization run.
func (g *GridSearchOptimizer) GetMetrics() *OptimizationMetrics {
	return g.metrics
}

// Optimize implements ArbitrageOptimizer using grid search.
func (g *GridSearchOptimizer) Optimize(
	objective func([]math.LegacyDec) math.LegacyDec,
	bounds OptimizationBounds,
	initialGuess []math.LegacyDec,
) (optimal []math.LegacyDec, value math.LegacyDec, found bool) {
	startTime := time.Now()
	evaluations := 0

	n := len(bounds.Lower)
	if n == 0 {
		g.metrics = &OptimizationMetrics{
			Algorithm:   "GridSearch",
			Iterations:  0,
			Evaluations: 0,
			Dimensions:  0,
			Duration:    time.Since(startTime),
			BestValue:   DecZero,
			Found:       false,
		}
		return nil, DecZero, false
	}

	// Limit dimensions for tractability
	activeDims := n
	if activeDims > g.MaxPools {
		activeDims = g.MaxPools
	}

	// Generate grid points for each active dimension
	grids := make([][]math.LegacyDec, activeDims)
	gridPointsDec := math.LegacyNewDec(int64(g.GridPoints - 1))

	for i := 0; i < activeDims; i++ {
		lower := bounds.Lower[i]
		upper := bounds.Upper[i]
		grids[i] = make([]math.LegacyDec, g.GridPoints)
		rangeVal := upper.Sub(lower)

		for j := 0; j < g.GridPoints; j++ {
			// t = j / (GridPoints - 1)
			t := math.LegacyNewDec(int64(j)).Quo(gridPointsDec)
			// grid[i][j] = lower + t * range
			grids[i][j] = lower.Add(t.Mul(rangeVal))
		}
	}

	// Evaluate all grid combinations
	bestValue := DecMinValue
	bestPoint := make([]math.LegacyDec, n)
	for i := range bestPoint {
		bestPoint[i] = DecZero
	}

	// Use indices to enumerate all combinations
	indices := make([]int, activeDims)
	point := make([]math.LegacyDec, n)
	for i := range point {
		point[i] = DecZero
	}

	iterations := 0
	for {
		iterations++
		// Build current point from indices
		for i := 0; i < activeDims; i++ {
			point[i] = grids[i][indices[i]]
		}
		// Zero out dimensions beyond MaxPools
		for i := activeDims; i < n; i++ {
			point[i] = DecZero
		}

		// Evaluate
		evaluations++
		val := objective(point)
		if val.GT(bestValue) {
			bestValue = val
			copy(bestPoint, point)
		}

		// Increment indices (odometer style)
		carry := true
		for i := 0; carry && i < activeDims; i++ {
			indices[i]++
			if indices[i] >= g.GridPoints {
				indices[i] = 0
			} else {
				carry = false
			}
		}
		if carry {
			break // all combinations exhausted
		}
	}

	// Check if we found a profitable solution
	foundProfit := bestValue.IsPositive()

	g.metrics = &OptimizationMetrics{
		Algorithm:   "GridSearch",
		Iterations:  iterations,
		Evaluations: evaluations,
		Dimensions:  activeDims,
		Duration:    time.Since(startTime),
		BestValue:   bestValue,
		Found:       foundProfit,
	}

	if !foundProfit {
		return nil, bestValue, false
	}

	return bestPoint, bestValue, true
}

// NelderMeadOptimizer implements Nelder-Mead simplex for deterministic optimization.
// More efficient than grid search for higher dimensions.
type NelderMeadOptimizer struct {
	MaxIterations int
	Tolerance     math.LegacyDec
	MaxPools      int // limit active dimensions

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

	// Nelder-Mead parameters (as LegacyDec)
	alpha := DecOne                             // reflection
	gamma := math.LegacyNewDec(2)               // expansion
	rho := math.LegacyNewDecWithPrec(5, 1)      // contraction (0.5)
	sigma := math.LegacyNewDecWithPrec(5, 1)    // shrink (0.5)
	pointOne := math.LegacyNewDecWithPrec(1, 1) // 0.1 for delta calculation

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
	for i := 1; i <= n; i++ {
		simplex[i] = make([]math.LegacyDec, n)
		copy(simplex[i], simplex[0])
		// Offset by 10% of range or 1.0, whichever is larger
		delta := bounds.Upper[i-1].Sub(bounds.Lower[i-1]).Mul(pointOne)
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

		// Check convergence
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
		Algorithm:   "NelderMead",
		Iterations:  actualIters,
		Evaluations: evaluations,
		Dimensions:  n,
		Duration:    time.Since(startTime),
		BestValue:   bestValue,
		Found:       foundProfit,
	}

	if !foundProfit {
		return nil, bestValue, false
	}

	return result, bestValue, true
}

// HybridOptimizer uses TernarySearch to find optimal amounts,
// then Nelder-Mead to refine to local maximum.
// This is the optimal strategy for whaleswap arbitrage.
type HybridOptimizer struct {
	Grid       *GridSearchOptimizer
	NelderMead *NelderMeadOptimizer

	// metrics aggregates results from sub-optimizers
	metrics *OptimizationMetrics
	// allMetrics stores metrics from each phase for detailed logging
	AllMetrics []*OptimizationMetrics
}

// NewHybridOptimizer creates a hybrid optimizer.
func NewHybridOptimizer() *HybridOptimizer {
	return &HybridOptimizer{
		Grid: &GridSearchOptimizer{
			GridPoints: 5,
			MaxPools:   4,
		},
		NelderMead: &NelderMeadOptimizer{
			MaxIterations: 50,
			Tolerance:     math.LegacyNewDecWithPrec(5, 1), // 0.5
			MaxPools:      8,
		},
	}
}

// GetMetrics returns aggregated metrics from the last optimization run.
func (h *HybridOptimizer) GetMetrics() *OptimizationMetrics {
	return h.metrics
}

// Optimize implements ArbitrageOptimizer using hybrid approach:
// 1. TernarySearch finds optimal via coordinate descent
// 2. NelderMead polishes to true local maximum
func (h *HybridOptimizer) Optimize(
	objective func([]math.LegacyDec) math.LegacyDec,
	bounds OptimizationBounds,
	initialGuess []math.LegacyDec,
) (optimal []math.LegacyDec, value math.LegacyDec, found bool) {
	startTime := time.Now()
	h.AllMetrics = make([]*OptimizationMetrics, 0, 3)
	totalEvaluations := 0
	totalIterations := 0

	// Phase 1: TernarySearch (coordinate descent) finds a good solution
	ts := &TernarySearchOptimizer{MaxIterations: 10, MaxPools: 4}
	tsResult, tsValue, tsFound := ts.Optimize(objective, bounds, initialGuess)
	h.AllMetrics = append(h.AllMetrics, ts.GetMetrics())
	totalEvaluations += ts.metrics.Evaluations
	totalIterations += ts.metrics.Iterations

	if tsFound && tsValue.IsPositive() {
		// Phase 2: NelderMead refines the result
		refined, refinedVal, refinedOk := h.NelderMead.Optimize(objective, bounds, tsResult)
		h.AllMetrics = append(h.AllMetrics, h.NelderMead.GetMetrics())
		totalEvaluations += h.NelderMead.metrics.Evaluations
		totalIterations += h.NelderMead.metrics.Iterations

		if refinedOk && refinedVal.GT(tsValue) {
			h.metrics = &OptimizationMetrics{
				Algorithm:   "Hybrid(TernarySearch→NelderMead)",
				Iterations:  totalIterations,
				Evaluations: totalEvaluations,
				Dimensions:  ts.metrics.Dimensions,
				Duration:    time.Since(startTime),
				BestValue:   refinedVal,
				Found:       true,
			}
			return refined, refinedVal, true
		}
		// Refinement didn't improve - return original
		h.metrics = &OptimizationMetrics{
			Algorithm:   "Hybrid(TernarySearch)",
			Iterations:  totalIterations,
			Evaluations: totalEvaluations,
			Dimensions:  ts.metrics.Dimensions,
			Duration:    time.Since(startTime),
			BestValue:   tsValue,
			Found:       true,
		}
		return tsResult, tsValue, true
	}

	// Fallback: GridSearch if TernarySearch found nothing
	gridResult, gridValue, gridFound := h.Grid.Optimize(objective, bounds, initialGuess)
	h.AllMetrics = append(h.AllMetrics, h.Grid.GetMetrics())
	totalEvaluations += h.Grid.metrics.Evaluations
	totalIterations += h.Grid.metrics.Iterations

	if gridFound && gridValue.IsPositive() {
		// Try to refine grid result too
		refined, refinedVal, refinedOk := h.NelderMead.Optimize(objective, bounds, gridResult)
		h.AllMetrics = append(h.AllMetrics, h.NelderMead.GetMetrics())
		totalEvaluations += h.NelderMead.metrics.Evaluations
		totalIterations += h.NelderMead.metrics.Iterations

		if refinedOk && refinedVal.GT(gridValue) {
			h.metrics = &OptimizationMetrics{
				Algorithm:   "Hybrid(GridSearch→NelderMead)",
				Iterations:  totalIterations,
				Evaluations: totalEvaluations,
				Dimensions:  h.Grid.metrics.Dimensions,
				Duration:    time.Since(startTime),
				BestValue:   refinedVal,
				Found:       true,
			}
			return refined, refinedVal, true
		}

		h.metrics = &OptimizationMetrics{
			Algorithm:   "Hybrid(GridSearch)",
			Iterations:  totalIterations,
			Evaluations: totalEvaluations,
			Dimensions:  h.Grid.metrics.Dimensions,
			Duration:    time.Since(startTime),
			BestValue:   gridValue,
			Found:       true,
		}
		return gridResult, gridValue, true
	}

	// Nothing found
	dims := 0
	if len(bounds.Lower) > 0 {
		dims = len(bounds.Lower)
	}
	h.metrics = &OptimizationMetrics{
		Algorithm:   "Hybrid(NoProfit)",
		Iterations:  totalIterations,
		Evaluations: totalEvaluations,
		Dimensions:  dims,
		Duration:    time.Since(startTime),
		BestValue:   DecZero,
		Found:       false,
	}
	return nil, DecZero, false
}

// TernarySearchOptimizer uses coordinate descent with ternary search per dimension.
// More robust than BinarySearch as it optimizes each dimension independently.
//
// Key insight: Whaleswap's self-netting means pool order doesn't matter
// and no cycle is needed. Any set of swaps with net positive output is profit.
type TernarySearchOptimizer struct {
	MaxIterations int
	MaxPools      int

	// metrics stores results from the last optimization run
	metrics *OptimizationMetrics
}

// GetMetrics returns metrics from the last optimization run.
func (t *TernarySearchOptimizer) GetMetrics() *OptimizationMetrics {
	return t.metrics
}

// Optimize implements ArbitrageOptimizer using coordinate ternary search.
// For each dimension, performs ternary search to find optimal value while
// holding other dimensions fixed. Iterates until convergence.
func (t *TernarySearchOptimizer) Optimize(
	objective func([]math.LegacyDec) math.LegacyDec,
	bounds OptimizationBounds,
	initialGuess []math.LegacyDec,
) (optimal []math.LegacyDec, value math.LegacyDec, found bool) {
	startTime := time.Now()
	evaluations := 0

	n := len(bounds.Lower)
	if n == 0 {
		t.metrics = &OptimizationMetrics{
			Algorithm:   "TernarySearch",
			Iterations:  0,
			Evaluations: 0,
			Dimensions:  0,
			Duration:    time.Since(startTime),
			BestValue:   DecZero,
			Found:       false,
		}
		return nil, DecZero, false
	}

	// Limit dimensions
	activeDims := n
	if activeDims > t.MaxPools {
		activeDims = t.MaxPools
	}

	// Start from center of bounds
	two := math.LegacyNewDec(2)
	three := math.LegacyNewDec(3)
	convergenceThreshold := DecOne // converge when range < 1

	x := make([]math.LegacyDec, n)
	for i := 0; i < n; i++ {
		if i < activeDims {
			x[i] = bounds.Lower[i].Add(bounds.Upper[i]).Quo(two)
		} else {
			x[i] = DecZero
		}
	}

	// Coordinate descent with ternary search
	actualIters := 0
	for iter := 0; iter < t.MaxIterations; iter++ {
		actualIters = iter + 1
		improved := false

		for i := 0; i < activeDims; i++ {
			lo := bounds.Lower[i]
			hi := bounds.Upper[i]

			// Ternary search on dimension i
			for hi.Sub(lo).GT(convergenceThreshold) {
				rangeVal := hi.Sub(lo)
				m1 := lo.Add(rangeVal.Quo(three))
				m2 := hi.Sub(rangeVal.Quo(three))

				// Evaluate at m1
				x1 := make([]math.LegacyDec, n)
				copy(x1, x)
				x1[i] = m1
				evaluations++
				v1 := objective(x1)

				// Evaluate at m2
				x2 := make([]math.LegacyDec, n)
				copy(x2, x)
				x2[i] = m2
				evaluations++
				v2 := objective(x2)

				if v1.GT(v2) {
					hi = m2
				} else {
					lo = m1
				}
			}

			// Test the midpoint
			mid := lo.Add(hi).Quo(two)
			xtest := make([]math.LegacyDec, n)
			copy(xtest, x)
			xtest[i] = mid

			evaluations += 2 // both objective(xtest) and objective(x)
			if objective(xtest).GT(objective(x)) {
				x[i] = mid
				improved = true
			}
		}

		if !improved {
			break
		}
	}

	evaluations++
	val := objective(x)
	foundProfit := val.IsPositive()

	t.metrics = &OptimizationMetrics{
		Algorithm:   "TernarySearch",
		Iterations:  actualIters,
		Evaluations: evaluations,
		Dimensions:  activeDims,
		Duration:    time.Since(startTime),
		BestValue:   val,
		Found:       foundProfit,
	}

	if !foundProfit {
		return nil, val, false
	}

	return x, val, true
}
