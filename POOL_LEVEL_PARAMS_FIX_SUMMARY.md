# Pool-Level Parameters Fix - Summary

## ✅ Changes Completed

Successfully moved leverage risk parameters from **module-level** (global) to **pool-level** (per-pool), allowing each pool operator to set their own risk tolerance.

---

## Files Modified

### 1. `proto/dysonprotocol/whaleswap/v1/whaleswap.proto`
**Added to Pool message (fields 21-23):**
```protobuf
string min_collateral_ratio = 21;       // Pool-specific min CR at open (e.g., "1.5")
string max_leverage_ratio = 22;         // Pool-specific max leverage (e.g., "5.0")
string liquidation_threshold = 23;      // Pool-specific liquidation CR threshold (e.g., "1.2")
```

**Impact**: Each pool now controls its own health/liquidation parameters

### 2. `proto/dysonprotocol/whaleswap/v1/leverage.proto`
**Removed from LeverageParams** (no longer needed):
- ❌ `min_collateral_ratio`
- ❌ `max_leverage_ratio`
- ❌ `liquidation_threshold`

**Kept in LeverageParams** (module-level, protocol-wide):
```protobuf
uint64 block_delay_before_close = 1;
uint64 block_delay_before_liquidation = 2;  // ADDED
```

**Impact**: LeverageParams now contains only global/protocol settings

### 3. `x/whaleswap/types/params.go`
**Updated DefaultLeverageParams():**
```go
// OLD: MinCollateralRatio, MaxLeverageRatio, LiquidationThreshold (all gone)
// NEW:
BlockDelayBeforeClose:       1,
BlockDelayBeforeLiquidation: 1,
```

**Updated Validate():**
- Removed validation for 3 pool-specific params
- Added validation for `BlockDelayBeforeLiquidation`

### 4. `x/whaleswap/keeper/msg_leverage_open.go`
**OpenLongPosition changes:**
```go
// OLD: params, _ := k.leverageParams.Get(ctx); minCR := params.MinCollateralRatio
// NEW: minCR := pool.MinCollateralRatio (parsed from string if set)

// ADDED: Max leverage validation
leverage := (collateral + borrowed) / collateral
if leverage > pool.MaxLeverageRatio: return error
```

**OpenShortPosition changes:**
- Same updates as OpenLongPosition

### 5. `x/whaleswap/keeper/query_leverage_health.go`
**PositionHealth changes:**
```go
// OLD: liquidationThreshold, _ := k.leverageParams.Get(ctx)
// NEW: liquidationThreshold := pool.LiquidationThreshold
```

### 6. `x/whaleswap/keeper/msg_leverage_handlers.go`
**InitializeLiquidation changes:**
```go
// OLD: threshold := params.LiquidationThreshold
// NEW: threshold := pool.LiquidationThreshold
```

---

## Behavior Changes

### Before
```
All pools: min_collateral_ratio = 1.5, max_leverage = 20x, liquidation = 1.2
-> All pools have identical risk parameters
-> Pool operators cannot customize
```

### After
```
Pool A (USDC/ETH - Blue Chip):
  min_collateral_ratio: 1.5
  max_leverage_ratio:   20x
  liquidation_threshold: 1.2

Pool B (USDC/SHIB - Risky):
  min_collateral_ratio: 2.5
  max_leverage_ratio:   5x
  liquidation_threshold: 1.5
```

### Per-Pool Configuration Options

**Conservative Pool:**
- `min_collateral_ratio: 2.5` (require 250% collateral)
- `max_leverage_ratio: 3x` (prevent over-leverage)
- `liquidation_threshold: 1.3` (liquidate sooner)

**Aggressive Pool:**
- `min_collateral_ratio: 1.3` (allow 130% collateral)
- `max_leverage_ratio: 50x` (allow high leverage)
- `liquidation_threshold: 1.05` (liquidate only when critical)

---

## Validation Flow

**At Position Open (msg_leverage_open.go):**
1. Load pool parameters
2. Parse `pool.MinCollateralRatio` (default "1.5" if not set)
3. Calculate position CR = collateral / borrowed
4. Validate: CR >= min_collateral_ratio ✅
5. Calculate leverage = (collateral + borrowed) / collateral
6. Validate: leverage <= max_leverage_ratio ✅

**At Health Query (query_leverage_health.go):**
1. Load pool parameters
2. Parse `pool.LiquidationThreshold` (default "1.2" if not set)
3. Calculate health status based on CR vs threshold

**At Liquidation (msg_leverage_handlers.go):**
1. Load pool parameters
2. Use `pool.LiquidationThreshold` for liquidation checks

---

## Protocol-Level Parameters (LeverageParams)

Now contains only global/consensus settings:
```go
BlockDelayBeforeClose: 1       // How long owner must wait before closing
BlockDelayBeforeLiquidation: 1 // How long owner must wait after liquidation init
```

These are protocol-wide and apply to all pools.

---

## Backwards Compatibility

⚠️ **Breaking Change**: Any genesis state or stored `LeverageParams` with the old 3 fields will fail validation.

✅ **Mitigation**: Migration handler can:
1. Ignore the old fields
2. Set all pools with defaults: "1.5", "5.0", "1.2"
3. Pool operators can then update per-pool settings via governance

---

## Build Status

✅ Proto generation: SUCCESS
✅ Go compilation: SUCCESS
✅ All keeper logic updated: SUCCESS

---

## Next Steps (Optional)

1. Add CLI for pool operators to update leverage parameters
2. Add genesis migration for existing pools
3. Add events when pool-level parameters change
4. Add governance proposals for pool parameter updates

