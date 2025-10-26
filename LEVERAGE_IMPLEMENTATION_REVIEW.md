# Leverage Implementation vs Specification Review

## Overview
Comparing the implemented code in `x/whaleswap/keeper/` against the detailed specification in `leverage_spec.md`.

---

## ✅ ALIGNED - What Matches Spec

### 1. **Proto Messages & Types**
| Aspect | Spec | Implementation | Status |
|--------|------|-----------------|--------|
| PositionType enum | LONG, SHORT | ✅ `PositionType_POSITION_TYPE_{LONG,SHORT}` | ✅ |
| LiquidationStatus enum | NONE, INITIALIZED | ✅ Same enum values | ✅ |
| Pool fields | interest_rate_coin{1,2}, max_borrow_percent_coin{1,2}, interest_earned, total_borrowed | ✅ All added | ✅ |
| Transaction signers | `option (cosmos.msg.v1.signer)` | ✅ Properly annotated | ✅ |
| Coin consolidation | denom + amount → single Coin | ✅ `borrowed`, `held`, `collateral` as Coins | ✅ |

### 2. **Interest Calculation** (`leverage_interest.go`)
```go
// SPEC: interest = borrowed_amount × rate × (elapsed_seconds / seconds_per_year)
// IMPL: ✅ Exactly matches in CalculateInterest()
```
- ✅ Simple interest (no compounding)
- ✅ Rate per denom from pool config
- ✅ On-demand calculation (no accrual schedule)
- ✅ Time-based: `(time_elapsed_seconds / 365.25 * 24 * 60 * 60)`

### 3. **Health Status & Collateral Ratio** (`leverage_liquidation.go`)
```go
// SPEC thresholds:
// - HEALTHY: CR > 150%
// - AT_RISK: 120% ≤ CR ≤ 150%
// - LIQUIDATABLE: CR < 120%

// IMPL: ✅ ComputeHealthStatus() exactly matches thresholds
```

### 4. **Block Delay Enforcement** (`leverage_liquidation.go`)
```go
// SPEC: 1-block delay before owner can close
// IMPL: ✅ CanCloseBefore() checks: current_block > created_block_height
```

### 5. **Two-Step Liquidation** (`leverage_liquidation.go`)
**SPEC:**
1. Initialize: Record block height, set status to INITIALIZED
2. Finalize: Verify 1+ block passed, then settle

**IMPL:**
- ✅ `InitializeLiquidationInternal()`: Sets `liquidation_status` and `liquidation_initialized_block_height`
- ✅ `CanFinalizeLiquidationBefore()`: Checks `current_block > liquidation_initialized_block_height`

### 6. **Add Collateral Reset** (`leverage_collateral.go`)
```go
// SPEC: AddCollateral clears liquidation_status = NONE
// IMPL: ✅ ClearLiquidationPending() does exactly this
```

### 7. **Borrow Cap Enforcement** (`msg_leverage_open.go`)
```go
// SPEC: total_borrowed[denom] + borrow_amt ≤ reserves[denom] × max_borrow_percent[denom]
// IMPL: ✅ validateBorrowCap() implements exact formula
```

### 8. **Position Lifecycle** (`msg_leverage_open.go`)
- ✅ Open: Allocate position ID, record `created_block_height`, set `liquidation_status = NONE`
- ✅ Validate: Min CR threshold at open
- ✅ Store: Position with all required fields

### 9. **Query Methods** (`query_leverage_health.go`)
- ✅ `Position()`: Returns full position data
- ✅ `PositionHealth()`: Returns CR, health status, can_close, can_liquidate flags
- ✅ `PositionInterest()`: Returns accrued interest breakdown

---

## ⚠️ DIFFERENCES - Implementation vs Spec

### 1. **Proto Field Type Changes** (INTENTIONAL - IDIOMATIC)
| Field | Spec | Implementation | Reason |
|-------|------|-----------------|--------|
| `borrowed_denom` + `borrowed_amount` | Separate strings | `borrowed: Coin` | Cosmos SDK idiom |
| `held_denom` + `held_amount` | Separate strings | `held: Coin` | Cosmos SDK idiom |
| `collateral_denom` + `collateral_amount` | Separate strings | `collateral: Coin` | Cosmos SDK idiom |
| Params as strings | `"1.5"`, `"0.05"` | `LegacyDec` (native types) | Generated from proto customtype |

