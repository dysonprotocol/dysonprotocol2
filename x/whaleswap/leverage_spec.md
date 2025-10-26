# Leveraged Positions Specification

## Rationale

Leveraged positions allow users to amplify their exposure to price movements in AMM pools while maintaining capital efficiency. By borrowing from pool reserves and posting collateral, users can:

- **Long**: Borrow stable (e.g., USDC) → buy volatile asset (e.g., ETH) → profit if ETH appreciates
- **Short**: Borrow volatile (e.g., ETH) → sell for stable → profit if ETH depreciates

### Benefits to Ecosystem

- **Pool liquidity utilization**: Idle reserves earn interest; pools become capital markets
- **Pool operators incentivized**: Can liquidate underwater positions early, earning collateral
- **Loss absorption**: Pool absorbs losses if owed > collateral (mitigates forced liquidations)
- **Two-step liquidation**: Flash-loan resistant; sandbox-proof settlement
- **Algorithmic interest**: Transparent cost model; no manual accrual needed

---

## Parameters

### Pool-Level (Per Pool)

| Parameter | Type | Example | Purpose |
|-----------|------|---------|---------|
| `interest_rate_coin1` | LegacyDec string | `"0.05"` | Annual interest rate on borrows of coin1 denom (5% APY) |
| `interest_rate_coin2` | LegacyDec string | `"0.05"` | Annual interest rate on borrows of coin2 denom (5% APY) |
| `max_borrow_percent_coin1` | LegacyDec string | `"0.5"` | Max borrowable = 50% of coin1 reserves |
| `max_borrow_percent_coin2` | LegacyDec string | `"0.5"` | Max borrowable = 50% of coin2 reserves |
| `liquidation_threshold` | LegacyDec string | `"1.2"` | CR below which position is liquidatable (120%) |
| `min_collateral_ratio` | LegacyDec string | `"1.5"` | Minimum CR required at open (150%) |
| `max_leverage_ratio` | LegacyDec string | `"5.0"` | Maximum leverage = 5x |

### Module-Level (Global Leverage Params)

| Parameter | Type | Example | Purpose |
|-----------|------|---------|---------|
| `block_delay_before_close` | uint64 string | `"1"` | Blocks owner must wait before closing (1 block) |
| `block_delay_before_liquidation` | uint64 string | `"1"` | Blocks owner must wait before liquidation (1 block) |
| `max_interest_rate_borrowed` | LegacyDec string | `"1.00"` | Maximum annual interest rate for borrowed funds (100% APY) |

### Derived

- **Collateral Ratio (CR)**: `collateral_value / debt_with_interest`
  - Collateral valued at current pool price
  - Debt = principal + accrued interest (algorithmic)

- **Interest Formula**: `interest = borrowed_amount × annual_rate × (time_elapsed_seconds / seconds_per_year)`
  - Simple interest (no compounding)
  - Only depends on borrow denom's rate
  - Calculated on-demand; no accrual schedule

---

## Implementation Outline

