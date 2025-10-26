# Leverage Feature - Critical Fixes (PHASE 1)

## ⚡ Quick Reference: 3 Fixes to Apply Before `make proto-gen install`

---

## FIX 1: Max Leverage Validation (5 min)

**File:** `x/whaleswap/keeper/msg_leverage_open.go`

**Location:** In both `OpenLongPosition()` and `OpenShortPosition()` functions

**Apply after line:** After CR validation, before position creation

**Code to Add:**

```go
// Validate maximum leverage
if params != nil && params.MaxLeverageRatio != "" {
    maxLeverage, _ := math.LegacyNewDecFromStr(params.MaxLeverageRatio)
    // leverage = (collateral + borrowed) / collateral
    leverage := collateral.Add(borrowed).Quo(collateral)
    if leverage.GT(maxLeverage) {
        return nil, cosmossdkerrors.Wrapf(
            sdkerrors.ErrInvalidRequest,
            "leverage %s exceeds max %s",
            leverage.String(),
            maxLeverage.String(),
        )
    }
}
```

**Why:** Prevents unlimited leverage abuse; parameter exists but was never validated

---

## FIX 2: Event Emission Framework (10 min)

**File:** `x/whaleswap/keeper/msg_leverage_handlers.go`

**Add Event Emission Pattern:**

For **OpenLongPosition**:
```go
if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionOpened{
    PositionId:    posID,
    User:          msg.Trader,
    PoolId:        msg.PoolId,
    PositionType:  "LONG",
    CollateralDenom: pos.CollateralDenom,
    CollateralAmount: pos.CollateralAmount,
    BorrowedDenom:   pos.BorrowedDenom,
    BorrowedAmount:  pos.BorrowedAmount,
    HeldDenom:       pos.HeldDenom,
    HeldAmount:      pos.HeldAmount,
    EntryPrice:      pos.EntryPrice,
    AnnualInterestRate: rateStr,
    BorrowTime:      pos.BorrowTime,
}); err != nil {
    return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
}
```

Apply same pattern to all 6 handlers with appropriate event types:
- `EventLeveragePositionOpened` (2 handlers: long + short)
- `EventLeveragePositionClosed` (1 handler)
- `EventLeverageCollateralAdded` (1 handler)
- `EventLeverageLiquidationInitialized` (1 handler)
- `EventLeverageLiquidationFinalized` (1 handler)

**Why:** Enables indexing and monitoring; currently no events are emitted

---

## FIX 3: Liquidation Settlement Implementation (20 min)

**File:** `x/whaleswap/keeper/msg_leverage_handlers.go`

**Function:** `FinalizeLiquidation()`

**Current (Stub):**
```go
func (k Keeper) FinalizeLiquidation(ctx context.Context, msg *whaleswapv1.MsgFinalizeLiquidation) (*whaleswapv1.MsgFinalizeLiquidationResponse, error) {
    // TODO: Not implemented
    return nil, status.Errorf(codes.Unimplemented, "not implemented")
}
```

