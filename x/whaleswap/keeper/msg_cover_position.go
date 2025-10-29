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

// CoverPosition lets a user repay accrued interest (must be fully covered) and optionally
// reduce principal. If payment >= principal+interest, the position is auto-closed,
// held is unwound via a swap, collateral is returned, and any overpay is refunded.
func (k Keeper) CoverPosition(ctx context.Context, msg *whaleswapv1.MsgCoverPosition) (*whaleswapv1.MsgCoverPositionResponse, error) {
	if msg == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "message cannot be nil")
	}

	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	if pos.BorrowTime == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid position: missing borrow_time")
	}
	if pos.User != msg.User {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "not position owner")
	}
	if !msg.Payment.IsValid() || !msg.Payment.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid payment")
	}
	if msg.Payment.Denom != pos.Borrowed.Denom {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "payment denom must match borrowed denom")
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	// Interest using position snapshot rate
	if len(pos.InterestRate) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "position interest_rate must have exactly 2 entries")
	}
	rate := pos.InterestRate.AmountOf(pos.Borrowed.Denom)
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("CoverPosition starting", "position_id", msg.PositionId, "user", msg.User, "payment", msg.Payment.String(), "pool_id", pos.PoolId, "borrowed", pos.Borrowed.String(), "held", pos.Held.String(), "collateral", pos.Collateral.String())
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interestDec, ierr := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
	if ierr != nil {
		return nil, ierr
	}
	interestInt := interestDec.TruncateInt()
	totalRepayment := pos.Borrowed.Amount.Add(interestInt)
	logger.Info("CoverPosition interest computed", "elapsed_sec", int64(elapsed), "rate", rate.String(), "interest", interestInt.String(), "total_repayment", totalRepayment.String())

	// Require full interest coverage
	if msg.Payment.Amount.LT(interestInt) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "payment %s less than accrued interest %s", msg.Payment.Amount, interestInt)
	}

	userAddr, aerr := k.addr(ctx, msg.User)
	if aerr != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, aerr.Error())
	}

	// Overpay (or exact) → auto-close (respect block delay like ClosePosition)
	if msg.Payment.Amount.GTE(totalRepayment) {
		logger.Info("CoverPosition entering auto-close path")
		if !k.CanCloseBefore(ctx, &pos) {
			blocks := k.BlocksUntilCloseable(ctx, &pos)
			return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrBlockDelayNotPassed, "position locked for %d more blocks", blocks)
		}
		borrowVault := k.leverageBorrowVaultBech(ctx)

		// Unwind held → borrowed via pool swap from the borrow vault
		mt := &whaleswapv1.MsgMakeTrade{
			Trader:    borrowVault,
			MaxInput:  sdk.NewCoins(pos.Held),
			MinOutput: sdk.NewCoins(),
			Operations: []whaleswapv1.TradeOperation{
				{Op: &whaleswapv1.TradeOperation_Swap{Swap: &whaleswapv1.SwapLeg{PoolId: pos.PoolId, SwapIn: pos.Held}}},
			},
			Note: "leverage-cover-close",
		}
		logger.Info("CoverPosition invoking MakeTrade to unwind held", "borrow_vault", borrowVault, "swap_in", pos.Held.String())
		mtResp, mtErr := k.MakeTrade(ctx, mt)
		if mtErr != nil {
			return nil, cosmossdkerrors.Wrap(mtErr, "failed MakeTrade for cover close")
		}
		proceedsBorrow := mtResp.TraderOutputs.AmountOf(pos.Borrowed.Denom)
		if !proceedsBorrow.IsPositive() {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "cover close swap produced no %s output", pos.Borrowed.Denom)
		}
		logger.Info("CoverPosition unwind complete", "proceeds_borrow", proceedsBorrow.String(), "borrow_denom", pos.Borrowed.Denom)

		// Move swap proceeds from borrow vault → module (so module can refund/send to user)
		proceedsCoin := sdk.NewCoin(pos.Borrowed.Denom, proceedsBorrow)
		if err := k.moveModuleToModule(ctx, whaleswap.LeverageBorrowVaultModuleName, whaleswap.ModuleName, sdk.NewCoins(proceedsCoin)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to transfer proceeds to module")
		}
		logger.Info("CoverPosition moved proceeds from borrow vault to module", "proceeds", proceedsCoin.String())

		// Determine repayment split: first use swap proceeds, then user's payment for any remainder.
		var needFromPayment math.Int
		if proceedsBorrow.GTE(totalRepayment) {
			needFromPayment = math.ZeroInt()
		} else {
			needFromPayment = totalRepayment.Sub(proceedsBorrow)
		}
		logger.Info("CoverPosition repayment split", "needed_from_payment", needFromPayment.String(), "from_proceeds", proceedsBorrow.String(), "total_repayment", totalRepayment.String())
		// Collect only the required portion of the user's payment (defer until after MakeTrade to avoid mid-trade invariant mismatches)
		if needFromPayment.IsPositive() {
			if err := k.sendToModule(ctx, userAddr, sdk.NewCoins(sdk.NewCoin(msg.Payment.Denom, needFromPayment))); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to transfer required payment to module")
			}
			logger.Info("CoverPosition collected required payment from user", "amount", needFromPayment.String(), "denom", msg.Payment.Denom)
		}

		// Add repayment to pool reserves and accounting
		// Reload pool from store to avoid overwriting reserves mutated by MakeTrade
		freshPool, gerr := k.PoolsMap.Get(ctx, pos.PoolId)
		if gerr != nil {
			return nil, cosmossdkerrors.Wrapf(gerr, "pool %d not found after unwind", pos.PoolId)
		}
		pool = freshPool
		repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, totalRepayment)
		pool.Coins = pool.Coins.Add(repaymentCoin)
		totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(pos.Borrowed)
		pool.TotalBorrowed = totalBorrowed
		pool.InterestEarned = sdk.NewCoins(pool.InterestEarned...).Add(sdk.NewCoin(pos.Borrowed.Denom, interestInt))
		if err := k.updatePool(ctx, &pool); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to update pool")
		}
		logger.Info("CoverPosition updated pool after close", "added_to_reserve", repaymentCoin.String(), "new_total_borrowed", sdk.NewCoins(pool.TotalBorrowed...).String(), "interest_earned_added", interestInt.String(), "pool_reserves", sdk.NewCoins(pool.Coins...).String())

		// Refund any unused portion of the user's payment
		refundAmt := msg.Payment.Amount.Sub(needFromPayment)
		var refund sdk.Coin
		if refundAmt.IsPositive() {
			// We only collected needFromPayment from user, so the unused portion remains in the user's account.
			// Report it as refund in the response event without moving coins from the module.
			refund = sdk.NewCoin(pos.Borrowed.Denom, refundAmt)
			logger.Info("CoverPosition refund (unused user payment)", "refund", refund.String())
		} else {
			refund = sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt())
		}

		// Profit is any proceeds remaining after covering the total repayment
		profitAmt := math.ZeroInt()
		if proceedsBorrow.GT(totalRepayment) {
			profitAmt = proceedsBorrow.Sub(totalRepayment)
		}
		profit := sdk.NewCoin(pos.Borrowed.Denom, profitAmt)
		if profit.Amount.IsPositive() {
			if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(profit)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to send profit")
			}
			logger.Info("CoverPosition sent profit from proceeds", "profit", profit.String())
		}

		// Return full collateral to user
		if pos.Collateral.Amount.IsPositive() {
			if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(pos.Collateral)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to return collateral")
			}
			logger.Info("CoverPosition returned collateral", "collateral", pos.Collateral.String())
		}

		// Delete position
		if err := k.LeveragePositions.Remove(ctx, msg.PositionId); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to delete position")
		}
		logger.Info("CoverPosition deleted position", "position_id", msg.PositionId)

		// Emit events: covered (closed=true) and closed
		newCR := math.LegacyZeroDec()
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionCovered{
			PositionId:         msg.PositionId,
			User:               msg.User,
			PoolId:             pos.PoolId,
			InterestPaid:       sdk.NewCoin(pos.Borrowed.Denom, interestInt),
			PrincipalPaid:      pos.Borrowed,
			NewCollateralRatio: newCR.String(),
			Closed:             true,
			Refunded:           refund,
			Profit:             profit,
		}); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to emit cover event")
		}
		// Also emit standard close event for observability
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionClosed{
			PositionId:      msg.PositionId,
			User:            msg.User,
			PoolId:          pos.PoolId,
			Profit:          profit,
			AccruedInterest: sdk.NewCoin(pos.Borrowed.Denom, interestInt),
		}); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to emit close event")
		}

		// Invariants
		if err := k.AssertAMMInvariants(ctx); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "AMM invariant after CoverPosition close")
		}
		if err := k.AssertInvariants(ctx); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "invariant after CoverPosition close")
		}
		logger.Info("CoverPosition close invariants passed")

		return &whaleswapv1.MsgCoverPositionResponse{
			InterestPaid:       sdk.NewCoin(pos.Borrowed.Denom, interestInt),
			PrincipalPaid:      pos.Borrowed,
			NewBorrowed:        sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt()),
			NewCollateralRatio: newCR,
			Closed:             true,
			Refunded:           refund,
			Profit:             profit,
		}, nil
	}

	// Partial cover: pay all interest; remainder reduces principal; keep open
	// Transfer payment to module now (no block-delay requirement)
	if err := k.sendToModule(ctx, userAddr, sdk.NewCoins(msg.Payment)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to transfer payment to module")
	}

	principalPaid := msg.Payment.Amount.Sub(interestInt)
	logger.Info("CoverPosition partial cover", "payment", msg.Payment.String(), "interest_paid", interestInt.String(), "principal_paid", principalPaid.String())

	// Update pool reserves/accounting: add interest+principal payments
	addCoin := sdk.NewCoin(pos.Borrowed.Denom, msg.Payment.Amount)
	pool.Coins = pool.Coins.Add(addCoin)
	pool.InterestEarned = sdk.NewCoins(pool.InterestEarned...).Add(sdk.NewCoin(pos.Borrowed.Denom, interestInt))
	if principalPaid.IsPositive() {
		pool.TotalBorrowed = sdk.NewCoins(pool.TotalBorrowed...).Sub(sdk.NewCoin(pos.Borrowed.Denom, principalPaid))
	}
	if err := k.updatePool(ctx, &pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool")
	}
	logger.Info("CoverPosition updated pool after partial cover", "added_to_reserve", addCoin.String(), "principal_reduction", principalPaid.String(), "new_total_borrowed", sdk.NewCoins(pool.TotalBorrowed...).String(), "interest_earned_added", interestInt.String(), "pool_reserves", sdk.NewCoins(pool.Coins...).String())

	// Update position: reduce principal, reset borrow_time, clear liquidation (like AddCollateral)
	newPrincipal := pos.Borrowed.Amount.Sub(principalPaid)
	pos.Borrowed = sdk.NewCoin(pos.Borrowed.Denom, newPrincipal)
	now := sdkCtx.BlockTime()
	pos.BorrowTime = &now
	k.ClearLiquidationPending(&pos)
	if err := k.LeveragePositions.Set(ctx, msg.PositionId, pos); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update position")
	}
	logger.Info("CoverPosition updated position after partial cover", "new_borrowed", pos.Borrowed.String(), "borrow_time", now)

	// Compute new collateral ratio based on current pool price
	borrowDenom := pos.Borrowed.Denom
	heldDenom, derr := k.getOtherDenom(&pool, borrowDenom)
	if derr != nil {
		return nil, cosmossdkerrors.Wrap(derr, "failed to derive held denom")
	}
	borrowPoolAmt := pool.Coins.AmountOf(borrowDenom)
	heldPoolAmt := pool.Coins.AmountOf(heldDenom)
	if !borrowPoolAmt.IsPositive() || !heldPoolAmt.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves for CR computation")
	}
	priceHeldPerBorrow := math.LegacyNewDecFromInt(heldPoolAmt).Quo(math.LegacyNewDecFromInt(borrowPoolAmt))
	collateralValueInBorrow := math.LegacyNewDecFromInt(pos.Collateral.Amount)
	if pos.Collateral.Denom == heldDenom {
		collateralValueInBorrow = collateralValueInBorrow.Quo(priceHeldPerBorrow)
	}
	// newPrincipal is non-negative; when zero, CR is undefined for debt=0; return zero
	var newCR math.LegacyDec
	if newPrincipal.IsZero() {
		newCR = math.LegacyZeroDec()
	} else {
		newCR = collateralValueInBorrow.Quo(math.LegacyNewDecFromInt(newPrincipal))
	}
	logger.Info("CoverPosition computed new CR", "borrow_pool", borrowPoolAmt.String(), "held_pool", heldPoolAmt.String(), "price_held_per_borrow", priceHeldPerBorrow.String(), "collateral_value_in_borrow", collateralValueInBorrow.String(), "new_cr", newCR.String())

	// Emit cover event (closed = false)
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionCovered{
		PositionId:         msg.PositionId,
		User:               msg.User,
		PoolId:             pos.PoolId,
		InterestPaid:       sdk.NewCoin(pos.Borrowed.Denom, interestInt),
		PrincipalPaid:      sdk.NewCoin(pos.Borrowed.Denom, principalPaid),
		NewCollateralRatio: newCR.String(),
		Closed:             false,
		Refunded:           sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt()),
		Profit:             sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt()),
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit cover event")
	}

	// Invariants
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AMM invariant after CoverPosition")
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after CoverPosition")
	}
	logger.Info("CoverPosition partial-cover invariants passed")

	return &whaleswapv1.MsgCoverPositionResponse{
		InterestPaid:       sdk.NewCoin(pos.Borrowed.Denom, interestInt),
		PrincipalPaid:      sdk.NewCoin(pos.Borrowed.Denom, principalPaid),
		NewBorrowed:        pos.Borrowed,
		NewCollateralRatio: newCR,
		Closed:             false,
		Refunded:           sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt()),
		Profit:             sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt()),
	}, nil
}