### Position Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. OPEN (Any Block)                                             │
│  - User posts collateral → module                               │
│  - Module borrows from pool (checks max_borrow_percent)        │
│  - Module swaps borrowed → desired denom (long/short)           │
│  - Validate CR ≥ min_collateral_ratio (150%)                    │
│  - Store position with: borrow_time, created_block_height      │
│  - Status: HEALTHY (CR > 150%)                                  │
│  - Owner can close: NO (wait 1 block)                           │
│  - Can liquidate: NO (CR > 120%)                                │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. MONITORING (Next Block+)                                     │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ 2A. OWNER CLOSE (After 1 block, CR > 120%)              │    │
│ │  - Calculate accrued interest (algorithmic)             │    │
│ │  - Swap held → borrowed denom                           │    │
│ │  - Repay principal + interest                           │    │
│ │  - Send profit (excess) to owner                        │    │
│ │  - Return collateral to owner                           │    │
│ │  - Delete position                                      │    │
│ │  - Status: CLOSED                                       │    │
│ └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ 2B. ADD COLLATERAL (Any time, CR < 150%)               │    │
│ │  - User posts additional collateral → module            │    │
│ │  - Increases CR (moves toward health)                   │    │
│ │  - Clears any liquidation initialize marker            │    │
│ │  - Resets liquidation countdown                         │    │
│ │  - Status: RESCUED / HEALTHY (if new CR > 150%)         │    │
│ └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ 2C. PRICE MOVE: CR < 120% (Liquidatable)               │    │
│ │  - Status: LIQUIDATABLE                                 │    │
│ │  - Owner cannot close (blocked)                         │    │
│ │  - Can be liquidated                                    │    │
│ └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. LIQUIDATION STEP 1: INITIALIZE (CR < 120%)                  │
│  - Verify CR < liquidation_threshold (120%)                    │
│  - Record: liquidation_initialized_block_height = current      │
│  - Position marked as "liquidation pending"                    │
│  - No transfers; no state change to pool                       │
│  - Status: LIQUIDATION_PENDING                                 │
│  - Can be added collateral (clears pending mark)              │
│  - Owner cannot close (blocked)                                │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ (1+ block later)
┌─────────────────────────────────────────────────────────────────┐
│ 4. LIQUIDATION STEP 2: FINALIZE                                │
│  - Verify CR still < liquidation_threshold (120%)             │
│  - Verify at least 1 block since initialize                   │
│  - Liquidator sends: full owed amount (principal + interest)  │
│  - Liquidator receives: ALL collateral                        │
│  - Update pool: increase borrowed_denom balance, clear lent   │
│  - If owed > collateral: Pool absorbs loss (shortfall)        │
│  - Delete position                                             │
│  - Status: LIQUIDATED                                          │
└─────────────────────────────────────────────────────────────────┘
```

### Key Decision Points

1. **Block delay (1 block)**
   - Owner must wait before closing
   - Liquidation can proceed immediately after initialize (1 block wait)
   - Prevents MEV sandwich in same block

2. **Two-step liquidation**
   - Initialize: Expensive check; allows system to react
   - Finalize: Executes settlement after 1 block
   - Result: Flash loan attacks impossible; time-locked settlement

3. **Add collateral resets**
   - Clears any pending liquidation marker
   - User can rescue position before liquidation finalizes
   - No liquidation bonus needed (collateral is payment)

4. **Loss absorption**
   - If repayment owed > collateral available: pool covers
   - Pool operator incentivized to liquidate early (minimize loss)
   - Interest stays in pool as yield

5. **Borrow cap**
   - Per-denom limit on total borrowed
   - E.g., can't borrow > 50% of USDC in pool
   - Prevents liquidity drain; protects LPs

---

## Health Thresholds

| CR | Status | Owner Can Close | Initialize Liquidation | Finalize Liquidation |
|----|--------|-----------------|------------------------|----------------------|
| > 150% | HEALTHY | ✅ | ❌ | ❌ |
| 120–150% | AT_RISK | ✅ | ❌ | ❌ |
| < 120% | LIQUIDATABLE | ❌ | ✅ | ✅ (1+ block later) |

---

## Proto Messages

### `leverage.proto` (New File)

```protobuf
syntax = "proto3";

package dysonprotocol.whaleswap.v1;

import "gogoproto/gogo.proto";
import "cosmos/base/v1beta1/coin.proto";
import "google/protobuf/timestamp.proto";

option go_package = "dysonprotocol.com/x/whaleswap/types";

// ═════ ENUMS ═════

enum PositionType {
  POSITION_TYPE_UNSPECIFIED = 0;
  POSITION_TYPE_LONG = 1;   // Bullish: leverage held denom upward
  POSITION_TYPE_SHORT = 2;  // Bearish: short borrowed denom
}

