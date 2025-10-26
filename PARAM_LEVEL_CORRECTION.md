# Parameter Level Correction

## ✅ Spec is CORRECT

Each pool operator should set their own leverage risk parameters.

### Why Pool-Level Makes Sense

| Parameter | Pool Operator Control | Reasoning |
|-----------|----------------------|-----------|
| `min_collateral_ratio` | ✅ Per-pool | Deep USDC/ETH pool: 1.5x (conservative). New USDC/SHIB pool: 2.0x (cautious). |
| `max_leverage_ratio` | ✅ Per-pool | Blue-chip pairs: 20x leverage OK. Volatile pairs: 5x max. |
| `liquidation_threshold` | ✅ Per-pool | Stable pairs: liquidate at 1.1x. Volatile pairs: liquidate at 1.3x. |
| `interest_rate_coin1/2` | ✅ Per-pool | USDC in deep pool: 3% APY. USDC in new pool: 10% APY (compensation for risk). |
| `max_borrow_percent_coin1/2` | ✅ Per-pool | Deep reserve: borrow up to 80%. Shallow reserve: borrow up to 20%. |

---

## ❌ Implementation Issue

The implementation incorrectly puts health/liquidation rules in **Module-Level** `LeverageParams` instead of **Pool-Level** `Pool`.

### What's Wrong in Code

```go
// CURRENT (WRONG):
type LeverageParams struct {
  MinCollateralRatio    LegacyDec      // Global, same for all pools
  MaxLeverageRatio      LegacyDec      // Global, same for all pools
  LiquidationThreshold  LegacyDec      // Global, same for all pools
  BlockDelayBeforeClose uint64         // ✅ This one is correct (protocol-wide)
}

// Pool has these (correct):
Pool.InterestRateCoin1
Pool.InterestRateCoin2
Pool.MaxBorrowPercentCoin1
Pool.MaxBorrowPercentCoin2

// But MISSING: (should be pool-specific)
// Pool.MinCollateralRatio
// Pool.MaxLeverageRatio
// Pool.LiquidationThreshold
```

### What Should Exist

```protobuf
message Pool {
  // ... existing fields ...
  
  // Interest rates (per-pool) ✅ CORRECT
  string interest_rate_coin1 = 15;
  string interest_rate_coin2 = 16;
  
  // Borrow caps (per-pool) ✅ CORRECT
  string max_borrow_percent_coin1 = 17;
  string max_borrow_percent_coin2 = 18;
  
  // ✅ MUST ADD: Leverage risk params (per-pool)
  string min_collateral_ratio = 21;        // e.g., "1.5"
  string max_leverage_ratio = 22;           // e.g., "5.0"
  string liquidation_threshold = 23;        // e.g., "1.2"
  
  // ... rest of fields ...
}

message LeverageParams {
  // Module-level: Only global/protocol settings
  uint64 block_delay_before_close = 1;           // ✅ Keep (protocol-wide)
  uint64 block_delay_before_liquidation = 2;    // ✅ Add (protocol-wide)
  // OPTIONAL:
  // string max_interest_rate_borrowed = 3;     // Global cap on rates
}
```

---

## 🔧 Required Fixes

### 1. Update `whaleswap.proto` Pool

Add to the Pool message:
```protobuf
message Pool {
  // ... existing 20 fields ...
  
  // ═════ NEW: Per-Pool Leverage Parameters ═════
  string min_collateral_ratio = 21 [
    (cosmos_proto.scalar) = "cosmos.Dec",
    (gogoproto.customtype) = "cosmossdk.io/math.LegacyDec",
    (gogoproto.nullable) = false
  ];
  
  string max_leverage_ratio = 22 [
    (cosmos_proto.scalar) = "cosmos.Dec",
    (gogoproto.customtype) = "cosmossdk.io/math.LegacyDec",
    (gogoproto.nullable) = false
  ];
  
  string liquidation_threshold = 23 [
    (cosmos_proto.scalar) = "cosmos.Dec",
    (gogoproto.customtype) = "cosmossdk.io/math.LegacyDec",
    (gogoproto.nullable) = false
  ];
}
```

### 2. Update `leverage.proto` LeverageParams

Keep only protocol-wide settings:
```protobuf
message LeverageParams {
  uint64 block_delay_before_close = 1;
  uint64 block_delay_before_liquidation = 2;  // ADD THIS
  // OPTIONAL:
  // string max_interest_rate_borrowed = 3;
}
```

### 3. Update Keeper Logic

Replace all references to `LeverageParams.MinCollateralRatio` with `Pool.MinCollateralRatio`:

**CURRENT (WRONG):**
```go
params, _ := k.leverageParams.Get(ctx)
minCR := params.MinCollateralRatio  // ❌ Same for all pools
```

**CORRECT:**
```go
pool, _ := k.PoolsMap.Get(ctx, msg.PoolId)
minCR := pool.MinCollateralRatio  // ✅ Pool-specific
```

### 4. Update Pool Creation

When creating a pool, set default leverage params:
```go
pool := Pool{
  // ... existing fields ...
  MinCollateralRatio:   math.LegacyMustNewDecFromStr("1.5"),
  MaxLeverageRatio:     math.LegacyMustNewDecFromStr("5.0"),
  LiquidationThreshold: math.LegacyMustNewDecFromStr("1.2"),
}
```

---

## Impact on Code

| File | Changes Needed |
|------|-----------------|
| `proto/dysonprotocol/whaleswap/v1/whaleswap.proto` | Add 3 fields to Pool message |
| `proto/dysonprotocol/whaleswap/v1/leverage.proto` | Remove 3 fields from LeverageParams, add 1 |
| `x/whaleswap/keeper/msg_leverage_open.go` | Change `params.MinCollateralRatio` → `pool.MinCollateralRatio` etc. |
| `x/whaleswap/keeper/msg_leverage_handlers.go` | Same changes for liquidation logic |
| `x/whaleswap/keeper/query_leverage_health.go` | Same changes for health queries |
| `x/whaleswap/types/params.go` | Remove validation for min_collateral_ratio, max_leverage_ratio, liquidation_threshold |

---

## Summary

✅ **Spec is correct**: Each pool should control its own leverage risk parameters
❌ **Implementation is wrong**: These are currently global/module-level
🔧 **Fix**: Move these 3 parameters from LeverageParams to Pool message

The implementation should match the spec's pool-level categorization.

