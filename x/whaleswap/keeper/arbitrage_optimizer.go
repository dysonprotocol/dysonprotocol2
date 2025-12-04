package keeper

// This file is kept for backwards compatibility with imports.
// The LIGHTNING algorithm in arbitrage.go handles optimization internally.

// OptimizationMetrics is kept for compatibility with query responses.
type OptimizationMetrics struct {
	Algorithm     string
	Iterations    int
	PathsFound    int
	TotalOps      int
	DurationMs    int64
	Found         bool
}