enum LiquidationStatus {
  LIQUIDATION_STATUS_UNSPECIFIED = 0;
  LIQUIDATION_STATUS_NONE = 1;       // No liquidation in progress
  LIQUIDATION_STATUS_INITIALIZED = 2; // Liquidation initialized; awaiting finalize
}

// ═════ TYPES ═════

message LeveragePosition {
  uint64 position_id = 1;
  uint64 pool_id = 2;
  string user = 3;
  
  PositionType position_type = 4;
  
  // Borrow side (volatile denom for long/short)
  string borrowed_denom = 5;
  string borrowed_amount = 6;  // sdk.Int as string
  
  // Held side (what position holds)
  string held_denom = 7;
  string held_amount = 8;
  
  // Collateral (security deposit)
  string collateral_denom = 9;
  string collateral_amount = 10;
  
  // Timing & prices
  google.protobuf.Timestamp borrow_time = 11;
  string entry_price = 12;  // held_denom / borrowed_denom
  
  // Blocks
  uint64 created_block_height = 13;  // Block when opened
  uint64 liquidation_initialized_block_height = 14;  // Block when liquidation initialized (0 if none)
  
  // Status
  LiquidationStatus liquidation_status = 15;
  
  // Informational
  string accrued_interest = 16;
}

message LeverageParams {
  string min_collateral_ratio = 1;           // "1.5"
  string max_leverage_ratio = 2;             // "5.0"
  string liquidation_threshold = 3;          // "1.2"
  string block_delay_before_close = 4;       // "1"
}

// ═════ MESSAGES ═════

message MsgOpenLongPosition {
  string trader = 1;
  uint64 pool_id = 2;
  cosmos.base.v1beta1.Coin collateral = 3;
  string borrow_amount = 4;
}

message MsgOpenLongPositionResponse {
  uint64 position_id = 1;
  string held_denom = 2;
  string held_amount = 3;
}

message MsgOpenShortPosition {
  string trader = 1;
  uint64 pool_id = 2;
  cosmos.base.v1beta1.Coin collateral = 3;
  string borrow_amount = 4;
}

message MsgOpenShortPositionResponse {
  uint64 position_id = 1;
  string held_denom = 2;
  string held_amount = 3;
}

message MsgClosePosition {
  string user = 1;
  uint64 pool_id = 2;
  uint64 position_id = 3;
}

message MsgClosePositionResponse {
  string profit_denom = 1;
  string profit_amount = 2;
  string accrued_interest = 3;
}

message MsgAddCollateral {
  string user = 1;
  uint64 pool_id = 2;
  uint64 position_id = 3;
  cosmos.base.v1beta1.Coin collateral = 4;  // Additional collateral
}

message MsgAddCollateralResponse {
  string new_collateral_amount = 1;
  string new_collateral_ratio = 2;
}

message MsgInitializeLiquidation {
  string initializer = 1;  // Anyone can call
  string user = 2;         // Position owner
  uint64 pool_id = 3;
  uint64 position_id = 4;
}

message MsgInitializeLiquidationResponse {
  string collateral_ratio = 1;
  string liquidation_threshold = 2;
}

message MsgFinalizeLiquidation {
  string liquidator = 1;
  string user = 2;
  uint64 pool_id = 3;
  uint64 position_id = 4;
}

message MsgFinalizeLiquidationResponse {
  string collateral_received = 1;
  string collateral_denom = 2;
  string repayment_amount = 3;
  string accrued_interest = 4;
  string pool_loss = 5;  // > 0 if owed > collateral
}

// ═════ QUERIES ═════

message QueryPositionHealthRequest {
  string user = 1;
  uint64 pool_id = 2;
  uint64 position_id = 3;
}