**Impact**: ✅ **Better** - No runtime string parsing; type-safe decimal math.

### 2. **Module-Level Parameters Missing from Implementation**

**SPEC includes:**
```
- block_delay_before_close: uint64
- block_delay_before_liquidation: uint64
- max_interest_rate_borrowed: LegacyDec
```

**IMPL includes only:**
```go
LeverageParams{
  MinCollateralRatio:    LegacyDec    ✅
  MaxLeverageRatio:      LegacyDec    ✅
  LiquidationThreshold:  LegacyDec    ✅
  BlockDelayBeforeClose: uint64       ✅  (only this one!)
}
```

**NOT IMPLEMENTED:**
- ❌ `block_delay_before_liquidation` (separate from close delay)
- ❌ `max_interest_rate_borrowed` (global cap on rates)

**Severity**: 🟡 **Low** - These are optional enhancements
- Both delays currently hardcoded to 1 block universally
- No global rate cap needed if pool-level rates are reasonable

### 3. **Query Messages Missing**

**SPEC defines:** `QueryPositionRequest` + `QueryPositionResponse`

**IMPL has:**
- ✅ `Position()` (via `QueryPositionRequest`)
- ✅ `PositionHealth()`
- ✅ `PositionInterest()`
- ❌ NO explicit `QueryPositionRequest` proto message

**Impact**: Minor - The query exists; proto just wasn't explicitly named.

### 4. **Event Types Not Implemented**

**SPEC defines 5 event types:**
- `EventLeveragePositionOpened`
- `EventLeveragePositionClosed`
- `EventLeverageCollateralAdded`
- `EventLeverageLiquidationInitialized`
- `EventLeverageLiquidationFinalized`

**IMPL**: ❌ No event emission in any handler

**Severity**: 🟡 **Medium** - Needed for indexing/monitoring
- Should add `k.EmitEvent()` calls in message handlers
- Easy to add retroactively

### 5. **Pool Loss Type in Response**

**SPEC:**
```protobuf
MsgFinalizeLiquidationResponse {
  string collateral_received = 1;
  string collateral_denom = 2;
  string repayment_amount = 3;
  string accrued_interest = 4;
  string pool_loss = 5;           // Decimal!
}
```

**IMPL:**
```protobuf
MsgFinalizeLiquidationResponse {
  cosmos.base.v1beta1.Coin collateral_received = 1;
  cosmos.base.v1beta1.Coin repayment_amount = 2;
  string accrued_interest = 3;    // Dec
  string pool_loss = 4;           // Dec
}
```

**Status**: ✅ Better - Now properly typed as Coin

### 6. **Response Field Naming Mismatches**

**Spec → Implementation**

| Message | Spec Field | Impl Field | Status |
|---------|------------|-----------|--------|
| `MsgOpenLongPositionResponse` | `held_denom`, `held_amount` | `held: Coin` | ✅ Better |
| `MsgClosePositionResponse` | `profit_denom`, `profit_amount` | `profit: Coin` | ✅ Better |
| `MsgAddCollateralResponse` | `new_collateral_amount`, `new_collateral_ratio` | `new_collateral: Coin`, `new_collateral_ratio: Dec` | ✅ Better |

### 7. **Liquidation Settlement Logic**

**SPEC (Section 4. LIQUIDATION STEP 2: FINALIZE):**
```
- Liquidator sends: full owed amount (principal + interest)
- Liquidator receives: ALL collateral
- If owed > collateral: Pool absorbs loss
```

**IMPL (`msg_leverage_handlers.go` FinalizeLiquidation):**
```go
// Liquidator doesn't explicitly send repayment
// Response only shows what's returned to user
// Pool loss calculated but not tracked separately
```

**Severity**: 🔴 **HIGH ISSUE** - Settlement mechanics simplified
- Current impl: Returns remaining collateral to user; loss goes to pool implicitly
- Spec requires: Liquidator actively repays debt, receives all collateral
- **Fix needed**: Require MsgFinalizeLiquidation to include payment from liquidator

### 8. **Swap Execution During Open**

**SPEC (Step 1. OPEN):**
```
- Module swaps borrowed → desired denom (long/short)
```

**IMPL (`msg_leverage_open.go`):**
```go
// Simplified: held_amount ≈ borrowed_amount × pool_price
// No actual swap executed
heldAmt := math.LegacyNewDecFromInt(borrowAmt).Mul(price).TruncateInt()
```

