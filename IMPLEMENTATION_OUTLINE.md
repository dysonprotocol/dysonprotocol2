# Leverage Feature Implementation - Comprehensive Outline

## 📋 Current Status: PHASE 1 COMPLETE ✅

**Proto Generation:** ✅ Complete  
**Core Keeper Logic:** ✅ Complete  
**Event System:** ✅ Complete  
**Max Leverage Validation:** ✅ Complete  
**Settlement Flow:** ✅ Complete  

---

## 🏗️ Architecture Overview

### Collections (Storage)

| Collection | Type | Purpose | Prefix |
|------------|------|---------|--------|
| `leveragePositionSeq` | Sequence | Allocate position IDs | 19 |
| `LeveragePositions` | Map[uint64]LeveragePosition | Position records | 20 |
| `leverageParams` | Item[LeverageParams] | Module parameters | 21 |
| `PositionsByUser` | Map[Pair[addr, id]]uint64 | Reverse index: user→positions | 22 |
| `PositionsByPool` | Map[Pair[poolId, id]]uint64 | Reverse index: pool→positions | 23 |

**Location:** `x/whaleswap/keeper/keeper.go` (lines 46-51, 91-95)

---

## 📁 File Structure

### Proto Definitions
```
proto/dysonprotocol/whaleswap/v1/
├── leverage.proto (252 lines)
│   ├── Enums: PositionType, LiquidationStatus
│   ├── Messages: LeveragePosition, LeverageParams
│   ├── Tx Messages: 6 message types + responses
│   ├── Query Messages: 3 query types + responses
│   └── Events: 5 event types
├── whaleswap.proto (187 lines - updated)
│   └── Pool: Added leverage fields (min_collateral_ratio, max_leverage_ratio, liquidation_threshold)
├── tx.proto (updated)
│   └── Msg service: 6 leverage handlers registered
└── query.proto (updated)
    └── Query service: 3 leverage query handlers registered
```

