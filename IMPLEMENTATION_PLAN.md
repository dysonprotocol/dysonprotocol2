## Leverage Enhancements – Implementation Plan

### 1. Goals
- Fix leverage interest accounting so we never “forget” unpaid interest.
- Add `MsgRemoveCollateral` to safely withdraw excess collateral.
- Add `MsgPartialClosePosition` to reduce position size without a full unwind.

### 2. Interest Accounting Redesign
We will treat interest as an explicit liability that only changes when a transaction touches the position.

#### 2.1 New/Repurposed State Fields (`LeveragePosition`)
- `initial_borrowed`: snapshot of the opening principal (analytics, limits).
- `borrowed` (existing): current outstanding principal.
- `accrued_interest`: rename semantics to “unpaid interest carried forward”.
- `total_interest_paid`: running counter for metrics/UX.
- `last_interest_settlement_time`: last timestamp we flushed fresh interest into `accrued_interest`.

#### 2.2 Settlement Flow (run at the start of any keeper method touching the position)
1. Read `elapsed = now - last_interest_settlement_time`.
2. Compute `fresh_interest = borrowed * rate * elapsed / seconds_per_year`.
3. `interest_due = accrued_interest + fresh_interest`.
4. Do not mutate state yet. Return `interest_due` plus helpers to the caller.

#### 2.3 Paying Interest
When a user supplies funds (cover, close, partial close, liquidation, etc.):
1. Require that we cover `interest_due` first.
2. `interest_paid = min(payment, interest_due)`; subtract from `interest_due`.
3. Any unpaid remainder becomes the new `accrued_interest`.
4. Increment `total_interest_paid += interest_paid`.
5. Set `last_interest_settlement_time = now`.
6. Only after the above do we touch principal (reduce/increase `borrowed`).

#### 2.4 Benefits
- Deterministic (no background cron needed).
- No “interest reset” exploits; clocks only move when settlements happen.
- Accurate reporting (`total_interest_paid`, `accrued_interest`).
- Clean separation between structural updates (`UpdatedTime`) and finance (`last_interest_settlement_time`). We can keep `UpdatedTime` for operational auditing.

### 3. Keeper Refactors
Create helper(s) inside `x/whaleswap/keeper/leverage_interest.go`:
- `func (k Keeper) RefreshInterest(ctx context.Context, pos *LeveragePosition) (math.LegacyDec, error)` – mutates pos: adds fresh interest into `accrued_interest`, updates `last_interest_settlement_time`, returns total interest due as `math.LegacyDec`.
- `func (k Keeper) PayInterest(pos *LeveragePosition, payment math.Int) (interestPaid sdk.Coin, remainingPayment math.Int, error)` – subtracts from `accrued_interest`, updates `total_interest_paid`, ensures we never drop below zero.

Update all existing flows (`OpenPosition`, `ClosePosition`, `CoverPosition`, liquidation initialize/finalize, future remove/partial close) to call these helpers.

### 4. MsgRemoveCollateral
1. **Proto**: add request/response messages + `EventLeverageCollateralRemoved`.
2. **Validation**:
   - Position open/liquidating, caller owns it, denom matches.
   - Amount > 0 and <= current collateral.
3. **Interest Handling**: call `RefreshInterest`; no payment required but CR calculation must use `borrowed + interest_due`.
4. **CR Check**: convert collateral value to borrow denom using live pool price; ensure new CR ≥ `min_collateral_ratio`.
5. **State Update**:
   - Transfer collateral from module → user.
   - Update `pos.Collateral`, `pos.UpdatedTime/Height`.
   - Leave interest untouched (since no payment).
6. **Emit Event** + response with new CR.

### 5. MsgPartialClosePosition (integrated into `MsgClosePosition`)
1. **Proto**: `MsgPartialClosePosition` (fractional parameter or explicit target amounts – we’ll use `fraction` Dec for now) + response + `EventLeveragePositionPartiallyClosed`.
2. **Flow**:
   - Validate fraction (0 < f < 1) and block-delay (same as close).
   - `RefreshInterest`, compute interest/principal owed for the chosen fraction:
     - `principal_to_close = borrowed * f`.
     - `interest_to_close = interest_due * f`.
   - Swap `held * f` to borrowed denom via borrow vault.
   - Cover `interest_to_close` first, then `principal_to_close`.
   - If proceeds < required repayment, pull needed amount from collateral (swap when cross-denom). Reject if still short.
   - Return proportional collateral (`collateral * f`) minus any portion consumed for shortfall.
   - Update pool totals (interest earned, total borrowed) and position fields (borrowed, held, collateral, `UpdatedTime`, `last_interest_settlement_time` already set by helper).
   - Recompute CR, emit event/response.

### 6. Proto / Generated Code Steps
1. Update `proto/dysonprotocol/whaleswap/v1/leverage.proto` with new fields + comments.
2. Update `events.proto` & `tx.proto` with new msgs/events.
3. `make proto-gen install`.
4. Regenerate ts/python clients if required (follow existing workflows).

### 7. Keeper / Logic Updates
1. Implement interest helpers in `leverage_interest.go`.
2. Refactor existing msgs (`OpenPosition`, `ClosePosition`, `CoverPosition`, liquidation flows) to use the new helpers and fields.
3. Implement `MsgRemoveCollateral` and `MsgPartialClosePosition`.
4. Update `msg_server.go` to wire the new handlers.
5. Extend invariants/tests to cover new accounting guarantees.

### 8. Testing Strategy
- **Unit tests**:
  - Interest helper edge cases (zero elapsed, partial payments, rounding).
  - Remove collateral CR enforcement.
  - Partial close scenarios: profitable, underwater, cross-denom collateral.
- **Integration tests (`tests/whaleswap/…`)**:
  - End-to-end flow: open → accrue → partial close → cover → remove collateral.
  - Liquidation path verifying new interest tracking.
- **Invariants**: ensure module balances & pool accounting still hold after new flows.

### 9. Follow-ups
- Revisit UI/query layers to expose `initial_borrowed`, `total_interest_paid`, `accrued_interest`.
- Update docs (`docs/whaleswap_guide.md`) describing the new interest model and messages.

