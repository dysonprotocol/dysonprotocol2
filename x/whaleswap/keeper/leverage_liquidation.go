package keeper

import (
	"context"
	"fmt"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// ComputeHealthStatus evaluates position collateral ratio and returns health status.
func (k Keeper) ComputeHealthStatus(collateralValue, debtWithInterest math.LegacyDec) (whaleswapv1.PositionHealthStatus, error) {
	if debtWithInterest.IsZero() {
		return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_HEALTHY, nil
	}
	if debtWithInterest.IsNegative() {
		return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_UNSPECIFIED, fmt.Errorf("debt cannot be negative")
	}
	cr := collateralValue.Quo(debtWithInterest)
	thresholdHealthy := math.LegacyNewDecWithPrec(150, 2) // 1.5
	thresholdRisk := math.LegacyNewDecWithPrec(120, 2)    // 1.2
	if cr.GT(thresholdHealthy) {
		return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_HEALTHY, nil
	}
	if cr.GTE(thresholdRisk) {
		return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_AT_RISK, nil
	}
	return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_LIQUIDATABLE, nil
}

// IsPositionLiquidatable checks if CR < liquidation_threshold.
func (k Keeper) IsPositionLiquidatable(cr, threshold math.LegacyDec) bool {
	return cr.LT(threshold)
}

// ComputeCollateralRatio returns CR = collateral_value / debt_with_interest.
func (k Keeper) ComputeCollateralRatio(collateralValue, debtWithInterest math.LegacyDec) (math.LegacyDec, error) {
	if debtWithInterest.IsZero() {
		return math.LegacyDec{}, fmt.Errorf("debt_with_interest cannot be zero")
	}
	return collateralValue.Quo(debtWithInterest), nil
}

// InitializeLiquidationInternal records the liquidation start block.
func (k Keeper) InitializeLiquidationInternal(ctx context.Context, pos *whaleswapv1.LeveragePosition) error {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if pos.LiquidationStatus == whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_INITIALIZED {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "liquidation already initialized")
	}
	pos.LiquidationStatus = whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_INITIALIZED
	pos.Status = whaleswapv1.PositionStatus_POSITION_STATUS_LIQUIDATING
	pos.LiquidationInitializedBlockHeight = uint64(sdkCtx.BlockHeight())
	return nil
}

// ClearLiquidationPending resets liquidation state (called by AddCollateral).
func (k Keeper) ClearLiquidationPending(pos *whaleswapv1.LeveragePosition) {
	pos.LiquidationStatus = whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE
	pos.Status = whaleswapv1.PositionStatus_POSITION_STATUS_OPEN
	pos.LiquidationInitializedBlockHeight = 0
}

// CanCloseBefore checks if 1 block has passed since creation.
func (k Keeper) CanCloseBefore(ctx context.Context, pos *whaleswapv1.LeveragePosition) bool {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	return uint64(sdkCtx.BlockHeight()) > pos.CreatedBlockHeight
}

// CanFinalizeLiquidationBefore checks if 1 block has passed since initialize.
func (k Keeper) CanFinalizeLiquidationBefore(ctx context.Context, pos *whaleswapv1.LeveragePosition) bool {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	return uint64(sdkCtx.BlockHeight()) > pos.LiquidationInitializedBlockHeight
}

// BlocksUntilCloseable returns blocks until owner can close position.
func (k Keeper) BlocksUntilCloseable(ctx context.Context, pos *whaleswapv1.LeveragePosition) uint64 {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	currentHeight := uint64(sdkCtx.BlockHeight())
	if currentHeight > pos.CreatedBlockHeight {
		return 0
	}
	return pos.CreatedBlockHeight + 1 - currentHeight
}
