package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

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
