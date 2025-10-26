package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// ClosePosition closes an open leveraged position and settles collateral/profit.
func (k Keeper) ClosePosition(ctx context.Context, msg *whaleswapv1.MsgClosePosition) (*whaleswapv1.MsgClosePositionResponse, error) {
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	if pos.User != msg.User {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "not position owner")
	}
	if !k.CanCloseBefore(ctx, &pos) {
		blocks := k.BlocksUntilCloseable(ctx, &pos)
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrBlockDelayNotPassed, "position locked for %d more blocks", blocks)
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	// Calculate interest
	rate, err := k.GetInterestRateForDenom(ctx, &pool, pos.Borrowed.Denom)
	if err != nil {
		return nil, err
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, err := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
	if err != nil {
		return nil, err
	}

	// Return collateral and profit to user; pool receives repayment
	userAddr, err := k.addr(ctx, msg.User)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}

	// Profit = held value minus borrowed amount (simplified; actual swap/settlement omitted)
	profit := pos.Held
	repayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)

	// Return collateral to user
	if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(pos.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to return collateral")
	}

	// Return profit to user (if positive)
	if profit.Amount.IsPositive() {
		if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(profit)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to return profit")
		}
	}

	// Update pool: decrease total_borrowed and add interest earned
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(pos.Borrowed)
	pool.TotalBorrowed = totalBorrowed
	interestEarned := sdk.NewCoins(pool.InterestEarned...).Add(sdk.NewCoin(pos.Borrowed.Denom, repayment))
	pool.InterestEarned = interestEarned
	if err := k.PoolsMap.Set(ctx, pos.PoolId, pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool")
	}

	// Delete position
	if err := k.LeveragePositions.Remove(ctx, msg.PositionId); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to delete position")
	}

	// Emit event
	interestCoin := sdk.NewCoin(pos.Borrowed.Denom, interest.TruncateInt())
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionClosed{
		PositionId:      msg.PositionId,
		User:            msg.User,
		PoolId:          pos.PoolId,
		Profit:          profit,
		AccruedInterest: interestCoin,
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return &whaleswapv1.MsgClosePositionResponse{
		Profit:          profit,
		AccruedInterest: interestCoin,
	}, nil
}

// InitializeLiquidation marks a position for liquidation.
func (k Keeper) InitializeLiquidation(ctx context.Context, msg *whaleswapv1.MsgInitializeLiquidation) (*whaleswapv1.MsgInitializeLiquidationResponse, error) {
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	// Calculate CR
	rate, _ := k.GetInterestRateForDenom(ctx, &pool, pos.Borrowed.Denom)
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, _ := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))

	collateralValue := math.LegacyNewDecFromInt(pos.Collateral.Amount)
	debtValue := math.LegacyNewDecFromInt(pos.Borrowed.Amount).Add(interest)
	cr, _ := k.ComputeCollateralRatio(collateralValue, debtValue)

	// Use pool-specific liquidation threshold
	liquidationThreshold := math.LegacyMustNewDecFromStr("1.2")
	if pool.LiquidationThreshold != "" {
		parsed, err := math.LegacyNewDecFromStr(pool.LiquidationThreshold)
		if err == nil {
			liquidationThreshold = parsed
		}
	}

	if err := k.InitializeLiquidationInternal(ctx, &pos); err != nil {
		return nil, err
	}
	if err := k.LeveragePositions.Set(ctx, msg.PositionId, pos); err != nil {
		return nil, err
	}

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeverageLiquidationInitialized{
		PositionId:           msg.PositionId,
		User:                 pos.User,
		PoolId:               pos.PoolId,
		CollateralRatio:      cr.String(),
		LiquidationThreshold: liquidationThreshold.String(),
		BlockHeight:          uint64(sdkCtx.BlockHeight()),
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return &whaleswapv1.MsgInitializeLiquidationResponse{
		CollateralRatio:      cr,
		LiquidationThreshold: liquidationThreshold,
	}, nil
}

// FinalizeLiquidation completes position liquidation.
func (k Keeper) FinalizeLiquidation(ctx context.Context, msg *whaleswapv1.MsgFinalizeLiquidation) (*whaleswapv1.MsgFinalizeLiquidationResponse, error) {
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}

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

	// Calculate final repayment
	rate, _ := k.GetInterestRateForDenom(ctx, &pool, pos.Borrowed.Denom)
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, _ := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
	repayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)

	// Liquidator sends repayment to module
	liquidatorAddr, err := k.addr(ctx, msg.Liquidator)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, "invalid liquidator address")
	}
	repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, repayment)
	if err := k.sendToModule(ctx, liquidatorAddr, sdk.NewCoins(repaymentCoin)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to collect repayment from liquidator")
	}

	// Pool loss if collateral < repayment
	poolLossInt := repayment.Sub(pos.Collateral.Amount)
	if poolLossInt.IsNegative() {
		poolLossInt = math.ZeroInt()
	}
	poolLossCoin := sdk.NewCoin(pos.Borrowed.Denom, poolLossInt)
	interestCoin := sdk.NewCoin(pos.Borrowed.Denom, interest.TruncateInt())

	// Send all collateral to liquidator
	if err := k.sendFromModule(ctx, liquidatorAddr, sdk.NewCoins(pos.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to send collateral to liquidator")
	}

	// Update pool
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(pos.Borrowed)
	pool.TotalBorrowed = totalBorrowed
	pool.InterestEarned = sdk.NewCoins(pool.InterestEarned...).Add(
		sdk.NewCoin(pos.Borrowed.Denom, repayment),
	)
	if err := k.PoolsMap.Set(ctx, pos.PoolId, pool); err != nil {
		return nil, err
	}

	// Delete position
	if err := k.LeveragePositions.Remove(ctx, msg.PositionId); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to delete position")
	}

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

	return &whaleswapv1.MsgFinalizeLiquidationResponse{
		CollateralReceived: pos.Collateral,
		RepaymentAmount:    repaymentCoin,
		AccruedInterest:    interestCoin,
		PoolLoss:           poolLossCoin,
	}, nil
}
