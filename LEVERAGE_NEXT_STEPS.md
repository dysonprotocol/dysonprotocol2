# Leverage Feature Implementation - Next Steps Outline

## 📊 Current Status Overview

### ✅ Completed (80% of Core)
1. **Proto Definitions** - All leverage types, messages, queries defined
   - `leverage.proto` - Full schema with enums, positions, params, 6 tx messages, 3 queries
   - `whaleswap.proto` - Pool-level leverage fields (interest rates, borrow caps)
   - `tx.proto` - Message handlers registered
   - `query.proto` - Query handlers registered

2. **Keeper Logic - Foundation Layer** (7 files created)
   - `leverage_interest.go` ✅ - Interest calculation (on-demand, simple interest formula)
   - `leverage_liquidation.go` ✅ - Health status, CR computation, block delays, liquidation state machine
   - `leverage_collateral.go` ✅ - AddCollateral with liquidation reset
   - `keeper.go` ✅ - Collections, sequences, indexing setup
   - `msg_leverage_open.go` ✅ - OpenLongPosition, OpenShortPosition with borrow cap validation
   - `query_leverage_health.go` ✅ - Position, PositionHealth, PositionInterest queries
   - `msg_leverage_handlers.go` - Partial handlers (stubs)

3. **Parameter System** ✅
   - Pool-level: interest rates, borrow caps (from POOL_LEVEL_PARAMS_FIX)
   - Module-level: block delays, health thresholds

---

## 🔴 HIGH PRIORITY - Must Fix Before Proto Generation

### Issue 1: Max Leverage Not Enforced
**Location:** `msg_leverage_open.go` (both OpenLongPosition & OpenShortPosition)

**Problem:** 
- Parameter `max_leverage_ratio` exists in `LeverageParams` but is never validated
- Users can open positions with unlimited leverage

**Solution:**
```go
// In both OpenLongPosition() and OpenShortPosition():
params, _ := k.leverageParams.Get(ctx)
if params != nil && params.MaxLeverageRatio != "" {
    maxLeverage, _ := math.LegacyNewDecFromStr(params.MaxLeverageRatio)
    leverage := collateral.Quo(collateral)  // (collateral + borrowed) / collateral
    if leverage.GT(maxLeverage) {
        return nil, fmt.Errorf("leverage %s exceeds max %s", leverage.String(), maxLeverage.String())
    }
}
```

**Impact:** Blocks unlimited leverage abuse

---

### Issue 2: Liquidation Settlement Flow Incomplete
**Location:** `msg_leverage_handlers.go` (FinalizeLiquidation stub)

**Problem:**
- Spec requires: Liquidator sends repayment → receives all collateral
- Current: Just returns collateral without payment validation
- Pool loss not tracked

**Current Code (Stub):**
```go
func (k Keeper) FinalizeLiquidation(ctx context.Context, msg *types.MsgFinalizeLiquidation) {
    // TODO: Not implemented
    return nil, status.Errorf(codes.Unimplemented, "not implemented")
}
```

**Solution Approach:**
1. Validate position exists & is liquidatable
2. Calculate: `repayment_needed = principal + accrued_interest`
3. Transfer repayment from liquidator → module
4. Send collateral to liquidator
5. If collateral < repayment: Pool absorbs loss
6. Delete position

**Files to Update:**
- `msg_leverage_handlers.go` - Implement FinalizeLiquidation
- `leverage_liquidation.go` - Add settler helper function

---

### Issue 3: Missing Maximum Leverage in Pool Open
**Location:** Both open functions in `msg_leverage_open.go`

**Add Leverage Calculation:**
```go
leverage := (collateral + borrowed) / collateral

// This is already being used for CR calculation, just enforce it
if leverage > maxLeverageRatio {
    return error
}
```

---

## 🟡 MEDIUM PRIORITY - Complete Before Tests

### Issue 4: Events Not Emitted
**Locations:** All 6 message handlers need event emission

**Missing Events:**
- `EventLeveragePositionOpened` - when opening long/short
- `EventLeveragePositionClosed` - when closing position
- `EventLeverageCollateralAdded` - when adding collateral
- `EventLeverageLiquidationInitialized` - when initializing liquidation
- `EventLeverageLiquidationFinalized` - when finalizing liquidation

