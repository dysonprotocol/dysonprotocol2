package keeper

// ArbitrageOptimizer is the interface for a deterministic black-box optimizer.
// The optimizer must be deterministic to ensure consensus across all nodes.
type ArbitrageOptimizer interface {
	// Optimize finds the optimal swap amounts to maximize profit.
	//
	// Parameters:
	//   - objective: function to maximize; takes []float64 returns float64
	//   - bounds: lower and upper bounds for each variable
	//   - initialGuess: starting point for optimization
	//
	// Returns:
	//   - optimal: the optimal swap amounts found
	//   - value: the objective value at optimal point
	//   - found: true if a profitable solution was found
	Optimize(
		objective func([]float64) float64,
		bounds OptimizationBounds,
		initialGuess []float64,
	) (optimal []float64, value float64, found bool)
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
}

// Optimize implements ArbitrageOptimizer using grid search.
func (g *GridSearchOptimizer) Optimize(
	objective func([]float64) float64,
	bounds OptimizationBounds,
	initialGuess []float64,
) (optimal []float64, value float64, found bool) {
	n := len(bounds.Lower)
	if n == 0 {
		return nil, 0, false
	}

	// Limit dimensions for tractability
	activeDims := n
	if activeDims > g.MaxPools {
		activeDims = g.MaxPools
	}

	// Generate grid points for each active dimension
	grids := make([][]float64, activeDims)
	for i := 0; i < activeDims; i++ {
		lower := bounds.Lower[i]
		upper := bounds.Upper[i]
		grids[i] = make([]float64, g.GridPoints)
		for j := 0; j < g.GridPoints; j++ {
			t := float64(j) / float64(g.GridPoints-1)
			grids[i][j] = lower + t*(upper-lower)
		}
	}

	// Evaluate all grid combinations
	bestValue := -1e18
	bestPoint := make([]float64, n)

	// Use indices to enumerate all combinations
	indices := make([]int, activeDims)
	point := make([]float64, n)

	for {
		// Build current point from indices
		for i := 0; i < activeDims; i++ {
			point[i] = grids[i][indices[i]]
		}
		// Zero out dimensions beyond MaxPools
		for i := activeDims; i < n; i++ {
			point[i] = 0
		}

		// Evaluate
		val := objective(point)
		if val > bestValue {
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
	if bestValue <= 0 {
		return nil, bestValue, false
	}

	return bestPoint, bestValue, true
}

// NelderMeadOptimizer implements Nelder-Mead simplex for deterministic optimization.
// More efficient than grid search for higher dimensions.
type NelderMeadOptimizer struct {
	MaxIterations int
	Tolerance     float64
	MaxPools      int // limit active dimensions
}

// Optimize implements ArbitrageOptimizer using Nelder-Mead.
// Note: We negate the objective since Nelder-Mead typically minimizes.
func (nm *NelderMeadOptimizer) Optimize(
	objective func([]float64) float64,
	bounds OptimizationBounds,
	initialGuess []float64,
) (optimal []float64, value float64, found bool) {
	totalDims := len(bounds.Lower)
	if totalDims == 0 {
		return nil, 0, false
	}

	// Limit active dimensions
	n := totalDims
	if n > nm.MaxPools {
		n = nm.MaxPools
	}

	// Nelder-Mead parameters
	alpha := 1.0 // reflection
	gamma := 2.0 // expansion
	rho := 0.5   // contraction
	sigma := 0.5 // shrink

	// Wrapper to handle full dimension vector
	evalFull := func(partial []float64) float64 {
		full := make([]float64, totalDims)
		copy(full, partial)
		return objective(full)
	}

	// Initialize simplex with n+1 vertices
	simplex := make([][]float64, n+1)
	values := make([]float64, n+1)

	// First vertex: initial guess or center of bounds
	simplex[0] = make([]float64, n)
	if len(initialGuess) >= n {
		copy(simplex[0], initialGuess[:n])
	} else {
		for i := 0; i < n; i++ {
			simplex[0][i] = (bounds.Lower[i] + bounds.Upper[i]) / 2
		}
	}

	// Remaining vertices: offset along each axis
	for i := 1; i <= n; i++ {
		simplex[i] = make([]float64, n)
		copy(simplex[i], simplex[0])
		// Offset by 10% of range or 1.0, whichever is larger
		delta := (bounds.Upper[i-1] - bounds.Lower[i-1]) * 0.1
		if delta < 1.0 {
			delta = 1.0
		}
		simplex[i][i-1] += delta
		// Clamp to bounds
		if simplex[i][i-1] > bounds.Upper[i-1] {
			simplex[i][i-1] = bounds.Upper[i-1]
		}
	}

	// Evaluate initial simplex (negate for minimization)
	for i := 0; i <= n; i++ {
		values[i] = -evalFull(simplex[i])
	}

	// Main loop
	for iter := 0; iter < nm.MaxIterations; iter++ {
		// Sort vertices by value (ascending = best to worst for minimization)
		for i := 0; i <= n; i++ {
			for j := i + 1; j <= n; j++ {
				if values[j] < values[i] {
					simplex[i], simplex[j] = simplex[j], simplex[i]
					values[i], values[j] = values[j], values[i]
				}
			}
		}

		// Check convergence
		if values[n]-values[0] < nm.Tolerance {
			break
		}

		// Compute centroid of all but worst
		centroid := make([]float64, n)
		for i := 0; i < n; i++ {
			sum := 0.0
			for j := 0; j < n; j++ {
				sum += simplex[j][i]
			}
			centroid[i] = sum / float64(n)
		}

		// Reflection
		reflected := make([]float64, n)
		for i := 0; i < n; i++ {
			reflected[i] = centroid[i] + alpha*(centroid[i]-simplex[n][i])
			// Clamp to bounds
			if reflected[i] < bounds.Lower[i] {
				reflected[i] = bounds.Lower[i]
			}
			if reflected[i] > bounds.Upper[i] {
				reflected[i] = bounds.Upper[i]
			}
		}
		reflectedVal := -evalFull(reflected)

		// Accept reflection if better than worst (standard NM accepts if better than second-worst,
		// but being more permissive helps exploration in bounded spaces)
		if reflectedVal < values[n] {
			// Check if we should try expansion (reflected is best so far)
			if reflectedVal < values[0] {
				// Try expansion
				expanded := make([]float64, n)
				for i := 0; i < n; i++ {
					expanded[i] = centroid[i] + gamma*(reflected[i]-centroid[i])
					if expanded[i] < bounds.Lower[i] {
						expanded[i] = bounds.Lower[i]
					}
					if expanded[i] > bounds.Upper[i] {
						expanded[i] = bounds.Upper[i]
					}
				}
				expandedVal := -evalFull(expanded)
				if expandedVal < reflectedVal {
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
		contracted := make([]float64, n)
		for i := 0; i < n; i++ {
			contracted[i] = centroid[i] + rho*(simplex[n][i]-centroid[i])
			if contracted[i] < bounds.Lower[i] {
				contracted[i] = bounds.Lower[i]
			}
			if contracted[i] > bounds.Upper[i] {
				contracted[i] = bounds.Upper[i]
			}
		}
		contractedVal := -evalFull(contracted)
		if contractedVal < values[n] {
			copy(simplex[n], contracted)
			values[n] = contractedVal
			continue
		}

		// Shrink
		for i := 1; i <= n; i++ {
			for j := 0; j < n; j++ {
				simplex[i][j] = simplex[0][j] + sigma*(simplex[i][j]-simplex[0][j])
			}
			values[i] = -evalFull(simplex[i])
		}
	}

	// Build full result vector
	result := make([]float64, totalDims)
	copy(result, simplex[0])

	// Return best found (negate back to original objective scale)
	bestValue := -values[0]
	if bestValue <= 0 {
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
			Tolerance:     0.5,
			MaxPools:      8,
		},
	}
}

// Optimize implements ArbitrageOptimizer using hybrid approach:
// 1. TernarySearch finds optimal via coordinate descent
// 2. NelderMead polishes to true local maximum
func (h *HybridOptimizer) Optimize(
	objective func([]float64) float64,
	bounds OptimizationBounds,
	initialGuess []float64,
) (optimal []float64, value float64, found bool) {
	// Phase 1: TernarySearch (coordinate descent) finds a good solution
	ts := &TernarySearchOptimizer{MaxIterations: 10, MaxPools: 4}
	tsResult, tsValue, tsFound := ts.Optimize(objective, bounds, initialGuess)

	if tsFound && tsValue > 0 {
		// Phase 2: NelderMead refines the result
		refined, refinedVal, refinedOk := h.NelderMead.Optimize(objective, bounds, tsResult)
		if refinedOk && refinedVal > tsValue {
			return refined, refinedVal, true
		}
		// Refinement didn't improve - return original
		return tsResult, tsValue, true
	}

	// Fallback: GridSearch if TernarySearch found nothing
	gridResult, gridValue, gridFound := h.Grid.Optimize(objective, bounds, initialGuess)
	if gridFound && gridValue > 0 {
		// Try to refine grid result too
		refined, refinedVal, refinedOk := h.NelderMead.Optimize(objective, bounds, gridResult)
		if refinedOk && refinedVal > gridValue {
			return refined, refinedVal, true
		}
		return gridResult, gridValue, true
	}

	return nil, 0, false
}

// TernarySearchOptimizer uses coordinate descent with ternary search per dimension.
// More robust than BinarySearch as it optimizes each dimension independently.
//
// Key insight: Whaleswap's self-netting means pool order doesn't matter
// and no cycle is needed. Any set of swaps with net positive output is profit.
type TernarySearchOptimizer struct {
	MaxIterations int
	MaxPools      int
}

// Optimize implements ArbitrageOptimizer using coordinate ternary search.
// For each dimension, performs ternary search to find optimal value while
// holding other dimensions fixed. Iterates until convergence.
func (t *TernarySearchOptimizer) Optimize(
	objective func([]float64) float64,
	bounds OptimizationBounds,
	initialGuess []float64,
) (optimal []float64, value float64, found bool) {
	n := len(bounds.Lower)
	if n == 0 {
		return nil, 0, false
	}

	// Limit dimensions
	activeDims := n
	if activeDims > t.MaxPools {
		activeDims = t.MaxPools
	}

	// Start from center of bounds
	x := make([]float64, n)
	for i := 0; i < activeDims; i++ {
		x[i] = (bounds.Lower[i] + bounds.Upper[i]) / 2
	}

	// Coordinate descent with ternary search
	for iter := 0; iter < t.MaxIterations; iter++ {
		improved := false

		for i := 0; i < activeDims; i++ {
			lo, hi := bounds.Lower[i], bounds.Upper[i]

			// Ternary search on dimension i
			for hi-lo > 1.0 {
				m1 := lo + (hi-lo)/3
				m2 := hi - (hi-lo)/3

				// Evaluate at m1
				x1 := make([]float64, n)
				copy(x1, x)
				x1[i] = m1
				v1 := objective(x1)

				// Evaluate at m2
				x2 := make([]float64, n)
				copy(x2, x)
				x2[i] = m2
				v2 := objective(x2)

				if v1 > v2 {
					hi = m2
				} else {
					lo = m1
				}
			}

			// Test the midpoint
			mid := (lo + hi) / 2
			xtest := make([]float64, n)
			copy(xtest, x)
			xtest[i] = mid

			if objective(xtest) > objective(x) {
				x[i] = mid
				improved = true
			}
		}

		if !improved {
			break
		}
	}

	val := objective(x)
	if val <= 0 {
		return nil, val, false
	}

	return x, val, true
}
