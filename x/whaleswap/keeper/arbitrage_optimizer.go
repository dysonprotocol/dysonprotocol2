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

// NewGridSearchOptimizer creates a grid search optimizer with default settings.
func NewGridSearchOptimizer() *GridSearchOptimizer {
	return &GridSearchOptimizer{
		GridPoints: 7, // 7 points: -max, -2/3*max, -1/3*max, 0, 1/3*max, 2/3*max, max
		MaxPools:   4, // limit to 4 pools to keep evaluations manageable (7^4 = 2401)
	}
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

// NewNelderMeadOptimizer creates a Nelder-Mead optimizer.
func NewNelderMeadOptimizer() *NelderMeadOptimizer {
	return &NelderMeadOptimizer{
		MaxIterations: 100,
		Tolerance:     1.0, // 1 unit of denom tolerance
		MaxPools:      8,   // can handle more pools than grid search
	}
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

		if reflectedVal >= values[0] && reflectedVal < values[n-1] {
			// Accept reflection
			copy(simplex[n], reflected)
			values[n] = reflectedVal
			continue
		}

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

		// Contraction
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

// HybridOptimizer runs grid search first, then refines with Nelder-Mead.
// Good balance of exploration and exploitation.
type HybridOptimizer struct {
	Grid       *GridSearchOptimizer
	NelderMead *NelderMeadOptimizer
}

// NewHybridOptimizer creates a hybrid optimizer.
func NewHybridOptimizer() *HybridOptimizer {
	// Use BinarySearchOptimizer as the primary method
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

// Optimize implements ArbitrageOptimizer using hybrid approach.
func (h *HybridOptimizer) Optimize(
	objective func([]float64) float64,
	bounds OptimizationBounds,
	initialGuess []float64,
) (optimal []float64, value float64, found bool) {
	// Try binary search first - it's more efficient for arbitrage
	bs := NewBinarySearchOptimizer()
	bsResult, bsValue, bsFound := bs.Optimize(objective, bounds, initialGuess)
	if bsFound && bsValue > 0 {
		return bsResult, bsValue, true
	}

	// Fallback to grid search
	gridResult, gridValue, gridFound := h.Grid.Optimize(objective, bounds, initialGuess)
	if gridFound && gridValue > 0 {
		return gridResult, gridValue, true
	}

	return nil, 0, false
}

// BinarySearchOptimizer finds arbitrage by:
// 1. Testing small amounts in each direction to find ANY profit
// 2. Exponentially increasing until profit decreases
// 3. Binary search to find optimal amount
type BinarySearchOptimizer struct {
	MaxPools      int
	MaxIterations int
}

// NewBinarySearchOptimizer creates a binary search optimizer.
func NewBinarySearchOptimizer() *BinarySearchOptimizer {
	return &BinarySearchOptimizer{
		MaxPools:      4,
		MaxIterations: 20,
	}
}

// Optimize implements ArbitrageOptimizer using binary search approach.
func (bs *BinarySearchOptimizer) Optimize(
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
	if activeDims > bs.MaxPools {
		activeDims = bs.MaxPools
	}

	// Phase 1: Find a profitable direction by testing small amounts
	// Try each combination of directions (2^n combinations for n pools)
	bestPoint := make([]float64, n)
	bestValue := -1e18

	// Generate direction combinations: each pool can go +1 or -1 or 0
	// For efficiency, just try: all positive, all negative, and alternating
	directionSets := bs.generateDirections(activeDims)

	// Try different starting amounts: 1, 5, 10, 20 to find any profit
	startAmounts := []float64{1, 5, 10, 20, 50}

	for _, dirs := range directionSets {
		for _, startAmt := range startAmounts {
			point := make([]float64, n)
			for i := 0; i < activeDims; i++ {
				point[i] = float64(dirs[i]) * startAmt
			}

			val := objective(point)
			if val > 0 {
				// Found profit! Now scale up to find optimal
				scaledPoint, scaledVal := bs.scaleToOptimal(objective, point, bounds, activeDims)
				if scaledVal > bestValue {
					bestValue = scaledVal
					copy(bestPoint, scaledPoint)
				}
			}
		}
	}

	if bestValue <= 0 {
		return nil, bestValue, false
	}

	return bestPoint, bestValue, true
}

// generateDirections creates direction combinations to try.
// Returns slice of direction vectors where each element is -1, 0, or +1.
func (bs *BinarySearchOptimizer) generateDirections(n int) [][]int {
	// For circular arbitrage, we want to try various direction combinations
	// Key insight: profitable arb usually has SAME amounts in all pools
	// to enable self-netting (output of one pool feeds next)
	dirs := make([][]int, 0)

	// Try all positive (sell denom0 in each pool)
	allPos := make([]int, n)
	for i := range allPos {
		allPos[i] = 1
	}
	dirs = append(dirs, allPos)

	// Try all negative (sell denom1 in each pool)
	allNeg := make([]int, n)
	for i := range allNeg {
		allNeg[i] = -1
	}
	dirs = append(dirs, allNeg)

	// Try alternating patterns
	alt1 := make([]int, n)
	alt2 := make([]int, n)
	for i := range alt1 {
		if i%2 == 0 {
			alt1[i] = 1
			alt2[i] = -1
		} else {
			alt1[i] = -1
			alt2[i] = 1
		}
	}
	dirs = append(dirs, alt1, alt2)

	// For 3 pools, try all 8 combinations of +/- (2^3)
	if n >= 3 {
		signs := []int{1, -1}
		for _, s0 := range signs {
			for _, s1 := range signs {
				for _, s2 := range signs {
					d := make([]int, n)
					d[0], d[1], d[2] = s0, s1, s2
					dirs = append(dirs, d)
				}
			}
		}
	}

	return dirs
}

// scaleToOptimal scales a profitable direction to find optimal amounts.
// Uses exponential search then binary search.
func (bs *BinarySearchOptimizer) scaleToOptimal(
	objective func([]float64) float64,
	direction []float64,
	bounds OptimizationBounds,
	activeDims int,
) ([]float64, float64) {
	n := len(direction)

	// Phase 2: Exponential search - keep doubling until profit decreases
	scale := 1.0
	prevVal := objective(direction)
	prevScale := scale

	for iter := 0; iter < bs.MaxIterations; iter++ {
		scale *= 2.0

		// Check if we'd exceed bounds
		exceeded := false
		for i := 0; i < activeDims; i++ {
			amt := direction[i] * scale
			if amt > 0 && amt > bounds.Upper[i] {
				scale = bounds.Upper[i] / direction[i]
				exceeded = true
			} else if amt < 0 && amt < bounds.Lower[i] {
				scale = bounds.Lower[i] / direction[i]
				exceeded = true
			}
		}

		point := make([]float64, n)
		for i := 0; i < activeDims; i++ {
			point[i] = direction[i] * scale
		}

		val := objective(point)
		if val <= prevVal || exceeded {
			// Profit decreased or hit bounds - optimal is between prevScale and scale
			break
		}
		prevVal = val
		prevScale = scale
	}

	// Phase 3: Binary search between prevScale and scale
	lowScale := prevScale
	highScale := scale

	for iter := 0; iter < bs.MaxIterations; iter++ {
		if highScale-lowScale < 1.0 {
			break // Close enough
		}

		midScale := (lowScale + highScale) / 2.0
		midPoint := make([]float64, n)
		for i := 0; i < activeDims; i++ {
			midPoint[i] = direction[i] * midScale
		}
		midVal := objective(midPoint)

		// Try slightly higher
		highMidScale := (midScale + highScale) / 2.0
		highMidPoint := make([]float64, n)
		for i := 0; i < activeDims; i++ {
			highMidPoint[i] = direction[i] * highMidScale
		}
		highMidVal := objective(highMidPoint)

		if highMidVal > midVal {
			// Optimal is in upper half
			lowScale = midScale
		} else {
			// Optimal is in lower half
			highScale = midScale
		}
	}

	// Return best point found
	bestScale := (lowScale + highScale) / 2.0
	bestPoint := make([]float64, n)
	for i := 0; i < activeDims; i++ {
		bestPoint[i] = direction[i] * bestScale
	}
	bestVal := objective(bestPoint)

	return bestPoint, bestVal
}
