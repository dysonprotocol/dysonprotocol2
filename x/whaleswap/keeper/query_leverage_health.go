package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// Position queries a leverage position by ID and includes comprehensive health and interest information.
//
// Semantics:
//   - Retrieves complete position data including collateral, debt, and status.
//   - Computes real-time interest accrual based on elapsed time and rates.
//   - Calculates current collateral ratio and liquidation health status.
//   - Determines action permissions: close by owner, initialize/finalize liquidation.
//   - Returns enriched position data with computed fields for UI consumption.
//
// Validation:
//   - Request must be non-nil.
//   - PositionId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryPositionResponse with position data and computed health metrics.
//
// Errors are returned on invalid parameters, position not found, or computation failures; no panics.
func (k Keeper) Position(ctx context.Context, req *whaleswapv1.QueryPositionRequest) (*whaleswapv1.QueryPositionResponse, error) {
	if req == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "request cannot be nil")
	}
	if req.PositionId == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "position_id required")
	}
	pos, err := k.LeveragePositions.Get(ctx, req.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", req.PositionId)
	}
	status := pos.Status

	interest, elapsed, err := k.InterestStatus(ctx, &pos)
	if err != nil {
		return nil, err
	}
	rate := pos.InterestRate.AmountOf(pos.Borrowed.Denom)

	// Compute collateral ratio
	collateralValue := math.LegacyNewDecFromInt(pos.Collateral.Amount)
	debtValue := math.LegacyNewDecFromInt(pos.Borrowed.Amount).Add(interest)

	cr := math.LegacyNewDec(0)
	if !debtValue.IsZero() {
		cr, _ = k.ComputeCollateralRatio(collateralValue, debtValue)
	}

	health, err := k.ComputeHealthStatus(collateralValue, debtValue)
	if err != nil {
		return nil, err
	}

	// Use position's snapshotted liquidation_threshold
	liquidationThreshold, err := math.LegacyNewDecFromStr(pos.LiquidationThreshold)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid position liquidation_threshold: %s", pos.LiquidationThreshold)
	}
	if !liquidationThreshold.GT(math.LegacyNewDec(1)) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid position liquidation_threshold")
	}

	canClose := false
	canInitialize := false
	canFinalize := false
	blocksUntilCloseable := uint64(0)
	if status == whaleswapv1.PositionStatus_POSITION_STATUS_OPEN {
		canClose = k.CanCloseBefore(ctx, &pos)
		canInitialize = pos.LiquidationStatus == whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE && cr.LT(liquidationThreshold)
		blocksUntilCloseable = k.BlocksUntilCloseable(ctx, &pos)
	} else if status == whaleswapv1.PositionStatus_POSITION_STATUS_LIQUIDATING {
		canFinalize = k.CanFinalizeLiquidationBefore(ctx, &pos) && pos.LiquidationStatus == whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_INITIALIZED
	}

	// Compute total repayment
	totalRepayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)
	repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, totalRepayment)

	interestView := whaleswapv1.InterestView{
		InterestDue:    interest,
		TotalRepayment: repaymentCoin,
		TimeElapsed:    uint64(elapsed),
		AnnualRate:     rate,
	}

	return &whaleswapv1.QueryPositionResponse{
		Position:                 pos,
		HealthStatus:             health,
		CurrentCollateralRatio:   cr,
		LiquidationThreshold:     liquidationThreshold,
		CollateralValue:          collateralValue,
		DebtWithInterest:         debtValue,
		CanCloseByOwner:          canClose,
		BlocksUntilCloseable:     blocksUntilCloseable,
		CanInitializeLiquidation: canInitialize,
		CanFinalizeLiquidation:   canFinalize,
		Interest:                 interestView,
	}, nil
}
