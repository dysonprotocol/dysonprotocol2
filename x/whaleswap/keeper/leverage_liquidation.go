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

// ComputeHealthStatus evaluates position collateral ratio and returns health status
// relative to the position's liquidation_threshold.
//
// Health status is derived from the actual liquidation_threshold to ensure consistency:
//   - LIQUIDATABLE: CR < liquidation_threshold (position can be liquidated)
//   - AT_RISK: CR < liquidation_threshold * 1.25 (within 25% of liquidation)
//   - HEALTHY: CR >= liquidation_threshold * 1.25 (comfortable margin)
func (k Keeper) ComputeHealthStatus(collateralValue, debtWithInterest, liquidationThreshold math.LegacyDec) (whaleswapv1.PositionHealthStatus, error) {
	if debtWithInterest.IsZero() {
		return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_HEALTHY, nil
	}
	if debtWithInterest.IsNegative() {
		return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_UNSPECIFIED, fmt.Errorf("debt cannot be negative")
	}
	cr := collateralValue.Quo(debtWithInterest)

	// Derive thresholds from the position's actual liquidation_threshold
	// AT_RISK buffer: 25% above liquidation threshold
	atRiskBuffer := math.LegacyNewDecWithPrec(125, 2) // 1.25
	thresholdAtRisk := liquidationThreshold.Mul(atRiskBuffer)

	if cr.LT(liquidationThreshold) {
		return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_LIQUIDATABLE, nil
	}
	if cr.LT(thresholdAtRisk) {
		return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_AT_RISK, nil
	}
	return whaleswapv1.PositionHealthStatus_POSITION_HEALTH_STATUS_HEALTHY, nil
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

// CanCloseBefore checks if sufficient blocks have passed since creation per params.
func (k Keeper) CanCloseBefore(ctx context.Context, pos *whaleswapv1.LeveragePosition) bool {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	params := k.GetParams(ctx)
	currentHeight := uint64(sdkCtx.BlockHeight())
	requiredHeight := pos.CreatedHeight + params.BlockDelayBeforeClose
	return currentHeight >= requiredHeight
}

// CanFinalizeLiquidationBefore checks if sufficient blocks have passed since initialize per params.
func (k Keeper) CanFinalizeLiquidationBefore(ctx context.Context, pos *whaleswapv1.LeveragePosition) bool {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	params := k.GetParams(ctx)
	currentHeight := uint64(sdkCtx.BlockHeight())
	requiredHeight := pos.LiquidationInitializedBlockHeight + params.BlockDelayBeforeLiquidation
	return currentHeight >= requiredHeight
}

// BlocksUntilCloseable returns blocks until owner can close position per params.
func (k Keeper) BlocksUntilCloseable(ctx context.Context, pos *whaleswapv1.LeveragePosition) uint64 {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	params := k.GetParams(ctx)
	currentHeight := uint64(sdkCtx.BlockHeight())
	requiredHeight := pos.CreatedHeight + params.BlockDelayBeforeClose
	if currentHeight >= requiredHeight {
		return 0
	}
	return requiredHeight - currentHeight
}