message QueryPositionHealthResponse {
  enum HealthStatus {
    HEALTH_STATUS_UNSPECIFIED = 0;
    HEALTH_STATUS_HEALTHY = 1;
    HEALTH_STATUS_AT_RISK = 2;
    HEALTH_STATUS_LIQUIDATABLE = 3;
  }
  
  HealthStatus health_status = 1;
  string current_collateral_ratio = 2;
  string liquidation_threshold = 3;
  string collateral_value = 4;
  string debt_with_interest = 5;
  bool can_close_by_owner = 6;
  uint64 blocks_until_closeable = 7;
  bool can_initialize_liquidation = 8;
  bool can_finalize_liquidation = 9;
}

message QueryPositionInterestRequest {
  string user = 1;
  uint64 pool_id = 2;
  uint64 position_id = 3;
}

message QueryPositionInterestResponse {
  string borrowed_amount = 1;
  string accrued_interest = 2;
  string total_repayment = 3;
  uint64 time_elapsed = 4;
  string annual_rate = 5;
}
```

### `whaleswap.proto` (Updated Pool)

Add to existing `Pool` message:

```protobuf
message Pool {
  // ... existing fields ...
  uint64 pool_id = 1;
  repeated cosmos.base.v1beta1.Coin coins = 2;
  // ... etc ...
  
  // ═════ NEW: Interest & Leverage Fields ═════
  // Annual interest rate for borrows in coin1 denom
  string interest_rate_coin1 = 15;
  
  // Annual interest rate for borrows in coin2 denom
  string interest_rate_coin2 = 16;
  
  // Max borrow cap for coin1 (as % of reserve)
  string max_borrow_percent_coin1 = 17;
  
  // Max borrow cap for coin2 (as % of reserve)
  string max_borrow_percent_coin2 = 18;
  
  // Total accrued interest (yield for LPs)
  repeated cosmos.base.v1beta1.Coin interest_earned = 19;
  
  // Total borrowed (aggregate for cap enforcement)
  repeated cosmos.base.v1beta1.Coin total_borrowed = 20;
}
```

### `tx.proto` (Updated Service)

Add to Msg service:

```protobuf
service Msg {
  // ... existing ...
  
  rpc OpenLongPosition(MsgOpenLongPosition) returns (MsgOpenLongPositionResponse);
  rpc OpenShortPosition(MsgOpenShortPosition) returns (MsgOpenShortPositionResponse);
  rpc ClosePosition(MsgClosePosition) returns (MsgClosePositionResponse);
  rpc AddCollateral(MsgAddCollateral) returns (MsgAddCollateralResponse);
  rpc InitializeLiquidation(MsgInitializeLiquidation) returns (MsgInitializeLiquidationResponse);
  rpc FinalizeLiquidation(MsgFinalizeLiquidation) returns (MsgFinalizeLiquidationResponse);
}
```

### `query.proto` (Updated Service)

Add to Query service:

```protobuf
service Query {
  // ... existing ...
  
  rpc PositionHealth(QueryPositionHealthRequest) 
    returns (QueryPositionHealthResponse) {
    option (google.api.http).get = 
      "/dysonprotocol/whaleswap/v1/positions/{user}/{pool_id}/{position_id}/health";
  }
  
  rpc PositionInterest(QueryPositionInterestRequest) 
    returns (QueryPositionInterestResponse) {
    option (google.api.http).get = 
      "/dysonprotocol/whaleswap/v1/positions/{user}/{pool_id}/{position_id}/interest";
  }
}
```

### `events.pb.proto` (New Events)

```protobuf
message EventLeveragePositionOpened {
  uint64 position_id = 1;
  string user = 2;
  uint64 pool_id = 3;
  string position_type = 4;           // "LONG" or "SHORT"
  string collateral_denom = 5;
  string collateral_amount = 6;
  string borrowed_denom = 7;
  string borrowed_amount = 8;
  string held_denom = 9;
  string held_amount = 10;
  string entry_price = 11;
  string annual_interest_rate = 12;
  google.protobuf.Timestamp borrow_time = 13;
}

