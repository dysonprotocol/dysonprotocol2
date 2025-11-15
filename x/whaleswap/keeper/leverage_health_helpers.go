package keeper

import (
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// ensureHealthyCollateralRatio verifies that the provided collateral and debt amounts keep the position
// above both its minimum collateral ratio and liquidation threshold. It returns the resulting ratio.
func (k Keeper) ensureHealthyCollateralRatio(
	pos *whaleswapv1.LeveragePosition,
	collateral sdk.Coin,
	debt sdk.Coin,
) (math.LegacyDec, error) {
	if debt.Amount.IsZero() {
		return math.LegacyZeroDec(), nil
	}
	if !collateral.Amount.IsPositive() {
		return math.LegacyZeroDec(), cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral must remain positive")
	}
	if collateral.Denom != debt.Denom {
		return math.LegacyZeroDec(), cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral/debt denom mismatch")
	}

	collateralValue := math.LegacyNewDecFromInt(collateral.Amount)
	debtValue := math.LegacyNewDecFromInt(debt.Amount)
	ratio, err := k.ComputeCollateralRatio(collateralValue, debtValue)
	if err != nil {
		return math.LegacyZeroDec(), err
	}

	minCR, err := math.LegacyNewDecFromStr(pos.MinCollateralRatio)
	if err != nil {
		return math.LegacyZeroDec(), cosmossdkerrors.Wrap(err, "invalid min_collateral_ratio")
	}
	if ratio.LT(minCR) {
		return math.LegacyZeroDec(), cosmossdkerrors.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"collateral ratio %s below minimum %s",
			ratio.String(),
			minCR.String(),
		)
	}

	liqThreshold, err := math.LegacyNewDecFromStr(pos.LiquidationThreshold)
	if err != nil {
		return math.LegacyZeroDec(), cosmossdkerrors.Wrap(err, "invalid liquidation_threshold")
	}
	if ratio.LT(liqThreshold) {
		return math.LegacyZeroDec(), cosmossdkerrors.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"collateral ratio %s below liquidation threshold %s",
			ratio.String(),
			liqThreshold.String(),
		)
	}

	return ratio, nil
}
