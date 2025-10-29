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

// FinalizeLiquidation completes position liquidation.
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
	logger.Info("FinalizeLiquidation: loaded position",
		"pos_user", pos.User,
		"borrowed", pos.Borrowed.String(),
		"collateral", pos.Collateral.String(),
		"interest_rate", pos.InterestRate.String(),
		"borrow_time", pos.BorrowTime,
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

	// Calculate final repayment using per-position snapshot rate; must be set (len 2)
	if len(pos.InterestRate) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "position interest_rate must have exactly 2 entries")
	}
	rate := pos.InterestRate.AmountOf(pos.Borrowed.Denom)
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, _ := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
	repayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)
	logger.Info("FinalizeLiquidation: computed",
		"elapsed_sec", int64(elapsed),
		"interest", interest.String(),
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

	// Pool loss if collateral < repayment
	poolLossInt := repayment.Sub(pos.Collateral.Amount)
	if poolLossInt.IsNegative() {
		poolLossInt = math.ZeroInt()
	}
	poolLossCoin := sdk.NewCoin(pos.Borrowed.Denom, poolLossInt)
	interestCoin := sdk.NewCoin(pos.Borrowed.Denom, interest.TruncateInt())

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
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(pos.Borrowed)
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

	// Delete position
	if err := k.LeveragePositions.Remove(ctx, msg.PositionId); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to delete position")
	}
	logger.Info("FinalizeLiquidation: position removed", "position_id", msg.PositionId)

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeverageLiquidationFinalized{
		PositionId:         msg.PositionId,
		User:               pos.User,
		Liquidator:         msg.Liquidator,
		PoolId:             pos.PoolId,
		CollateralReceived: pos.Collateral,
		RepaymentAmount:    repaymentCoin,
		AccruedInterest:    interestCoin,
		PoolLoss:           poolLossCoin,
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}
	logger.Info("FinalizeLiquidation: event emitted",
		"position_id", msg.PositionId,
		"repayment", repaymentCoin.String(),
		"interest", interestCoin.String(),
		"pool_loss", poolLossCoin.String(),
	)

	resp := &whaleswapv1.MsgFinalizeLiquidationResponse{
		CollateralReceived: pos.Collateral,
		RepaymentAmount:    repaymentCoin,
		AccruedInterest:    interestCoin,
		PoolLoss:           poolLossCoin,
	}
	logger.Info("FinalizeLiquidation: complete", "response", resp)
	return resp, nil
}
