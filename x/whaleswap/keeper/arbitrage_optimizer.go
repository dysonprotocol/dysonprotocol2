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
	// Algorithm is the name of the optimizer used
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

// ClosedFormOptimizer evaluates the closed-form estimate from FLOOD.
// For constant-product AMMs, FLOOD computes the analytically optimal trade amount.
// No numerical refinement needed - the closed-form IS optimal.
type ClosedFormOptimizer struct {
	MaxPools int // limit active dimensions

	// metrics stores results from the last optimization run
	metrics *OptimizationMetrics
}

// NewHybridOptimizer creates a closed-form optimizer.
// Named "Hybrid" for backwards compatibility but only uses closed-form.
func NewHybridOptimizer() *ClosedFormOptimizer {
	return &ClosedFormOptimizer{
		MaxPools: 20, // supports up to 10 pools (20 dimensions)
	}
}

// GetMetrics returns metrics from the last optimization run.
func (o *ClosedFormOptimizer) GetMetrics() *OptimizationMetrics {
	return o.metrics
}

// Optimize evaluates the closed-form estimate and returns it if profitable.
// For constant-product AMMs, the closed-form from FLOOD is analytically optimal.
func (o *ClosedFormOptimizer) Optimize(
	objective func([]math.LegacyDec) math.LegacyDec,
	bounds OptimizationBounds,
	initialGuess []math.LegacyDec,
) (optimal []math.LegacyDec, value math.LegacyDec, found bool) {
	startTime := time.Now()

	n := len(bounds.Lower)
	if n == 0 {
		o.metrics = &OptimizationMetrics{
			Algorithm:   "CF(NoPool)",
			Evaluations: 0,
			Dimensions:  0,
			Duration:    time.Since(startTime),
			BestValue:   DecZero,
			Found:       false,
		}
		return nil, DecZero, false
	}

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

	if !hasClosedForm {
		o.metrics = &OptimizationMetrics{
			Algorithm:   "CF(NoCycle)",
			Evaluations: 0,
			Dimensions:  n,
			Duration:    time.Since(startTime),
			BestValue:   DecMinValue,
			Found:       false,
		}
		return nil, DecMinValue, false
	}

	// Evaluate the closed-form estimate
	cfVal := objective(initialGuess)

	if !cfVal.IsPositive() {
		o.metrics = &OptimizationMetrics{
			Algorithm:   "CF(NoProfit)",
			Evaluations: 1,
			Dimensions:  n,
			Duration:    time.Since(startTime),
			BestValue:   cfVal,
			Found:       false,
		}
		return nil, cfVal, false
	}

	// Closed-form is profitable - return it
	o.metrics = &OptimizationMetrics{
		Algorithm:     fmt.Sprintf("CF:%s", cfVal.TruncateInt().String()),
		Iterations:    1,
		Evaluations:   1,
		Dimensions:    n,
		Duration:      time.Since(startTime),
		BestValue:     cfVal,
		BestIteration: 0,
		Found:         true,
	}

	return initialGuess, cfVal, true
}
