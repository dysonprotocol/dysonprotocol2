package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

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