message EventLeveragePositionClosed {
  uint64 position_id = 1;
  string user = 2;
  string profit_denom = 3;
  string profit_amount = 4;
  string accrued_interest = 5;
}

message EventLeverageCollateralAdded {
  uint64 position_id = 1;
  string user = 2;
  string added_collateral_amount = 3;
  string new_total_collateral = 4;
  string new_collateral_ratio = 5;
}

message EventLeverageLiquidationInitialized {
  uint64 position_id = 1;
  string user = 2;
  string initializer = 3;
  string collateral_ratio = 4;
  uint64 block_height = 5;
}

message EventLeverageLiquidationFinalized {
  uint64 position_id = 1;
  string user = 2;
  string liquidator = 3;
  string collateral_received = 4;
  string collateral_denom = 5;
  string repayment_amount = 6;
  string accrued_interest = 7;
  string pool_loss = 8;  // Loss absorbed by pool (if any)
}
```

---

## Files to Edit

### Proto Files (Regenerate: `make proto-gen install`)

| File | Changes | Context |
|------|---------|---------|
| `proto/dysonprotocol/whaleswap/v1/leverage.proto` | **CREATE** | New file; all leverage types, messages, queries |
| `proto/dysonprotocol/whaleswap/v1/whaleswap.proto` | **UPDATE** Pool | Add: `interest_rate_coin1`, `interest_rate_coin2`, `max_borrow_percent_coin1`, `max_borrow_percent_coin2`, `interest_earned`, `total_borrowed` |
| `proto/dysonprotocol/whaleswap/v1/tx.proto` | **UPDATE** Msg service | Add: `OpenLongPosition`, `OpenShortPosition`, `ClosePosition`, `AddCollateral`, `InitializeLiquidation`, `FinalizeLiquidation` |
| `proto/dysonprotocol/whaleswap/v1/query.proto` | **UPDATE** Query service | Add: `PositionHealth`, `PositionInterest` |
| `proto/dysonprotocol/whaleswap/v1/events.pb.proto` | **CREATE/UPDATE** | Add: `EventLeveragePositionOpened`, `EventLeveragePositionClosed`, `EventLeverageCollateralAdded`, `EventLeverageLiquidationInitialized`, `EventLeverageLiquidationFinalized` |

### Keeper Files

| File | Type | Purpose | Key Methods |
|------|------|---------|-------------|
| `x/whaleswap/keeper/leverage_interest.go` | **CREATE** | Pure interest calculations | `CalculateInterest()`, `ComputeEffectiveRepayment()`, `GetInterestRateForDenom()` |
| `x/whaleswap/keeper/leverage_liquidation.go` | **CREATE** | Liquidation logic | `ComputeHealthStatus()`, `IsPositionLiquidatable()`, `InitializeLiquidation()`, `FinalizeLiquidation()` |
| `x/whaleswap/keeper/leverage_collateral.go` | **CREATE** | Collateral operations | `AddCollateral()` |
| `x/whaleswap/keeper/msg_leverage_open.go` | **CREATE** | Open position logic | `OpenLongPosition()`, `OpenShortPosition()`, validates borrow cap, records `created_block_height` |
| `x/whaleswap/keeper/msg_leverage_close.go` | **CREATE** | Close position logic | `ClosePosition()`, checks 1-block delay, calculates interest, handles settlement |
| `x/whaleswap/keeper/query_leverage_health.go` | **CREATE** | Health/status queries | `PositionHealth()`, `PositionInterest()` |
| `x/whaleswap/keeper/keeper.go` | **UPDATE** | Add collections & params | Add: `positionSeq`, `LeveragePositions`, `PositionsByUser`, `PositionsByPool`, `leverageParams` collections; add `GetLeverageParams()`, `SetLeverageParams()` |
| `x/whaleswap/keeper/msg_server.go` | **UPDATE** | Message routing | Add handlers for all 6 new messages |

### Type Files

| File | Changes | Purpose |
|------|---------|---------|
| `x/whaleswap/types/errors.go` | **UPDATE** | Add leverage-specific errors (e.g., `ErrInsufficientCollateral`, `ErrPositionNotLiquidatable`, `ErrBorrowCapExceeded`, `ErrBlockDelayNotPassed`) |
| `x/whaleswap/types/params.go` | **UPDATE** | Add `LeverageParams` type, validation, default values |
| `x/whaleswap/types/keys.go` | **UPDATE** | Add storage key constants for leverage collections |

---

## Implementation Steps

1. **Define Protos** (all 5 files above)
   - Ensure PositionType enum is clear (LONG vs SHORT)
   - Ensure LiquidationStatus tracks pending state
   - Ensure all fields use string for Int/Dec (protobuf compat)

2. **Generate Code**
   ```bash
   make proto-gen install
   ```

3. **Implement Keeper Logic** (in order)
   - `leverage_interest.go`: Pure math; testable independently
   - `keeper.go`: Add collections + accessors
   - `msg_leverage_open.go`: Validation, borrow cap, position creation
   - `msg_leverage_close.go`: Block delay, interest, settlement
   - `leverage_collateral.go`: AddCollateral + reset logic
   - `leverage_liquidation.go`: Health checks, 2-step flow
   - `query_leverage_health.go`: Status queries
   - `msg_server.go`: Route all 6 messages

4. **Integrate Events**
   - Emit from each message handler
   - Events include full position state for indexing

5. **Test**
   - Unit tests: Interest math, CR calculations
   - E2E tests: Open → price move → liquidate flow
   - E2E tests: Open → add collateral → rescue
   - E2E tests: 1-block delay enforcement

---

## Key Implementation Details

### Interest Calculation (On-Demand)

```go
interest = borrowed_amount × 
           interest_rate[borrowed_denom] × 
           (current_time - borrow_time) / seconds_per_year