**Replace With:**
```go
func (k Keeper) FinalizeLiquidation(ctx context.Context, msg *whaleswapv1.MsgFinalizeLiquidation) (*whaleswapv1.MsgFinalizeLiquidationResponse, error) {
    sdkCtx := sdk.UnwrapSDKContext(ctx)
    
    // Load position
    pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
    if err != nil {
        return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
    }
    if pos.User != msg.User {
        return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "not position owner")
    }
    if pos.PoolId != msg.PoolId {
        return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id mismatch")
    }
    
    // Load pool
    pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
    if err != nil {
        return nil, err
    }
    
    // Compute health status
    collateralValue := math.LegacyNewDecFromInt(math.NewIntFromString(pos.CollateralAmount))
    borrowed := math.NewIntFromString(pos.BorrowedAmount)
    rate, _ := k.GetInterestRateForDenom(ctx, &pool, pos.BorrowedDenom)
    
    // Calculate elapsed time
    elapsed := sdkCtx.BlockTime().Unix() - pos.BorrowTime.Unix()
    interest, _ := k.CalculateInterest(borrowed, rate, elapsed)
    debtWithInterest := math.LegacyNewDecFromInt(borrowed).Add(interest)
    
    // Check if still liquidatable
    cr := collateralValue.Quo(debtWithInterest)
    threshold := math.LegacyNewDecWithPrec(120, 2) // 1.2
    if cr.GTE(threshold) {
        return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "position no longer liquidatable")
    }
    
    // Verify liquidation was initialized at least 1 block ago
    if sdkCtx.BlockHeight() <= int64(pos.LiquidationInitializedBlockHeight) {
        return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "liquidation delay not passed")
    }
    
    // Calculate repayment needed
    repaymentNeeded := k.ComputeEffectiveRepayment(borrowed, interest)
    
    // Liquidator sends repayment
    liquidatorAddr, _ := k.addr(ctx, msg.Liquidator)
    if err := k.sendToModule(ctx, liquidatorAddr, sdk.NewCoins(sdk.NewCoin(pos.BorrowedDenom, repaymentNeeded))); err != nil {
        return nil, cosmossdkerrors.Wrap(err, "failed to transfer repayment from liquidator")
    }
    
    // Send collateral to liquidator
    collateral := sdk.NewCoin(pos.CollateralDenom, math.NewIntFromString(pos.CollateralAmount))
    if err := k.sendFromModule(ctx, liquidatorAddr, sdk.NewCoins(collateral)); err != nil {
        return nil, cosmossdkerrors.Wrap(err, "failed to send collateral to liquidator")
    }
    
    // Calculate pool loss (if any)
    poolLoss := math.LegacyZeroDec()
    if repaymentNeeded.GT(math.NewIntFromString(pos.CollateralAmount)) {
        diff := repaymentNeeded.Sub(math.NewIntFromString(pos.CollateralAmount))
        poolLoss = math.LegacyNewDecFromInt(diff)
    }
    
    // Emit event
    sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeverageLiquidationFinalized{
        PositionId:         pos.PositionId,
        User:               pos.User,
        Liquidator:         msg.Liquidator,
        CollateralReceived: collateral.Amount.String(),
        CollateralDenom:    collateral.Denom,
        RepaymentAmount:    repaymentNeeded.String(),
        AccruedInterest:    interest.String(),
        PoolLoss:           poolLoss.String(),
    })
    
    // Delete position
    if err := k.LeveragePositions.Remove(ctx, msg.PositionId); err != nil {
        return nil, cosmossdkerrors.Wrap(err, "failed to delete position")
    }
    
    return &whaleswapv1.MsgFinalizeLiquidationResponse{
        CollateralReceived: collateral.Amount.String(),
        CollateralDenom:    collateral.Denom,
        RepaymentAmount:    repaymentNeeded.String(),
        AccruedInterest:    interest.String(),
        PoolLoss:           poolLoss.String(),
    }, nil
}
```

**Why:** Spec requires liquidator to pay debt; current stub doesn't implement settlement

---

## ✅ Verification Checklist

After applying these 3 fixes:

- [ ] Both `OpenLongPosition` and `OpenShortPosition` check `leverage ≤ max_leverage_ratio`
- [ ] All 6 message handlers emit appropriate events
- [ ] `FinalizeLiquidation` validates CR, collects repayment, distributes collateral
- [ ] Code compiles: `make install`
- [ ] Ready for: `make proto-gen install`

---

## Next: Proto Generation

Once these fixes are applied and code compiles, proceed with:

```bash
cd /Users/user/dysonprotocol2
make proto-gen install
```

This will generate:
- `types/leverage.pb.go` (NEW)
- Updated `types/whaleswap.pb.go`, `types/tx.pb.go`, `types/query.pb.go`

Then continue to Phase 3 (Message Server Routing).