**Implementation Pattern:**
```go
if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionOpened{
    PositionId:   posID,
    User:         msg.Trader,
    PoolId:       msg.PoolId,
    PositionType: "LONG",
    // ... all fields populated ...
}); err != nil {
    return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
}
```

**Files to Create/Update:**
- `x/whaleswap/types/events.go` - Event type helpers (or add to types file)
- All 6 handler functions - Add emit calls

---

### Issue 5: Swap Execution Stubbed
**Location:** `msg_leverage_open.go` lines 157, 227

**Current (Simplified):**
```go
// Compute held amount from swap (simplified: held = borrowed * price)
heldAmt := math.LegacyNewDecFromInt(borrowAmt).Mul(price).TruncateInt()
```

**Production Version Needed:**
- Execute actual AMM swap via `PoolSwap` logic
- Get real slippage, fees, output
- Store actual held amount (not mock)

**For MVP:** This is acceptable; mark as TODO for future

---

## 🟢 MEDIUM PRIORITY - Code Quality & Completeness

### Issue 6: Message Handlers Incomplete
**File:** `msg_leverage_handlers.go`

**Status:** Only some handlers implemented
**Need to Implement:**
- ✅ OpenLongPosition - Done (in `msg_leverage_open.go`)
- ✅ OpenShortPosition - Done (in `msg_leverage_open.go`)
- ❌ ClosePosition - Stub
- ❌ AddCollateral - Call existing function
- ❌ InitializeLiquidation - Stub
- ❌ FinalizeLiquidation - Stub

**Each handler should:**
1. Validate inputs
2. Call keeper method
3. Emit event
4. Return response

---

## 🟢 LOW PRIORITY - Nice to Have

### Issue 7: Missing Module Params
**In `LeverageParams`:**
- ❌ `block_delay_before_liquidation` - Currently hardcoded to 1 block
- ❌ `max_interest_rate_borrowed` - Global cap on rates

**For MVP:** Skip these; keep hardcoded

---

## 📋 Implementation Roadmap

### Phase 1: Pre-Proto Generation (FIX CRITICAL ISSUES)
```
⏱️ Estimated: 30-45 minutes

1. Add max_leverage validation to msg_leverage_open.go
   - Check: leverage ≤ maxLeverageRatio
   - Apply to both OpenLongPosition & OpenShortPosition
   
2. Implement FinalizeLiquidation settlement
   - Validate position liquidatable
   - Calculate repayment (principal + interest)
   - Transfer settlement amounts
   - Handle pool loss
   - Delete position
   
3. Add event emission
   - Create event emission helper
   - Add to all 6 handlers
```

---

### Phase 2: Proto Generation
```
⏱️ Estimated: 2-3 minutes

make proto-gen install

This generates:
- types/leverage.pb.go (NEW)
- types/whaleswap.pb.go (UPDATED - Pool fields)
- types/tx.pb.go (UPDATED - Message handlers)
- types/query.pb.go (UPDATED - Query handlers)
```

---

### Phase 3: Message Server Routing
```
⏱️ Estimated: 15 minutes

File: keeper/msg_server.go

Add 6 handler stubs that delegate to keeper:

```go
func (k msgServer) OpenLongPosition(ctx context.Context, msg *types.MsgOpenLongPosition) (*types.MsgOpenLongPositionResponse, error) {
    return k.Keeper.OpenLongPosition(ctx, msg)
}

func (k msgServer) OpenShortPosition(ctx context.Context, msg *types.MsgOpenShortPosition) (*types.MsgOpenShortPositionResponse, error) {
    return k.Keeper.OpenShortPosition(ctx, msg)
}

// ... 4 more handlers similarly
```
```

---

### Phase 4: Query Server Routing
```
⏱️ Estimated: 10 minutes

File: keeper/query_server.go

Add 3 query handlers:

```go
func (k Keeper) Position(ctx context.Context, req *types.QueryPositionRequest) (*types.QueryPositionResponse, error) {
    // Delegate to keeper
}

func (k Keeper) PositionHealth(ctx context.Context, req *types.QueryPositionHealthRequest) (*types.QueryPositionHealthResponse, error) {
    // Delegate to keeper
}

func (k Keeper) PositionInterest(ctx context.Context, req *types.QueryPositionInterestRequest) (*types.QueryPositionInterestResponse, error) {
    // Delegate to keeper
}
```
```

---

