package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

/**
 * AddCollateral deposits additional collateral to a leveraged position and clears
 * liquidation markers.
 *
 * Behavior:
 * - Validates position ownership and pool/denom consistency.
 * - Transfers additional collateral from the user to the module.
 * - Adds the collateral to the position's existing collateral amount.
 * - Clears any pending liquidation markers on the position.
 * - Persists the updated position and computes the new collateral ratio.
 *
 * Validation:
 * - Position must exist and be owned by `user`.
 * - Pool ID must match the position's pool.
 * - Collateral denom must match the position's existing collateral denom.
 * - Collateral amount must be positive.
 *
 * Emits:
 * - EventLeverageCollateralAdded with position_id, user, pool_id,
 *   collateral_added, new_collateral, new_collateral_ratio.
 *
 * Returns:
 * - NewCollateral: updated collateral coin after addition.
 * - NewCollateralRatio: ratio of new collateral amount to borrowed amount
 *   (LegacyDec string).
 *
 * Errors are returned on validation failures (missing position, unauthorized
 * access, denom mismatches, invalid amounts) or event emission failures; no
 * panics.
 */
func (k Keeper) AddCollateral(ctx context.Context, msg *whaleswapv1.MsgAddCollateral) (*whaleswapv1.MsgAddCollateralResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	if pos.User != msg.User {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "not position owner")
	}
	if pos.PoolId != msg.PoolId {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id mismatch")
	}
	if msg.Collateral.Denom != pos.Collateral.Denom {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral denom mismatch")
	}
	if !msg.Collateral.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral amount must be positive")
	}
	userAddr, err := k.addr(ctx, msg.User)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}
	if err := k.sendToModule(ctx, userAddr, sdk.NewCoins(msg.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to transfer collateral to module")
	}

	newCollateralAmount := pos.Collateral.Amount.Add(msg.Collateral.Amount)
	newCollateral := sdk.NewCoin(pos.Collateral.Denom, newCollateralAmount)
	pos.Collateral = newCollateral

	k.ClearLiquidationPending(&pos)
	if err := k.LeveragePositions.Set(ctx, msg.PositionId, pos); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update position %d", msg.PositionId)
	}

	newCR := math.LegacyNewDecFromInt(newCollateralAmount).Quo(math.LegacyNewDecFromInt(pos.Borrowed.Amount))

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeverageCollateralAdded{
		PositionId:         msg.PositionId,
		User:               msg.User,
		PoolId:             msg.PoolId,
		CollateralAdded:    msg.Collateral,
		NewCollateral:      newCollateral,
		NewCollateralRatio: newCR.String(),
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return &whaleswapv1.MsgAddCollateralResponse{
		NewCollateral:      newCollateral,
		NewCollateralRatio: newCR,
	}, nil
}
