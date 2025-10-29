package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// Position queries a leverage position by ID and includes health and interest information.
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

	// Compute interest
	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	if len(pos.InterestRate) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "position interest_rate must have exactly 2 entries")
	}
	rate := pos.InterestRate.AmountOf(pos.Borrowed.Denom)

	// Calculate elapsed time
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	blockTime := sdkCtx.BlockTime()
	elapsed := blockTime.Sub(*pos.BorrowTime).Seconds()

	interest, err := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
	if err != nil {
		return nil, err
	}

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

	// Require pool liquidation_threshold to be set; per-denom
	if len(pool.LiquidationThreshold) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool liquidation_threshold must be set")
	}
	liquidationThreshold := pool.LiquidationThreshold.AmountOf(pos.Borrowed.Denom)
	if !liquidationThreshold.GT(math.LegacyNewDec(1)) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool liquidation_threshold")
	}

	canClose := k.CanCloseBefore(ctx, &pos)
	canInitialize := pos.LiquidationStatus == whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE && cr.LT(liquidationThreshold)
	canFinalize := k.CanFinalizeLiquidationBefore(ctx, &pos) && pos.LiquidationStatus == whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_INITIALIZED

	// Compute total repayment
	totalRepayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)

	return &whaleswapv1.QueryPositionResponse{
		Position:                 pos,
		HealthStatus:             health,
		CurrentCollateralRatio:   cr,
		LiquidationThreshold:     liquidationThreshold,
		CollateralValue:          collateralValue,
		DebtWithInterest:         debtValue,
		CanCloseByOwner:          canClose,
		BlocksUntilCloseable:     k.BlocksUntilCloseable(ctx, &pos),
		CanInitializeLiquidation: canInitialize,
		CanFinalizeLiquidation:   canFinalize,
		Borrowed:                 pos.Borrowed,
		AccruedInterest:          interest,
		TotalRepayment:           sdk.NewCoin(pos.Borrowed.Denom, totalRepayment),
		TimeElapsed:              uint64(elapsed),
		AnnualRate:               rate,
	}, nil
}