### Phase 5: Complete Remaining Handlers
```
⏱️ Estimated: 1-2 hours

Implement in msg_leverage_handlers.go:
1. ClosePosition (complex: swap back, repay, settle)
2. AddCollateral (simple: delegate to existing function)
3. InitializeLiquidation (simple: set state, check CR)
4. FinalizeLiquidation (complex: settle with liquidator)

Each needs:
- Full business logic
- Error handling
- Event emission
- State persistence
```

---

### Phase 6: Error Types & Types File Updates
```
⏱️ Estimated: 15 minutes

Files to Update:
1. types/errors.go - Add leverage-specific errors
   - ErrBorrowCapExceeded
   - ErrInsufficientCollateral
   - ErrPositionNotLiquidatable
   - ErrBlockDelayNotPassed
   - ErrInvalidLeverage
   - ErrInvalidPosition

2. types/params.go - Add LeverageParams validation
   - Already mostly done, verify complete
```

---

### Phase 7: Testing
```
⏱️ Estimated: 2-4 hours

Create tests in tests/whaleswap/leverage/:

1. test_leverage_open_long.py - Happy path
2. test_leverage_open_short.py - Happy path
3. test_leverage_borrow_cap.py - Reject over-cap
4. test_leverage_max_leverage.py - Reject over-leverage ✨ NEW
5. test_leverage_health_query.py - Query checks
6. test_leverage_liquidation.py - 2-step flow
7. test_leverage_add_collateral.py - Collateral + reset
8. test_leverage_close_position.py - Closing

Run with: make test PYTEST_ARGS="tests/whaleswap/leverage/ -v"
```

---

## 📊 File Status Checklist

### Proto Files
- [x] `proto/dysonprotocol/whaleswap/v1/leverage.proto` - Complete
- [x] `proto/dysonprotocol/whaleswap/v1/whaleswap.proto` - Complete (pool-level params)
- [x] `proto/dysonprotocol/whaleswap/v1/tx.proto` - Complete (handlers registered)
- [x] `proto/dysonprotocol/whaleswap/v1/query.proto` - Complete (queries registered)
- [ ] Run `make proto-gen install`

### Keeper Implementation
- [x] `keeper/leverage_interest.go` - Complete
- [x] `keeper/leverage_liquidation.go` - Complete (+ add settler)
- [x] `keeper/leverage_collateral.go` - Complete
- [x] `keeper/msg_leverage_open.go` - 90% (ADD: max_leverage validation)
- [ ] `keeper/msg_leverage_handlers.go` - 10% (Need 4 implementations + fix)
- [x] `keeper/query_leverage_health.go` - Complete
- [x] `keeper/keeper.go` - Complete (collections setup)
- [ ] `keeper/msg_server.go` - Add 6 handlers
- [ ] `keeper/query_server.go` - Add 3 handlers

### Type Definitions
- [ ] `types/errors.go` - Add leverage errors
- [ ] `types/params.go` - Validate LeverageParams

### Testing
- [ ] Create test suite in `tests/whaleswap/leverage/`

---

## 🎯 Critical Path (Minimum to Deploy)

**Fastest route to working leverage system:**

1. **Fix max_leverage validation** (5 min)
2. **Implement FinalizeLiquidation** (20 min)
3. **Run proto-gen** (2 min)
4. **Add msg_server handlers** (10 min)
5. **Add query_server handlers** (8 min)
6. **Implement ClosePosition** (30 min)
7. **Add event emission** (15 min)
8. **Run basic tests** (30 min)

**Total: ~2 hours to working system**

---

## Summary

| Category | Done | Todo | Priority |
|----------|------|------|----------|
| **Proto** | 100% | Run make | 🔴 BLOCKER |
| **Core Math** | 100% | — | ✅ |
| **Health Checks** | 100% | — | ✅ |
| **Interest** | 100% | — | ✅ |
| **Block Delays** | 100% | — | ✅ |
| **Max Leverage** | 0% | Add validation | 🔴 HIGH |
| **Liquidation** | 50% | Implement finalize | 🔴 HIGH |
| **Close Position** | 0% | Full impl | 🟡 MEDIUM |
| **Events** | 0% | Emit in handlers | 🟡 MEDIUM |
| **Handlers** | 20% | Complete 4 more | 🟡 MEDIUM |
| **Query Server** | 0% | Add routing | 🟡 MEDIUM |
| **Tests** | 0% | Create suite | 🟡 MEDIUM |

**Next immediate action:** Fix the two HIGH priority issues, then run proto-gen.