### Core Keeper Implementation
```
x/whaleswap/keeper/
├── keeper.go (200+ lines)
│   ├── Collections definition (leveragePositionSeq, LeveragePositions, etc.)
│   ├── Helper methods (GetLeverageParams, SetLeverageParams)
│   └── Address helpers (addr, sendToModule, sendFromModule)
│
├── msg_leverage_open.go (327 lines) ✅ COMPLETE
│   ├── OpenLongPosition(ctx, msg) → Creates long position
│   │   ├─ Validates borrow cap
│   │   ├─ Validates min collateral ratio
│   │   ├─ Validates max leverage ← FIX 1
│   │   ├─ Allocates position ID
│   │   ├─ Transfers collateral to module
│   │   ├─ Updates pool total_borrowed
│   │   ├─ Computes held amount (simplified swap)
│   │   ├─ Creates position record
│   │   ├─ Indexes by user and pool
│   │   └─ Emits EventLeveragePositionOpened ← FIX 2
│   │
│   ├── OpenShortPosition(ctx, msg) → Creates short position
│   │   └─ Same logic as above, reversed (borrow coin1, sell for coin0)
│   │
│   ├── validateBorrowCap(ctx, pool, denom, amount)
│   │   ├─ Gets pool-specific max borrow percent
│   │   ├─ Calculates max borrow amount
│   │   └─ Validates total borrowed ≤ cap
│   │
│   └─ Fixed: Event emission with correct Int/LegacyDec types
│
├── msg_leverage_handlers.go (239 lines) ✅ COMPLETE
│   ├── ClosePosition(ctx, msg) → Closes position & settles
│   │   ├─ Validates ownership & block delay
│   │   ├─ Calculates accrued interest
│   │   ├─ Returns collateral & profit to user
│   │   ├─ Updates pool (decrease borrowed, add interest earned)
│   │   ├─ Deletes position
│   │   └─ Emits EventLeveragePositionClosed ← FIX 2
│   │
│   ├── InitializeLiquidation(ctx, msg) → Marks position for liquidation
│   │   ├─ Validates position exists
│   │   ├─ Calculates current collateral ratio
│   │   ├─ Sets liquidation status = INITIALIZED
│   │   ├─ Records block height
│   │   └─ Emits EventLeverageLiquidationInitialized ← FIX 2
│   │
│   └── FinalizeLiquidation(ctx, msg) → Settles liquidation ← FIX 3
│       ├─ Validates liquidation initialized & delay passed
│       ├─ Calculates final repayment (principal + interest)
│       ├─ Collects repayment from liquidator ← KEY CHANGE
│       ├─ Sends all collateral to liquidator ← KEY CHANGE
│       ├─ Calculates pool loss (if repayment > collateral)
│       ├─ Updates pool (decrease borrowed, add interest)
│       ├─ Deletes position
│       └─ Emits EventLeverageLiquidationFinalized ← FIX 2
│
├── leverage_interest.go (35 lines) ✅ COMPLETE
│   ├── CalculateInterest(borrowed, rate, elapsed_secs) → LegacyDec
│   │   └─ Formula: borrowed × annual_rate × (seconds / 365.25*86400)
│   │
│   ├── ComputeEffectiveRepayment(principal, interest) → Int
│   │   └─ Formula: principal + interest (truncated)
│   │
│   └── GetInterestRateForDenom(ctx, pool, denom) → LegacyDec, error
│       ├─ Gets pool-specific rate for coin1 or coin2
│       └─ Returns error if denom not in pool
│
├── leverage_liquidation.go (85 lines) ✅ COMPLETE
│   ├── ComputeHealthStatus(cr) → HealthStatus enum
│   │   ├─ HEALTHY: CR > 150%
│   │   ├─ AT_RISK: 120% ≤ CR ≤ 150%
│   │   └─ LIQUIDATABLE: CR < 120%
│   │
│   ├── ComputeCollateralRatio(collateral, debt) → LegacyDec
│   │   └─ Formula: collateral / debt
│   │
│   ├── IsPositionLiquidatable(ctx, pos) → bool
│   │   └─ Checks: CR < liquidation_threshold
│   │
│   ├── InitializeLiquidationInternal(ctx, pos) → error
│   │   ├─ Sets liquidation_status = INITIALIZED
│   │   └─ Records current block height
│   │
│   ├── ClearLiquidationPending(pos)
│   │   └─ Sets liquidation_status = NONE (used by AddCollateral)
│   │
│   ├── CanCloseBefore(ctx, pos) → bool
│   │   └─ Checks: block_height > created_block_height + delay
│   │
│   ├── BlocksUntilCloseable(ctx, pos) → uint64
│   │   └─ Returns: max(0, created_block_height + delay - block_height)
│   │
│   └── CanFinalizeLiquidationBefore(ctx, pos) → bool
│       └─ Checks: block_height > liquidation_initialized_height + delay
│
├── leverage_collateral.go (72 lines) ✅ COMPLETE
│   └── AddCollateral(ctx, msg) → MsgAddCollateralResponse, error
│       ├─ Validates ownership & pool match & denom match
│       ├─ Transfers collateral from user to module
│       ├─ Updates position.collateral
│       ├─ Clears liquidation_pending status
│       ├─ Recalculates collateral ratio
│       └─ Emits EventLeverageCollateralAdded ← FIX 2
│
├── query_leverage_health.go (145 lines) ✅ COMPLETE
│   ├── Position(ctx, req) → QueryPositionResponse
│   │   └─ Fetches position by ID
│   │
│   ├── PositionHealth(ctx, req) → QueryPositionHealthResponse
│   │   ├─ Calculates current collateral ratio
│   │   ├─ Determines health status (HEALTHY/AT_RISK/LIQUIDATABLE)
│   │   ├─ Returns CR, thresholds, block delay flags
│   │   └─ Used for monitoring position risk
│   │
│   └── PositionInterest(ctx, req) → QueryPositionInterestResponse
│       ├─ Fetches position
│       ├─ Calculates accrued interest (on-demand)
│       ├─ Computes total repayment
│       └─ Returns breakdown: borrowed, interest, total, rate
│
├── msg_server.go (48 lines) - ROUTING ONLY (PHASE 2)
│   └─ Comments indicate all handlers are in their respective files
│       (No actual implementations, just documentation)
│
└── query_server.go (69 lines) - EXISTING AMM QUERIES
    ├── Offer(ctx, req) → QueryOfferResponse
    ├── Metrics(ctx, req) → QueryMetricsResponse
    └─ (Leverage queries not yet added - PHASE 3)
```

### Type Definitions
```
x/whaleswap/types/
├── leverage.pb.go (GENERATED - 2000+ lines)
│   ├── LeveragePosition struct
│   ├── LeverageParams struct
│   ├── 6 Msg types + responses
│   ├── 3 Query types + responses
│   └── 5 Event types
│
├── params.go (78 lines)
│   ├── DefaultLeverageParams()
│   │   ├─ BlockDelayBeforeClose: 1
│   │   └─ BlockDelayBeforeLiquidation: 1
│   │
│   └── LeverageParams.Validate()
│       ├─ Checks BlockDelayBeforeClose > 0
│       └─ Checks BlockDelayBeforeLiquidation > 0
│
└── errors.go (TO BE UPDATED - PHASE 6)
    └─ Will add leverage-specific error codes
```

