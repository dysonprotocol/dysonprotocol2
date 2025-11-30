# Whaleswap Arbitrage Detection System

## Overview

This module provides deterministic arbitrage detection for whaleswap pools. When a pool is updated (via swap, add liquidity, etc.), the system can find and execute profitable circular arbitrage opportunities.

## Key Design Decisions

### 1. Use Actual MakeTrade with CacheContext

The simulation uses the **actual `MakeTrade` implementation** with a `CacheContext`:
- Ensures simulation matches real execution exactly
- No duplicated AMM math that could drift out of sync
- CacheContext discards all state changes after each evaluation
- Deterministic across all nodes

```go
// In SimulateArbitrage:
cacheCtx, _ := ac.Ctx.CacheContext()
resp, err := ac.Keeper.MakeTrade(cacheCtx, msg)
// Changes to cacheCtx are discarded
```

### 2. Pool Graph Construction

Starting from affected denoms, expands the pool graph by N hops:
```
depth=0: Only pools directly containing affected denoms
depth=1: Pools 1 hop away (connected via shared denoms)
depth=2: 2 hops, etc.
```

### 3. Objective Function

The optimizer maximizes profit in a reference denom. The objective function:
1. Converts float64 swap amounts to int64
2. Builds a `MsgMakeTrade` with swap operations
3. Executes on CacheContext
4. Returns profit (or large negative value on failure)

### 4. Self-Netting for Circular Arbitrage

`MsgMakeTrade` supports circular arbitrage through self-netting:
- A→B→C→A cycle can result in net profit with zero inputs
- Trader debit/credit pairs by denom are netted out automatically

## Files

- `arbitrage.go` - Core types and simulation logic
- `arbitrage_optimizer.go` - Optimizer implementations (Grid, Nelder-Mead, Hybrid)
- `arbitrage_runner.go` - High-level runner for detection and execution

## Usage

### Basic Usage

```go
// In your msg interceptor or post handler:
func (h *Handler) Post(ctx sdk.Context, msg sdk.Msg, result *sdk.Result, err error) {
    if err != nil || !keeper.ShouldCheckArbitrage(msg) {
        return
    }
    
    // Get affected denoms from the message
    affectedDenoms := keeper.GetPoolDenomsFromMsg(msg)
    if len(affectedDenoms) == 0 {
        return
    }
    
    // Run arbitrage detection
    runner := keeper.NewArbitrageRunner(h.whaleswapKeeper)
    arbResult, _ := runner.CheckAndExecuteArbitrage(
        ctx,
        h.arbitrageTrader,  // module account or designated arbitrageur
        affectedDenoms,
        "udys",             // reference denom for profit
    )
    
    if arbResult != nil {
        logger.Info("arbitrage executed", "profit", arbResult.Profit)
    }
}
```

### Simulation Only (for queries/testing)

```go
runner := keeper.NewArbitrageRunner(h.whaleswapKeeper)
result, err := runner.SimulateOnly(ctx, trader, affectedDenoms, "udys")
if result != nil && result.Success {
    fmt.Printf("Found arb opportunity: profit %s\n", result.Profit)
}
```

### Custom Optimizer

```go
runner := keeper.NewArbitrageRunner(h.whaleswapKeeper).
    WithOptimizer(&keeper.GridSearchOptimizer{
        GridPoints: 10,
        MaxPools:   6,
    })
```

## Optimizer Options

### GridSearchOptimizer
- Simple, deterministic exhaustive search
- Best for small pool counts (≤4 pools)
- O(GridPoints^N) evaluations

### NelderMeadOptimizer  
- Gradient-free simplex optimization
- More efficient for larger pool counts
- Deterministic with fixed initial conditions

### HybridOptimizer (default)
- Coarse grid search → Nelder-Mead refinement
- Good balance of exploration and exploitation

## Configuration

```go
runner := &ArbitrageRunner{
    keeper:         k,
    optimizer:      NewHybridOptimizer(),
    MaxDepth:       1,     // include pools 1 hop away
    MaxFraction:    0.1,   // max 10% of pool reserve per swap
    MinProfitBasis: 10,    // require 0.1% profit minimum
}
```

## Integration Points

### Option 1: MsgInterceptor (recommended)

Add to `post.go`:
```go
type ArbitrageMsgInterceptor struct {
    whaleswapKeeper *whaleswapkeeper.Keeper
    arbitrageTrader string
}

func (i *ArbitrageMsgInterceptor) Post(ctx sdk.Context, msg sdk.Msg, result *sdk.Result, err error) {
    if err != nil {
        return
    }
    if !whaleswapkeeper.ShouldCheckArbitrage(msg) {
        return
    }
    // ... run arbitrage
}
```

### Option 2: EndBlocker

Check for arbitrage opportunities at end of each block across all pools.

### Option 3: Query Endpoint

Add a query to check for arbitrage without execution:
```protobuf
rpc SimulateArbitrage(SimulateArbitrageRequest) returns (SimulateArbitrageResponse);
```

## Determinism

All components are deterministic:
- Optimizer uses fixed-seed or deterministic algorithms
- Pool iteration order is consistent (by pool ID)
- Float64 math uses IEEE 754 (consistent across platforms)
- MakeTrade implementation is deterministic

## Performance Considerations

- Grid search: O(GridPoints^min(N, MaxPools)) evaluations
- Each evaluation runs full MakeTrade on CacheContext
- Typical execution: <10ms for 4 pools
- Consider limiting MaxDepth and MaxPools for large pool graphs
