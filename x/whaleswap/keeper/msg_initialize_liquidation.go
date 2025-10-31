package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// InitializeLiquidation marks a leveraged position for liquidation when its
// collateral ratio falls below the pool's liquidation_threshold.
//
// Semantics:
//   - Trigger: permissionless; any initializer may call this for any position.
//   - Computation: accrues interest on the borrowed amount using the
//     snapshotted per-denom APR and elapsed seconds since borrow_time; computes
//     CR = collateral / (principal + interest) using the position snapshot.
//   - Threshold: compares CR against the pool's per-denom liquidation_threshold
//     for the borrowed denom; the threshold must be configured (> 1).
//   - State updates: records liquidation markers (status and the current block
//     height) on the position and persists it.
//
// Emits:
//   - EventLeverageLiquidationInitialized (position_id, user, pool_id,
//     collateral_ratio, liquidation_threshold, block_height)
//
// Returns:
//   - *whaleswapv1.MsgInitializeLiquidationResponse with CollateralRatio and
//     LiquidationThreshold.
//
// Errors are returned on validation failures (missing position/pool, malformed
// snapshots or thresholds, position not liquidatable) or event emission
// failures; no panics.
func (k Keeper) InitializeLiquidation(ctx context.Context, msg *whaleswapv1.MsgInitializeLiquidation) (*whaleswapv1.MsgInitializeLiquidationResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("InitializeLiquidation: begin",
		"position_id", msg.PositionId,
		"initializer", msg.Initializer,
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
	logger.Info("InitializeLiquidation: loaded position",
		"pos_user", pos.User,
		"borrowed", pos.Borrowed.String(),
		"collateral", pos.Collateral.String(),
		"interest_rate", pos.InterestRate.String(),
		"borrow_time", pos.BorrowTime,
		"liquidation_status", pos.LiquidationStatus.String(),
	)

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	// Calculate CR using per-position snapshot rate; must be set (len 2)
	if len(pos.InterestRate) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "position interest_rate must have exactly 2 entries")
	}
	rate := pos.InterestRate.AmountOf(pos.Borrowed.Denom)
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, _ := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))

	collateralValue := math.LegacyNewDecFromInt(pos.Collateral.Amount)
	debtValue := math.LegacyNewDecFromInt(pos.Borrowed.Amount).Add(interest)
	cr, _ := k.ComputeCollateralRatio(collateralValue, debtValue)
	logger.Info("InitializeLiquidation: computed",
		"elapsed_sec", int64(elapsed),
		"interest", interest.String(),
		"collateral_value", collateralValue.String(),
		"debt_with_interest", debtValue.String(),
		"cr", cr.String(),
	)

	// Require pool liquidation_threshold to be set; use per-borrow denom
	if len(pool.LiquidationThreshold) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool liquidation_threshold must be set")
	}
	liquidationThreshold := pool.LiquidationThreshold.AmountOf(pos.Borrowed.Denom)
	if !liquidationThreshold.GT(math.LegacyNewDec(1)) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool liquidation_threshold")
	}
	logger.Info("InitializeLiquidation: thresholds",
		"liquidation_threshold", liquidationThreshold.String(),
	)

	if !k.IsPositionLiquidatable(cr, liquidationThreshold) {
		return nil, cosmossdkerrors.Wrapf(
			whaleswapv1.ErrPositionNotLiquidatable,
			"collateral ratio %s >= liquidation threshold %s",
			cr.String(),
			liquidationThreshold.String(),
		)
	}
	logger.Info("InitializeLiquidation: position is liquidatable")

	prevStatus := pos.Status
	if err := k.InitializeLiquidationInternal(ctx, &pos); err != nil {
		return nil, err
	}
	if err := k.savePosition(ctx, pos, prevStatus); err != nil {
		return nil, err
	}
	logger.Info("InitializeLiquidation: updated position state",
		"liquidation_status", pos.LiquidationStatus.String(),
		"liquidation_initialized_height", pos.LiquidationInitializedBlockHeight,
	)

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
	logger.Info("InitializeLiquidation: event emitted",
		"position_id", msg.PositionId,
		"cr", cr.String(),
		"threshold", liquidationThreshold.String(),
		"block", uint64(sdkCtx.BlockHeight()),
	)

	resp := &whaleswapv1.MsgInitializeLiquidationResponse{
		CollateralRatio:      cr,
		LiquidationThreshold: liquidationThreshold,
	}
	logger.Info("InitializeLiquidation: complete", "response", resp)
	return resp, nil
}
