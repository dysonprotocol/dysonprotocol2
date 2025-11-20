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

/**
 * FinalizeLiquidation (permissionless) completes leveraged position liquidation.
 *
 * Behavior:
 * - Permissionless liquidation: any `liquidator` may call this for any initialized
 *   liquidation.
 * - Accrues interest on borrowed amount using the snapshotted per-denom APR and
 *   elapsed seconds since borrow_time.
 * - Computes final repayment as principal + accrued interest.
 * - Liquidator sends repayment to module and receives all collateral.
 * - Updates pool accounting (repayment to reserves, subtract borrowed, accrue
 *   interest earned); pool does not incur losses in liquidation.
 * - Deletes the position and clears all state.
 *
 * Semantics:
 * - Block delay: requires at least 1 block to have passed since initialization.
 * - Settlement: full collateral goes to liquidator regardless of repayment amount;
 *   pool absorbs any shortfall as loss.
 * - Pool loss: when repayment > collateral, the difference is recorded as pool
 *   loss (may be 0).
 *
 * Validation:
 * - Position must exist with LIQUIDATION_STATUS_INITIALIZED.
 * - Block delay must have passed (current_height > initialized_height).
	 * - Position must have an interest_rate snapshot for the borrowed denom.
 * - Pool must exist.
 *
 * Emits:
 * - EventLeverageLiquidationFinalized (position_id, user, liquidator, pool_id,
 *   collateral_received, repayment_amount, accrued_interest).
 *
 * Returns:
 * - *whaleswapv1.MsgFinalizeLiquidationResponse with CollateralReceived,
 *   RepaymentAmount, and AccruedInterest.
 *
 * Errors are returned on validation failures or event emission failures;
 * no panics.
*/
func (k Keeper) FinalizeLiquidation(ctx context.Context, msg *whaleswapv1.MsgFinalizeLiquidation) (*whaleswapv1.MsgFinalizeLiquidationResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("FinalizeLiquidation: begin",
		"position_id", msg.PositionId,
		"liquidator", msg.Liquidator,
		"user", msg.User,
		"pool_id", msg.PoolId,
	)
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	if pos.Status == whaleswapv1.PositionStatus_POSITION_STATUS_CLOSED || pos.Status == whaleswapv1.PositionStatus_POSITION_STATUS_LIQUIDATED {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "position %d not active", msg.PositionId)
	}
	logger.Info("FinalizeLiquidation: loaded position",
		"pos_user", pos.User,
		"borrowed", pos.Borrowed.String(),
		"collateral", pos.Collateral.String(),
		"interest_rate", pos.InterestRate.String(),
		"updated_time", pos.UpdatedTime,
		"liquidation_status", pos.LiquidationStatus.String(),
	)

	if pos.LiquidationStatus != whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_INITIALIZED {
		return nil, cosmossdkerrors.Wrap(whaleswapv1.ErrPositionNotLiquidatable, "liquidation not initialized")
	}

	if !k.CanFinalizeLiquidationBefore(ctx, &pos) {
		return nil, cosmossdkerrors.Wrap(whaleswapv1.ErrBlockDelayNotPassed, "liquidation block delay not passed")
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	interestDec, interestCoin, err := k.SettleInterest(ctx, &pos)
	if err != nil {
		return nil, err
	}
	repayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interestDec)
	logger.Info("FinalizeLiquidation: computed",
		"interest", interestDec.String(),
		"repayment", repayment.String(),
	)

	// Liquidator sends repayment to module
	liquidatorAddr, err := k.addr(ctx, msg.Liquidator)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, "invalid liquidator address")
	}
	repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, repayment)
	// Log module balance before collecting repayment
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	beforeRepayBal := k.bank.GetBalance(ctx, moduleAddr, pos.Borrowed.Denom).Amount
	logger.Info("FinalizeLiquidation: collect repayment",
		"from", liquidatorAddr.String(),
		"coin", repaymentCoin.String(),
		"module_before", beforeRepayBal.String(),
	)
	if err := k.sendToModule(ctx, liquidatorAddr, sdk.NewCoins(repaymentCoin)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to collect repayment from liquidator")
	}
	afterRepayBal := k.bank.GetBalance(ctx, moduleAddr, pos.Borrowed.Denom).Amount
	logger.Info("FinalizeLiquidation: collected repayment",
		"module_after", afterRepayBal.String(),
	)

	collateralSent := pos.Collateral

	// Send all collateral to liquidator
	// Log module balance before sending collateral out
	beforeCollBal := k.bank.GetBalance(ctx, moduleAddr, pos.Collateral.Denom).Amount
	logger.Info("FinalizeLiquidation: send collateral",
		"to", liquidatorAddr.String(),
		"collateral", pos.Collateral.String(),
		"module_before", beforeCollBal.String(),
	)
	if err := k.sendFromModule(ctx, liquidatorAddr, sdk.NewCoins(pos.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to send collateral to liquidator")
	}
	afterCollBal := k.bank.GetBalance(ctx, moduleAddr, pos.Collateral.Denom).Amount
	logger.Info("FinalizeLiquidation: collateral sent",
		"module_after", afterCollBal.String(),
	)

	// Update pool: add repayment to reserves, update borrowed, track interest
	pool.Coins = pool.Coins.Add(repaymentCoin)
	totalBorrowed, hasNeg := sdk.NewCoins(pool.TotalBorrowed...).SafeSub(pos.Borrowed)
	if hasNeg {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"pool total borrowed %s would be negative after subtracting position borrowed %s",
			sdk.NewCoins(pool.TotalBorrowed...).String(),
			pos.Borrowed.String(),
		)
	}
	beforePoolBorrowed := sdk.NewCoins(pool.TotalBorrowed...)
	pool.TotalBorrowed = totalBorrowed
	pool.InterestEarned = sdk.NewCoins(pool.InterestEarned...).Add(interestCoin)
	if err := k.PoolsMap.Set(ctx, pos.PoolId, pool); err != nil {
		return nil, err
	}
	logger.Info("FinalizeLiquidation: pool updated",
		"pool_id", pos.PoolId,
		"borrowed_before", beforePoolBorrowed.String(),
		"borrowed_after", pool.TotalBorrowed.String(),
		"added_to_reserve", repaymentCoin.String(),
		"interest_earned_added", interestCoin.String(),
		"pool_reserves", sdk.NewCoins(pool.Coins...).String(),
	)

	prevStatus := pos.Status
	pos.Status = whaleswapv1.PositionStatus_POSITION_STATUS_LIQUIDATED
	pos.LiquidationStatus = whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE
	pos.LiquidationInitializedBlockHeight = 0
	pos.Borrowed = sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt())
	pos.AccruedInterest = sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt())
	resetInterestRemainderIfNoDebt(&pos)
	if err := k.savePosition(ctx, pos, prevStatus); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to persist position status")
	}
	logger.Info("FinalizeLiquidation: position marked liquidated", "position_id", msg.PositionId)

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeverageLiquidationFinalized{
		PositionId:         msg.PositionId,
		User:               pos.User,
		Liquidator:         msg.Liquidator,
		PoolId:             pos.PoolId,
		CollateralReceived: collateralSent,
		RepaymentAmount:    repaymentCoin,
		AccruedInterest:    interestCoin,
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}
	logger.Info("FinalizeLiquidation: event emitted",
		"position_id", msg.PositionId,
		"repayment", repaymentCoin.String(),
		"interest", interestCoin.String(),
	)

	// Update address metrics
	if err := k.incrementLiquidation(ctx, pos.User, interestCoin); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update liquidation metrics")
	}

	resp := &whaleswapv1.MsgFinalizeLiquidationResponse{
		CollateralReceived: collateralSent,
		RepaymentAmount:    repaymentCoin,
		AccruedInterest:    interestCoin,
	}
	logger.Info("FinalizeLiquidation: complete", "response", resp)
	return resp, nil
}
