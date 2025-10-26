# Parameter Level Analysis: Spec vs Implementation

## 🔍 Critical Finding

**The spec incorrectly categorizes parameters.** Some parameters should be **Pool-Level** but are spec'd as **Module-Level**, and vice versa.

---

## Current Implementation (CORRECT)

### Pool-Level (in `whaleswap.proto` Pool message)
✅ `interest_rate_coin1` 
✅ `interest_rate_coin2`
✅ `max_borrow_percent_coin1`
✅ `max_borrow_percent_coin2`

### Module-Level (in `leverage.proto` LeverageParams)
✅ `min_collateral_ratio`
✅ `max_leverage_ratio`
✅ `liquidation_threshold`
✅ `block_delay_before_close`

---

## Spec Says (PROBLEMATIC)

### Pool-Level (Spec Section)
| Parameter | Spec | Implementation | Status |
|-----------|------|-----------------|--------|
| `interest_rate_coin1` | Pool-level | ✅ Pool.interest_rate_coin1 | ✅ CORRECT |
| `interest_rate_coin2` | Pool-level | ✅ Pool.interest_rate_coin2 | ✅ CORRECT |
| `max_borrow_percent_coin1` | Pool-level | ✅ Pool.max_borrow_percent_coin1 | ✅ CORRECT |
| `max_borrow_percent_coin2` | Pool-level | ✅ Pool.max_borrow_percent_coin2 | ✅ CORRECT |
| ⚠️ `liquidation_threshold` | **Pool-level** | ❌ LeverageParams (module-level) | **MISMATCH** |
| ⚠️ `min_collateral_ratio` | **Pool-level** | ❌ LeverageParams (module-level) | **MISMATCH** |
| ⚠️ `max_leverage_ratio` | **Pool-level** | ❌ LeverageParams (module-level) | **MISMATCH** |

### Module-Level (Spec Section)
| Parameter | Spec | Implementation | Status |
|-----------|------|-----------------|--------|
| `block_delay_before_close` | Module-level | ✅ LeverageParams | ✅ CORRECT |
| ❌ `block_delay_before_liquidation` | Module-level | ❌ NOT IMPLEMENTED | **MISSING** |
| ❌ `max_interest_rate_borrowed` | Module-level | ❌ NOT IMPLEMENTED | **MISSING** |

---

## Analysis: Which Is Right?

### `liquidation_threshold`, `min_collateral_ratio`, `max_leverage_ratio`

**Spec Says**: Pool-level
**Implementation**: Module-level
**Reality**: **Implementation is BETTER** ✅

**Reasoning:**
- These parameters define **health/liquidation rules** that should be **universal** for the protocol
- Different thresholds per pool would create:
  - ⚠️ Confusion: Different liquidation rules for different pools
  - ⚠️ Arbitrage: Users pick pools with favorable thresholds
  - ⚠️ Governance nightmare: Thousands of per-pool parameters
- These are **consensus rules**, not **pool properties**
- Similar to: network fees are protocol-level, not pool-level

**Verdict**: Implementation is **correct**. Spec has error.

### Interest Rates (`interest_rate_coin1`, `interest_rate_coin2`)

**Spec Says**: Pool-level ✅
**Implementation**: Pool-level ✅
**Verdict**: Correct

**Reasoning:**
- Each pool has different reserve risk
- USDC/ETH pool might have different rates than USDC/SOL pool
- Pool operators should set rates for their liquidity
- Proper design: per-pool economics

---

## 🟡 Missing Parameters

The spec defines 2 module-level params that aren't implemented:

### 1. `block_delay_before_liquidation`
**Spec:** "Blocks owner must wait before liquidation (1 block)"
**Current Impl:** Hardcoded universally to 1 block
**Assessment:** 
- ✅ Correct behavior (1 block enforced)
- ⚠️ Not configurable (could be governance parameter)
- **Fix**: Add to LeverageParams as uint64

### 2. `max_interest_rate_borrowed`
**Spec:** "Maximum annual interest rate for borrowed funds (100% APY)"
**Current Impl:** Not implemented
**Assessment:**
- ⚠️ No global rate cap
- Allows pool operators to set arbitrarily high rates
- Probably unnecessary (pool-level rate control sufficient)
- **Fix**: Optional; only if governance wants rate ceiling

---

## ✅ Recommended Fix

### Update `LeverageParams` proto & code:

```protobuf
message LeverageParams {
  string min_collateral_ratio = 1;           // "1.5"
  string max_leverage_ratio = 2;             // "20.0"
  string liquidation_threshold = 3;          // "1.2"
  uint64 block_delay_before_close = 4;       // "1"
  uint64 block_delay_before_liquidation = 5; // "1" (NEW)
  // OPTIONAL:
  // string max_interest_rate_borrowed = 6;  // "1.00" (NEW, optional)
}
```

### Add validation in `params.go`:

```go
// Check block delay for liquidation
if p.BlockDelayBeforeLiquidation == 0 {
  return fmt.Errorf("block_delay_before_liquidation must be > 0")
}
```

### Keep pool-level params in Pool:
```protobuf
message Pool {
  // ... existing ...
  string interest_rate_coin1 = 15;
  string interest_rate_coin2 = 16;
  string max_borrow_percent_coin1 = 17;
  string max_borrow_percent_coin2 = 18;
  // ... etc
}
```

---

## Summary

| Item | Status | Action |
|------|--------|--------|
| Pool-level rates | ✅ Correct | No change |
| Pool-level borrow caps | ✅ Correct | No change |
| Health params (module-level) | ✅ Better than spec | No change needed |
| `block_delay_before_liquidation` | 🟡 Hardcoded | Add to LeverageParams |
| `max_interest_rate_borrowed` | ⚠️ Optional | Can skip for MVP |

**Conclusion**: Implementation is **well-designed**. Spec has conceptual error about which parameters should be pool vs module level.