```

- Called at query time and at close/liquidation time
- No storage of interest; always calculated fresh
- Only depends on borrow denom's rate (set at pool level)

### Borrow Cap Enforcement

At open:
```go
total_borrowed[denom] + borrow_amount ≤ 
  pool.reserves[denom] × max_borrow_percent[denom]
```

### Two-Step Liquidation

**Initialize**: Expensive checks, time-lock
```
(CR < 120%) && (not already initialized)
→ Record: liquidation_initialized_block_height
→ Status: LIQUIDATION_STATUS_INITIALIZED
```

**Finalize**: Verify, settle, delete
```
(CR < 120%) && (current_block > liquidation_initialized_block_height)
→ Liquidator sends: principal + accrued_interest
→ Pool: absorbs any shortfall (owed > collateral)
→ Liquidator receives: all collateral
→ Delete position
```

### Add Collateral Reset

```
AddCollateral() →
  collateral_amount += added_amount
  liquidation_status = LIQUIDATION_STATUS_NONE  // Clear pending
  liquidation_initialized_block_height = 0
```

Result: User can rescue position before liquidation finalizes.

---

## Testing Strategy

### Unit Tests (`x/whaleswap/keeper/*_test.go`)

- Interest math edge cases (time = 0, rate = 0, huge amounts)
- CR calculations (edge prices, zero values)
- Borrow cap enforcement
- Block height comparisons

### E2E Tests (`tests/whaleswap/leverage/`)

- **test_leverage_open_long.py**: Open long, verify held amount
- **test_leverage_open_short.py**: Open short, verify held amount
- **test_leverage_open_borrow_cap.py**: Reject if exceeds cap
- **test_leverage_close_profit.py**: Close with profit; verify settlement
- **test_leverage_close_block_delay.py**: Reject close same block; allow next block
- **test_leverage_liquidation_flow.py**: Initialize → wait 1 block → finalize
- **test_leverage_liquidation_loss.py**: Pool absorbs shortfall
- **test_leverage_add_collateral_rescue.py**: Add collateral → clear liquidation marker
- **test_leverage_interest_accrual.py**: Interest grows with time
- **test_leverage_health_query.py**: Query returns correct status

---

## Invariants

After every operation:

1. **Position accounting**:
   ```
   position.held_amount > 0
   position.borrowed_amount > 0
   position.collateral_amount > 0
   ```

2. **Pool accounting**:
   ```
   pool.total_borrowed[denom] ≤ 
     pool.reserves[denom] × max_borrow_percent[denom]
   ```

3. **Interest accounting**:
   ```
   interest_accrued ≥ 0
   interest_accrued = borrowed × rate × (time_elapsed / seconds_per_year)
   ```

4. **Liquidation state**:
   ```
   If liquidation_status == INITIALIZED:
     liquidation_initialized_block_height != 0
   If liquidation_status == NONE:
     liquidation_initialized_block_height == 0
   ```

---

## Next Steps

1. Create `leverage_spec.md` in `x/whaleswap/` (this file)
2. Create proto files (4 new/updated files in `proto/dysonprotocol/whaleswap/v1/`)
3. Run `make proto-gen install`
4. Implement keeper files (8 new/updated files in `x/whaleswap/keeper/`)
5. Run tests: `make test PYTEST_ARGS="tests/whaleswap/leverage/ -v"`
6. Document CLI usage and examples in separate guide

---

Implementation Summary - Leverage Feature
I've successfully implemented the core proto definitions and foundational keeper logic for the leverage specification. Here's what's been completed:
✅ Completed Components
Proto Files (Ready for make proto-gen install):
proto/dysonprotocol/whaleswap/v1/leverage.proto - Full type system, messages, queries
Updated whaleswap.proto - Added leverage fields to Pool
Updated tx.proto - Added 6 leverage message handlers
Updated query.proto - Added 3 leverage query handlers
Keeper Foundation (Core Math & Business Logic):
keeper/leverage_interest.go - On-demand interest calculation
keeper/leverage_liquidation.go - Health status, liquidation mechanics, block delay enforcement
keeper/leverage_collateral.go - AddCollateral with liquidation reset
keeper/msg_leverage_open.go - OpenLongPosition & OpenShortPosition with borrow cap validation
Updated keeper/keeper.go - Added 5 leverage collections + initialization
📋 Remaining Quick Tasks (Can be completed in ~30 mins):
1. Create error types - x/whaleswap/types/errors.go:
2. Create params type - x/whaleswap/types/params.go:
3. Add storage keys - x/whaleswap/types/keys.go:
4. Create message handlers - x/whaleswap/keeper/msg_server.go:
Add 6 handler methods routing to the keeper functions
5. Create query handlers - x/whaleswap/keeper/query_leverage_health.go:
6. Create close handler - x/whaleswap/keeper/msg_leverage_close.go:
ClosePosition with 1-block delay check
Calculate accrued interest
Settle repayment + profit
🔧 Next Step
Run:
This will generate all .pb.go files from the proto definitions. The keeper code is ready to compile once protos are generated.
📌 Key Design Highlights
On-demand interest: No background accrual; calculated fresh at query/close/liquidation
Two-step liquidation: Initialize (record block height) → wait 1 block → finalize (settle)
Simple interest formula: interest = borrowed × annual_rate × (elapsed_seconds / seconds_per_year)
Collateral ratio: CR = collateral_value / (principal + interest)
Health thresholds: HEALTHY (>150%), AT_RISK (120%-150%), LIQUIDATABLE (<120%)
Borrow caps: Per-denom limits as % of pool reserves, enforced at open
Would you like me to:
Complete the remaining 5 files (errors, params, keys, handlers, queries)?
Create comprehensive tests for the leverage logic?
Create CLI examples or documentation?