---

## 🔄 Message Flow Diagram

### Opening a Long Position
```
User Message: MsgOpenLongPosition
    ↓
keeper.OpenLongPosition(ctx, msg)
    ├─ Validate collateral
    ├─ Load pool
    ├─ Validate borrow cap
    ├─ Validate min CR = collateral / borrowed ≥ 1.5 (or pool param)
    ├─ Validate max leverage = (collateral + borrowed) / collateral ≤ 20x (or pool param)
    ├─ Allocate position ID
    ├─ Transfer collateral: user → module
    ├─ Update pool.TotalBorrowed
    ├─ Create position (simplified: held = borrowed × price)
    ├─ Index position by user & pool
    ├─ Emit EventLeveragePositionOpened
    └─ Return PositionId + Held amount
```

### Closing a Position
```
User Message: MsgClosePosition
    ↓
keeper.ClosePosition(ctx, msg)
    ├─ Load position
    ├─ Validate ownership
    ├─ Check block delay passed (created_block + 1 block)
    ├─ Calculate accrued interest
    ├─ Return collateral to user
    ├─ Return profit to user
    ├─ Update pool (decrease borrowed, add interest)
    ├─ Delete position
    ├─ Emit EventLeveragePositionClosed
    └─ Return profit + accrued interest
```

### Liquidating a Position
```
Step 1: InitializeLiquidation
  User Message: MsgInitializeLiquidation
      ↓
  keeper.InitializeLiquidation(ctx, msg)
      ├─ Validate position liquidatable (CR < 1.2)
      ├─ Set liquidation_status = INITIALIZED
      ├─ Record block height
      ├─ Emit EventLeverageLiquidationInitialized
      └─ Return CR + threshold

Step 2: Wait 1+ block

Step 3: FinalizeLiquidation
  Liquidator Message: MsgFinalizeLiquidation
      ↓
  keeper.FinalizeLiquidation(ctx, msg)
      ├─ Validate initialized & delay passed
      ├─ Calculate repayment (principal + interest)
      ├─ Collect repayment from liquidator
      ├─ Send all collateral to liquidator
      ├─ Calculate pool loss = max(0, repayment - collateral)
      ├─ Update pool
      ├─ Delete position
      ├─ Emit EventLeverageLiquidationFinalized
      └─ Return settlement details
```

---

## 🔧 Phase Completion Status

### ✅ Phase 1: Critical Fixes
- [x] Max leverage validation (lines 61-72, 183-194 in msg_leverage_open.go)
- [x] Event emission (5 types, 6 locations)
- [x] Liquidation settlement implementation
- [x] Proto generation
- [x] Code compilation

**Time: 27 min of 35 min estimated**

### ⏳ Phase 2: Message Server Routing (NEXT - 15 min)
**File:** `x/whaleswap/keeper/msg_server.go`
**Task:** Add 6 handler stubs that delegate to keeper methods

Handlers to add:
```go
func (k msgServer) OpenLongPosition(ctx context.Context, msg *types.MsgOpenLongPosition) (*types.MsgOpenLongPositionResponse, error)
func (k msgServer) OpenShortPosition(ctx context.Context, msg *types.MsgOpenShortPosition) (*types.MsgOpenShortPositionResponse, error)
func (k msgServer) ClosePosition(ctx context.Context, msg *types.MsgClosePosition) (*types.MsgClosePositionResponse, error)
func (k msgServer) AddCollateral(ctx context.Context, msg *types.MsgAddCollateral) (*types.MsgAddCollateralResponse, error)
func (k msgServer) InitializeLiquidation(ctx context.Context, msg *types.MsgInitializeLiquidation) (*types.MsgInitializeLiquidationResponse, error)
func (k msgServer) FinalizeLiquidation(ctx context.Context, msg *types.MsgFinalizeLiquidation) (*types.MsgFinalizeLiquidationResponse, error)
```

### ⏳ Phase 3: Query Server Routing (10 min)
**File:** `x/whaleswap/keeper/query_server.go`
**Task:** Add 3 query handler stubs

Handlers to add:
```go
func (k Keeper) Position(ctx context.Context, req *types.QueryPositionRequest) (*types.QueryPositionResponse, error)
func (k Keeper) PositionHealth(ctx context.Context, req *types.QueryPositionHealthRequest) (*types.QueryPositionHealthResponse, error)
func (k Keeper) PositionInterest(ctx context.Context, req *types.QueryPositionInterestRequest) (*types.QueryPositionInterestResponse, error)
```

