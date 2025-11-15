package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// RemoveCollateral withdraws collateral from a position while keeping the collateral ratio healthy.
func (k Keeper) RemoveCollateral(ctx context.Context, msg *whaleswapv1.MsgRemoveCollateral) (*whaleswapv1.MsgRemoveCollateralResponse, error) {
	if msg == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "message cannot be nil")
	}
	if !msg.Collateral.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral amount must be positive")
	}
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	if pos.Status != whaleswapv1.PositionStatus_POSITION_STATUS_OPEN {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "position not open")
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
	if msg.Collateral.Amount.GTE(pos.Collateral.Amount) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "cannot remove more collateral than available")
	}

	remainingCollateralAmt := pos.Collateral.Amount.Sub(msg.Collateral.Amount)
	if !remainingCollateralAmt.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral removal would leave zero collateral; close position instead")
	}
	remainingCollateralCoin := sdk.NewCoin(pos.Collateral.Denom, remainingCollateralAmt)

	totalDebt := pos.Borrowed.Add(pos.AccruedInterest)
	collateralForRatio := sdk.NewCoin(pos.Borrowed.Denom, remainingCollateralAmt)
	var newCR math.LegacyDec
	if totalDebt.Amount.IsPositive() {
		var err error
		newCR, err = k.ensureHealthyCollateralRatio(&pos, collateralForRatio, totalDebt)
		if err != nil {
			return nil, err
		}
	} else {
		newCR = math.LegacyZeroDec()
	}

	userAddr, err := k.addr(ctx, msg.User)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}

	pos.Collateral = remainingCollateralCoin
	if err := k.savePosition(ctx, pos, pos.Status); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update position %d", msg.PositionId)
	}

	if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(msg.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to return collateral")
	}

	return &whaleswapv1.MsgRemoveCollateralResponse{
		CollateralRemoved:  msg.Collateral,
		NewCollateral:      pos.Collateral,
		NewCollateralRatio: newCR,
	}, nil
}
