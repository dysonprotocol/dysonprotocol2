package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// ClosePosition closes a leveraged position by swapping held assets back to the
// borrowed denomination, repaying principal plus accrued interest, and returning
// any remaining collateral and profit to the user.
//
// Semantics:
//   - Inputs: the position ID and user address; the caller must be the position owner.
//   - Price impact: swaps are executed via MakeTrade through the borrow vault.
//   - Interest: calculated from the per-position interest rate and elapsed time.
//   - Settlement: pool reserves are restored by the full repayment; the position is deleted.
//   - Invariants: AMM and module-wide invariants are asserted after state updates.
//
// Returns:
//   - (*whaleswapv1.MsgClosePositionResponse, error). On success, InterestPaid and
//     PrincipalPaid reflect the repayment and Profit is any excess returned to the user.
//
// Emits:
//   - EventLeveragePositionClosed on successful close
//
// Errors are returned on validation or invariant violations; no panics.
func (k Keeper) ClosePosition(ctx context.Context, msg *whaleswapv1.MsgClosePosition) (*whaleswapv1.MsgClosePositionResponse, error) {
	if msg == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "message cannot be nil")
	}

	// Validate fraction
	fraction := msg.Fraction
	oneDec := math.LegacyOneDec()
	if fraction.IsNegative() || fraction.IsZero() || fraction.GT(oneDec) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "fraction must satisfy 0 < fraction <= 1")
	}
	isPartialClose := !fraction.Equal(oneDec)

	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	// Check for invalid position data before ownership to avoid panics
	if pos.UpdatedTime == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid position: missing updated_time")
	}
	// Ownership check must return before any further logic to avoid side effects or nil derefs
	if pos.User != msg.User {
		// Use a stable message that includes the substring expected by tests
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "unauthorized: not position owner")
	}
	if !k.CanCloseBefore(ctx, &pos) {
		blocks := k.BlocksUntilCloseable(ctx, &pos)
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrBlockDelayNotPassed, "position locked for %d more blocks", blocks)
	}
	if pos.Status == whaleswapv1.PositionStatus_POSITION_STATUS_CLOSED || pos.Status == whaleswapv1.PositionStatus_POSITION_STATUS_LIQUIDATED {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "position %d not active", msg.PositionId)
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)
	_, interestCoin, err := k.SettleInterest(ctx, &pos)
	if err != nil {
		return nil, err
	}

	// Return collateral and profit to user; pool receives repayment
	userAddr, err := k.addr(ctx, msg.User)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}

	// Calculate amounts for partial/full close
	// For partial close: calculate what REMAINS to avoid rounding accumulation
	// Any rounding error favors the pool (user gets slightly less)
	var (
		principalToRepay   sdk.Coin
		interestToRepay    sdk.Coin
		heldToSwap         sdk.Coin
		collateralToReturn sdk.Coin
	)

	if isPartialClose {
		// Calculate remaining amounts (what stays in position)
		remainingFraction := math.LegacyOneDec().Sub(fraction)
		principalRemainingAmt := remainingFraction.MulInt(pos.Borrowed.Amount).TruncateInt()
		interestRemainingAmt := remainingFraction.MulInt(interestCoin.Amount).TruncateInt()
		heldRemainingAmt := remainingFraction.MulInt(pos.Held.Amount).TruncateInt()
		collateralRemainingAmt := remainingFraction.MulInt(pos.Collateral.Amount).TruncateInt()

		// Validate that partial close won't create inconsistent state
		// If any critical field would be fully closed due to rounding, reject partial close
		if principalRemainingAmt.IsZero() && pos.Borrowed.IsPositive() {
			return nil, cosmossdkerrors.Wrap(
				sdkerrors.ErrInvalidRequest,
				"partial close would round principal to zero; use fraction=1 for full close",
			)
		}
		if heldRemainingAmt.IsZero() && pos.Held.IsPositive() {
			return nil, cosmossdkerrors.Wrap(
				sdkerrors.ErrInvalidRequest,
				"partial close would round held to zero; use fraction=1 for full close",
			)
		}
		if collateralRemainingAmt.IsZero() && pos.Collateral.IsPositive() {
			return nil, cosmossdkerrors.Wrap(
				sdkerrors.ErrInvalidRequest,
				"partial close would round collateral to zero; use fraction=1 for full close",
			)
		}

		// Amount to close = total - remaining (captures any rounding dust)
		principalRemainingCoin := sdk.NewCoin(pos.Borrowed.Denom, principalRemainingAmt)
		interestRemainingCoin := sdk.NewCoin(interestCoin.Denom, interestRemainingAmt)
		heldRemainingCoin := sdk.NewCoin(pos.Held.Denom, heldRemainingAmt)
		collateralRemainingCoin := sdk.NewCoin(pos.Collateral.Denom, collateralRemainingAmt)

		principalToRepay = pos.Borrowed.Sub(principalRemainingCoin)
		interestToRepay = interestCoin.Sub(interestRemainingCoin)
		heldToSwap = pos.Held.Sub(heldRemainingCoin)
		collateralToReturn = pos.Collateral.Sub(collateralRemainingCoin)

		// Validate that remaining position would still be healthy
		// Total debt = borrowed + accrued interest (after settling current interest and paying partial)
		totalRemainingDebtCoin := principalRemainingCoin.Add(interestRemainingCoin)
		if totalRemainingDebtCoin.IsPositive() {
			collateralForRatio := sdk.NewCoin(pos.Borrowed.Denom, collateralRemainingCoin.Amount)
			if _, err := k.ensureHealthyCollateralRatio(&pos, collateralForRatio, totalRemainingDebtCoin); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "partial close would leave position unhealthy")
			}
		}
	} else {
		principalToRepay = pos.Borrowed
		interestToRepay = interestCoin
		heldToSwap = pos.Held
		collateralToReturn = pos.Collateral
	}

	requiredRepayment := principalToRepay.Add(interestToRepay)

	// Swap held back to borrowed denom via MakeTrade using the borrow vault as trader
	borrowVault := k.leverageBorrowVaultBech(ctx)
	originalStatus := pos.Status
	mt := &whaleswapv1.MsgMakeTrade{
		Trader:    borrowVault,
		MaxInput:  sdk.NewCoins(heldToSwap),
		MinOutput: sdk.NewCoins(),
		Operations: []whaleswapv1.TradeOperation{
			{Op: &whaleswapv1.TradeOperation_Swap{Swap: &whaleswapv1.SwapLeg{PoolId: pos.PoolId, SwapIn: heldToSwap}}},
		},
		Note: msg.Note,
	}
	mtResp, mtErr := k.MakeTrade(ctx, mt)
	if mtErr != nil {
		return nil, cosmossdkerrors.Wrap(mtErr, "failed leverage close MakeTrade")
	}
	pos.TradeIds = append(pos.TradeIds, mtResp.TradeId)
	proceedsCoin := sdk.NewCoin(pos.Borrowed.Denom, mtResp.TraderOutputs.AmountOf(pos.Borrowed.Denom))
	if !proceedsCoin.IsPositive() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "close swap produced no %s output", pos.Borrowed.Denom)
	}

	// Determine funds available to cover repayment (after all swaps and fees)
	var collateralUsed sdk.Coin
	var collateralSwapped bool
	var totalProceeds sdk.Coin // Total funds in vault (for cross-denom case)
	var profit sdk.Coin
	var loss sdk.Coin
	collateralReturned := sdk.NewCoin(pos.Collateral.Denom, math.ZeroInt())

	if proceedsCoin.IsGTE(requiredRepayment) {
		// Profitable: proceeds alone cover full repayment
		// User gets: all collateral back + profit from proceeds
		collateralUsed = sdk.NewCoin(pos.Collateral.Denom, math.ZeroInt())
		collateralSwapped = false
		totalProceeds = proceedsCoin
		profit = proceedsCoin.Sub(requiredRepayment)
	} else {
		// Underwater: proceeds insufficient, need to use collateral
		// User gets: remaining collateral (if any), NO profit
		shortfallCoin := requiredRepayment.Sub(proceedsCoin)
		loss = shortfallCoin

		if pos.Collateral.Denom == pos.Borrowed.Denom {
			// Same denom: collateral can directly cover shortfall
			if collateralToReturn.IsLT(shortfallCoin) {
				// Insufficient: reject transaction to prevent pool loss
				return nil, cosmossdkerrors.Wrapf(
					whaleswapv1.ErrInsufficientCollateral,
					"position underwater: proceeds=%s + collateral=%s < repayment=%s (shortfall=%s)",
					proceedsCoin,
					collateralToReturn,
					requiredRepayment,
					shortfallCoin,
				)
			}
			// Collateral covers shortfall
			collateralUsed = shortfallCoin
			collateralSwapped = false
			totalProceeds = proceedsCoin
			profit = sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt())
		} else {
			// Cross-denom collateral: must swap to borrowed denom
			// Update position state first to avoid invariant violation
			pos.Collateral = pos.Collateral.Sub(collateralToReturn)
			if err := k.savePosition(ctx, pos, originalStatus); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to update position before collateral swap")
			}

			// Move collateral from module → borrow vault for swap
			if err := k.moveModuleToModule(ctx, whaleswap.ModuleName, whaleswap.LeverageBorrowVaultModuleName, sdk.NewCoins(collateralToReturn)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to move collateral to borrow vault for swap")
			}

			// Swap collateral to borrowed denom
			collateralSwapMt := &whaleswapv1.MsgMakeTrade{
				Trader:    borrowVault,
				MaxInput:  sdk.NewCoins(collateralToReturn),
				MinOutput: sdk.NewCoins(),
				Operations: []whaleswapv1.TradeOperation{
					{Op: &whaleswapv1.TradeOperation_Swap{
						Swap: &whaleswapv1.SwapLeg{
							PoolId: pos.PoolId,
							SwapIn: collateralToReturn,
						},
					}},
				},
				Note: msg.Note,
			}
			collSwapResp, collSwapErr := k.MakeTrade(ctx, collateralSwapMt)
			if collSwapErr != nil {
				return nil, cosmossdkerrors.Wrap(collSwapErr, "failed to swap collateral for shortfall coverage")
			}
			pos.TradeIds = append(pos.TradeIds, collSwapResp.TradeId)

			collateralProceedsCoin := sdk.NewCoin(pos.Borrowed.Denom, collSwapResp.TraderOutputs.AmountOf(pos.Borrowed.Denom))
			if !collateralProceedsCoin.IsPositive() {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "collateral swap produced no %s output", pos.Borrowed.Denom)
			}

			totalProceeds = proceedsCoin.Add(collateralProceedsCoin)

			// Critical check: reject if still underwater after swapping collateral
			if totalProceeds.IsLT(requiredRepayment) {
				return nil, cosmossdkerrors.Wrapf(
					whaleswapv1.ErrInsufficientCollateral,
					"position underwater after collateral swap: held_proceeds=%s + collateral_proceeds=%s < repayment=%s",
					proceedsCoin,
					collateralProceedsCoin,
					requiredRepayment,
				)
			}

			// Collateral was entirely swapped
			collateralUsed = collateralToReturn
			collateralSwapped = true
			// Calculate profit from total proceeds (may be positive if collateral swap yielded excess)
			profit = totalProceeds.Sub(requiredRepayment)
			if profit.IsPositive() {
				loss = sdk.Coin{}
			}

			sdkCtx.Logger().Info("ClosePosition: cross-denom collateral swap executed",
				"held_proceeds", proceedsCoin,
				"collateral_swapped", collateralToReturn,
				"collateral_proceeds", collateralProceedsCoin,
				"total_proceeds", totalProceeds,
				"repayment", requiredRepayment,
				"profit", profit)
		}
	}

	// Reload pool to get current state after MakeTrade(s)
	pool, err = k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to reload pool %d", pos.PoolId)
	}

	// Move swap proceeds from borrow vault to module and restore pool reserves
	// Important: funds must be in module BEFORE we add to pool.Coins for invariants
	if collateralSwapped {
		// Cross-denom case: both swaps executed in vault
		// Move all proceeds (held swap + collateral swap) to module
		if err := k.moveModuleToModule(ctx, whaleswap.LeverageBorrowVaultModuleName, whaleswap.ModuleName, sdk.NewCoins(totalProceeds)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to transfer proceeds to module")
		}

		// Restore pool reserves with full repayment (all funds now in module)
		pool.Coins = pool.Coins.Add(requiredRepayment)
		if err := k.updatePool(ctx, &pool); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to update pool after repayment")
		}

		// Return profit to user (excess over repayment, if any)
		if profit.IsPositive() {
			if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(profit)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to return profit")
			}
		}
	} else {
		// Same-denom case: swap proceeds in vault, collateral (if needed) already in module
		// Move swap proceeds from vault to module
		if err := k.moveModuleToModule(ctx, whaleswap.LeverageBorrowVaultModuleName, whaleswap.ModuleName, sdk.NewCoins(totalProceeds)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to transfer proceeds to module")
		}

		// Restore pool reserves with full repayment
		// repayment funded by: totalProceeds (just moved to module) + collateralUsed (already in module)
		pool.Coins = pool.Coins.Add(requiredRepayment)
		if err := k.updatePool(ctx, &pool); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to update pool after repayment")
		}

		// Return remaining collateral to user (amount not used for repayment)
		remainingCollateralCoin := collateralToReturn.Sub(collateralUsed)
		if remainingCollateralCoin.IsPositive() {
			if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(remainingCollateralCoin)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to return collateral")
			}
			collateralReturned = remainingCollateralCoin
		}

		// Return profit to user (only possible if proceeds >= repayment, meaning collateralUsed = 0)
		if profit.IsPositive() {
			if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(profit)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to return profit")
			}
		}
	}

	// Apply interest payment to position accounting
	actualInterestPaidCoin, actualPrincipalPaidCoin, err := k.ApplyInterestPayment(&pos, requiredRepayment)
	if err != nil {
		return nil, err
	}

	// Update position state after all fund movements
	pos.Borrowed = pos.Borrowed.Sub(actualPrincipalPaidCoin)
	pos.Held = pos.Held.Sub(heldToSwap)
	// Collateral already updated in cross-denom path; update here for same-denom path
	if !collateralSwapped {
		pos.Collateral = pos.Collateral.Sub(collateralToReturn)
	}
	resetInterestRemainderIfNoDebt(&pos)

	positionClosed := false
	if !isPartialClose {
		pos.Status = whaleswapv1.PositionStatus_POSITION_STATUS_CLOSED
		pos.LiquidationStatus = whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE
		pos.LiquidationInitializedBlockHeight = 0
		positionClosed = true
	}

	if err := k.savePosition(ctx, pos, originalStatus); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to persist position after close")
	}

	// Update pool accounting: decrease total_borrowed and add interest earned
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(principalToRepay)
	pool.TotalBorrowed = totalBorrowed
	pool.InterestEarned = sdk.NewCoins(pool.InterestEarned...).Add(interestToRepay)
	if err := k.PoolsMap.Set(ctx, pos.PoolId, pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool")
	}

	// Emit event
	if isPartialClose {
		// Calculate current collateral ratio
		collateralValue := math.LegacyNewDecFromInt(pos.Collateral.Amount)
		totalDebt := pos.Borrowed.Add(pos.AccruedInterest)
		remainder, remErr := getAccruedInterestRemainder(&pos)
		if remErr != nil {
			return nil, remErr
		}
		debtValue := math.LegacyNewDecFromInt(totalDebt.Amount).Add(remainder)
		currentCR := math.LegacyZeroDec()
		if !debtValue.IsZero() {
			currentCR, _ = k.ComputeCollateralRatio(collateralValue, debtValue)
		}

		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionPartiallyClosed{
			PositionId:         msg.PositionId,
			User:               msg.User,
			PoolId:             pos.PoolId,
			FractionClosed:     fraction.String(),
			InterestPaid:       actualInterestPaidCoin,
			PrincipalPaid:      actualPrincipalPaidCoin,
			CollateralReturned: collateralReturned,
			Profit:             profit,
			NewBorrowed:        pos.Borrowed,
			NewHeld:            pos.Held,
			NewCollateral:      pos.Collateral,
			NewCollateralRatio: currentCR.String(),
		}); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to emit partial close event")
		}
	} else {
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionClosed{
			PositionId:      msg.PositionId,
			User:            msg.User,
			PoolId:          pos.PoolId,
			Profit:          profit,
			AccruedInterest: actualInterestPaidCoin,
		}); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to emit full close event")
		}
	}

	// Invariants after settlement
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AMM invariant after ClosePosition")
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after ClosePosition")
	}

	// Update address metrics
	var metricsErr error
	if positionClosed {
		metricsErr = k.incrementPositionClosed(ctx, msg.User, actualInterestPaidCoin, profit, loss)
	} else {
		metricsErr = k.trackPartialCloseMetrics(ctx, msg.User, actualInterestPaidCoin, profit, loss)
	}
	if metricsErr != nil {
		return nil, cosmossdkerrors.Wrap(metricsErr, "failed to update position metrics")
	}

	// Calculate final collateral ratio
	collateralValue := math.LegacyNewDecFromInt(pos.Collateral.Amount)
	totalDebt := pos.Borrowed.Add(pos.AccruedInterest)
	remainder, remErr := getAccruedInterestRemainder(&pos)
	if remErr != nil {
		return nil, remErr
	}
	debtValue := math.LegacyNewDecFromInt(totalDebt.Amount).Add(remainder)
	finalCR := math.LegacyZeroDec()
	if !debtValue.IsZero() {
		finalCR, _ = k.ComputeCollateralRatio(collateralValue, debtValue)
	}

	return &whaleswapv1.MsgClosePositionResponse{
		InterestPaid:       actualInterestPaidCoin,
		PrincipalPaid:      actualPrincipalPaidCoin,
		CollateralReturned: collateralReturned,
		Profit:             profit,
		NewBorrowed:        pos.Borrowed,
		NewHeld:            pos.Held,
		NewCollateral:      pos.Collateral,
		NewCollateralRatio: finalCR,
		Closed:             positionClosed,
	}, nil
}