### ⏳ Phase 4: Error Types (15 min)
**File:** `x/whaleswap/types/errors.go`
**Task:** Add leverage-specific error codes

### ⏳ Phase 5: Testing (2-4 hours)
**Directory:** `tests/whaleswap/leverage/`
**Files:**
- test_leverage_open_long.py
- test_leverage_open_short.py
- test_leverage_borrow_cap.py
- test_leverage_max_leverage.py
- test_leverage_health.py
- test_leverage_liquidation.py
- test_leverage_add_collateral.py
- test_leverage_close_position.py

---

## 📊 Key Data Structures

### LeveragePosition
```go
type LeveragePosition struct {
    PositionId uint64                    // Unique identifier
    PoolId uint64                        // Associated pool
    User string                          // Owner address
    PositionType PositionType            // LONG or SHORT
    Borrowed cosmos.base.v1beta1.Coin    // Principal borrowed
    Held cosmos.base.v1beta1.Coin        // Collateral held
    Collateral cosmos.base.v1beta1.Coin  // Deposited collateral
    BorrowTime *timestamp.Timestamp      // When position opened
    EntryPrice LegacyDec                 // Price at open
    CreatedBlockHeight uint64            // Block height created
    LiquidationStatus LiquidationStatus  // NONE or INITIALIZED
    LiquidationInitializedBlockHeight uint64
    AccruedInterest LegacyDec            // (unused, calculated on-demand)
}
```

### LeverageParams
```go
type LeverageParams struct {
    BlockDelayBeforeClose uint64           // Blocks to wait before owner can close
    BlockDelayBeforeLiquidation uint64    // Blocks to wait before liquidation finalized
}
```

### Pool (with leverage fields)
```go
type Pool struct {
    // ... existing AMM fields ...
    
    // Leverage fields (pool-specific)
    MinCollateralRatio string              // e.g., "1.5" (LegacyDec)
    MaxLeverageRatio string                // e.g., "20.0" (LegacyDec)
    LiquidationThreshold string            // e.g., "1.2" (LegacyDec)
    InterestRateCoin1 string               // e.g., "0.05" (annual APY)
    InterestRateCoin2 string
    MaxBorrowPercentCoin1 string           // e.g., "0.8" (80% of reserves)
    MaxBorrowPercentCoin2 string
    TotalBorrowed []cosmos.base.v1beta1.Coin
    InterestEarned []cosmos.base.v1beta1.Coin
}
```

---

## 🎯 Integration Points

### With Bank Module
- Transfer collateral: user → module
- Transfer collateral: module → liquidator
- Transfer repayment: liquidator → module

### With Nameservice
- (Future) Resolve leverage liquidators via nameservice

### With NFT
- (Future) Positions as NFTs

### With Storage
- (Future) Position metadata stored as structured data

---

## 📝 Notes & Constraints

### Simplified Implementation (MVP)
- **Swap execution:** Not real AMM swap; uses `held = borrowed × price` approximation
  - Location: `msg_leverage_open.go` lines 99, 221
  - Rationale: Acceptable for MVP; production needs actual swap logic
  - Future: Integrate with `msg_pool_swap.go` logic

- **Interest calculation:** On-demand only (no accrual schedule)
  - Calculated fresh at: query, close, liquidation
  - Formula: `borrowed × annual_rate × (seconds_elapsed / 365.25*86400)`

- **Block delay:** Hardcoded to 1 block for both close and liquidation
  - Could make configurable in LeverageParams later

### Design Decisions
- **Pool-level parameters:** min_collateral_ratio, max_leverage_ratio, liquidation_threshold
  - Rationale: Each pool operator controls their risk
  - Falls back to defaults if not set

- **On-demand interest:** No background accrual process
  - Rationale: Simpler state management
  - Tradeoff: Interest calculated at every query/close/liquidation

- **Two-step liquidation:** Initialize → Wait 1 block → Finalize
  - Rationale: Ensures fair opportunity for owner to add collateral
  - Implementation: Block heights tracked in position

- **Liquidator settlement:** Liquidator must pay full debt, receives full collateral
  - Rationale: Clear incentives, no ambiguity
  - Pool loss tracked for governance visibility

---

## 🚀 Ready for Phase 2

All blockers cleared. Code compiles, proto generated. Ready to add message server routing.

**Next command:** Phase 2 - Message Server Routing