**Severity**: 🟡 **Medium** - Mock implementation
- For MVP this is acceptable (spec says "simplified")
- Production needs: Execute actual AMM swap to get real output

### 9. **Close Position Settlement**

**SPEC (2A. OWNER CLOSE):**
```
- Swap held → borrowed denom
- Repay principal + interest
- Send profit (excess) to owner
```

**IMPL (`msg_leverage_handlers.go` ClosePosition):**
```go
// Simplified: No swap executed
// profit = held amount directly (not swapped back)
// repayment = borrowed + interest
// actual exchange/slippage not modeled
```

**Severity**: 🟡 **Medium** - Mock implementation
- Same note as above: acceptable for MVP, needs real swaps later

### 10. **Missing Max Leverage Enforcement**

**SPEC includes:** `max_leverage_ratio` parameter (e.g., "5.0")

**IMPL**: 
- ✅ Parameter stored in `LeverageParams`
- ❌ Never validated/enforced

**Calculation:**
```
leverage = (collateral + borrowed) / collateral
```

**Severity**: 🔴 **HIGH** - Parameter exists but unused
- Should validate at open: `leverage ≤ max_leverage_ratio`

---

## 🚩 CRITICAL ISSUES

### 1. **Liquidation Settlement Flow Incomplete**
- Spec requires liquidator to send payment
- Current impl returns collateral but doesn't model payment
- **Action**: Add `repayment` parameter to MsgFinalizeLiquidation

### 2. **Max Leverage Not Enforced**
- Parameter exists but never checked
- **Action**: Add check in `OpenLongPosition` / `OpenShortPosition`
  ```go
  leverage := (collateral + borrowed) / collateral
  if leverage > maxLeverage { return error }
  ```

### 3. **Events Not Emitted**
- No indexing/monitoring capability
- **Action**: Add emit calls in all 6 message handlers

### 4. **Swap Execution Stubbed**
- Positions don't actually acquire held assets
- Mock implementation only
- **Action**: Integrate with AMM swap logic (future)

---

## 🟢 WHAT'S CORRECT & WELL-DONE

1. ✅ **Proto Schema** - Idiomatic Cosmos SDK types (better than spec)
2. ✅ **Interest Math** - Exact formula implementation
3. ✅ **Health Checks** - All thresholds correct
4. ✅ **Block Delays** - Properly enforced
5. ✅ **Borrow Caps** - Correctly calculated
6. ✅ **Two-Step Liquidation** - State machine correct
7. ✅ **Collateral Reset** - AddCollateral clears pending
8. ✅ **Query System** - All three queries implemented correctly
9. ✅ **Type Safety** - LegacyDec/Int types used throughout
10. ✅ **Collections** - Proper indexing (by user, by pool)

---

## Summary Table

| Category | Status | Issues | Priority |
|----------|--------|--------|----------|
| **Proto Definitions** | ✅ | None | — |
| **Interest Calculation** | ✅ | None | — |
| **Health & CR** | ✅ | None | — |
| **Block Delays** | ✅ | None | — |
| **Two-Step Liquidation** | ⚠️ | Settlement flow needs payment model | 🔴 HIGH |
| **Borrow Caps** | ✅ | None | — |
| **Max Leverage** | ⚠️ | Parameter unused | 🔴 HIGH |
| **Swap Execution** | ⚠️ | Stubbed (mock only) | 🟡 MEDIUM |
| **Events** | ❌ | Not implemented | 🟡 MEDIUM |
| **Module Params** | ⚠️ | Incomplete (missing 2 params) | 🟡 LOW |
| **Query System** | ✅ | None | — |

---

## Recommendations

### Must Fix (High Priority)
1. **Fix Settlement Flow**: Add payment validation to `FinalizeLiquidation`
2. **Enforce Max Leverage**: Add check in both `OpenLongPosition` and `OpenShortPosition`

### Should Add (Medium Priority)
1. **Event Emission**: Add in all 6 message handlers
2. **Real Swap Execution**: Hook into AMM pool swap logic

### Nice to Have (Low Priority)
1. **Module-Level Delay Params**: Make liquidation delay separate from close delay
2. **Global Rate Cap**: Add `max_interest_rate_borrowed` enforcement
3. **QueryPosition Proto**: Explicitly define in proto file

