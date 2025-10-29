package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

func (k Keeper) UpdatePoolConfig(ctx context.Context, msg *whaleswapv1.MsgUpdatePoolConfig) (*whaleswapv1.MsgUpdatePoolConfigResponse, error) {
	// Load pool
	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", msg.PoolId)
	}
	// Check majority owner
	signer, err := k.addr(ctx, msg.Signer)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get signer address: %s", msg.Signer)
	}
	if err := k.ensureMajorityOwner(ctx, pool, signer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "signer is not majority owner of shares: %s", signer.String())
	}

	// FeeRate: allow 0, 1, or 2 entries; if provided, normalize using DecCoins helpers and store exactly two entries.
	if len(msg.FeeRate) > 0 {
		if len(pool.Coins) != 2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid pool coins")
		}
		baseDenom, quoteDenom := pool.Coins[0].Denom, pool.Coins[1].Denom
		one := math.LegacyNewDec(1)
		inFee := sdk.NewDecCoins(msg.FeeRate...)
		fr1 := inFee.AmountOf(baseDenom)
		fr2 := inFee.AmountOf(quoteDenom)
		if fr1.IsNegative() || !fr1.LT(one) || fr2.IsNegative() || !fr2.LT(one) {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "fee_rate amounts must satisfy 0 <= x < 1")
		}
		pool.FeeRate = sdk.DecCoins{
			sdk.NewDecCoinFromDec(baseDenom, fr1),
			sdk.NewDecCoinFromDec(quoteDenom, fr2),
		}
	}

	// MinCollateralRatio: required; per-denom; > 1
	baseDenom, quoteDenom := pool.Coins[0].Denom, pool.Coins[1].Denom
	one := math.LegacyNewDec(1)
	inMinCR := sdk.NewDecCoins(msg.MinCollateralRatio...)
	if len(inMinCR) != 2 || inMinCR[0].Denom != baseDenom || inMinCR[1].Denom != quoteDenom {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_collateral_ratio must have exactly two entries matching pool denoms [%s,%s] in canonical order", baseDenom, quoteDenom)
	}
	if inMinCR[0].Amount.LTE(one) || inMinCR[1].Amount.LTE(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "min_collateral_ratio amounts must be > 1 for both denoms")
	}
	pool.MinCollateralRatio = inMinCR

	inMaxLev := sdk.NewDecCoins(msg.MaxLeverageRatio...)
	if len(inMaxLev) != 2 || inMaxLev[0].Denom != baseDenom || inMaxLev[1].Denom != quoteDenom {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_leverage_ratio must have exactly two entries matching pool denoms [%s,%s] in canonical order", baseDenom, quoteDenom)
	}
	if inMaxLev[0].Amount.LTE(one) || inMaxLev[1].Amount.LTE(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "max_leverage_ratio amounts must be > 1 for both denoms")
	}
	pool.MaxLeverageRatio = inMaxLev

	// Liquidation threshold (required; per-denom; > 1)
	inLiq := sdk.NewDecCoins(msg.LiquidationThreshold...)
	if len(inLiq) != 2 || inLiq[0].Denom != baseDenom || inLiq[1].Denom != quoteDenom {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "liquidation_threshold must have exactly two entries matching pool denoms [%s,%s] in canonical order", baseDenom, quoteDenom)
	}
	if inLiq[0].Amount.LTE(one) || inLiq[1].Amount.LTE(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "liquidation_threshold amounts must be > 1 for both denoms")
	}
	pool.LiquidationThreshold = inLiq
	// InterestRate: allow 0, 1, or 2 entries. Normalize using DecCoins helpers and store exactly two entries.
	if len(pool.Coins) != 2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid pool coins")
	}
	inIR := sdk.NewDecCoins(msg.InterestRate...)
	ir1 := inIR.AmountOf(baseDenom)
	ir2 := inIR.AmountOf(quoteDenom)
	if ir1.IsNegative() || ir2.IsNegative() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "interest_rate amounts must be >= 0")
	}
	pool.InterestRate = sdk.DecCoins{
		sdk.NewDecCoinFromDec(baseDenom, ir1),
		sdk.NewDecCoinFromDec(quoteDenom, ir2),
	}

	// MaxBorrowPercent (optional). Accept exactly two DecCoins in canonical order; amounts in [0,1).
	if len(msg.MaxBorrowPercent) > 0 {
		if len(pool.Coins) != 2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid pool coins")
		}
		if len(msg.MaxBorrowPercent) != 2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_borrow_percent must contain exactly two entries when provided")
		}
		baseDenom, quoteDenom := pool.Coins[0].Denom, pool.Coins[1].Denom
		dec := sdk.NewDecCoins(msg.MaxBorrowPercent...)
		if len(dec) != 2 || dec[0].Denom != baseDenom || dec[1].Denom != quoteDenom {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_borrow_percent denoms must match pool coins in canonical order: want [%s,%s]", baseDenom, quoteDenom)
		}
		one := math.LegacyNewDec(1)
		if dec[0].Amount.IsNegative() || dec[0].Amount.GTE(one) ||
			dec[1].Amount.IsNegative() || dec[1].Amount.GTE(one) {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "max_borrow_percent amounts must satisfy 0 <= x < 1")
		}
		pool.MaxBorrowPercent = dec
	}

	// Bands: required fields, but allow empty arrays to disable band.
	// If both empty, clear bands; else expect exactly two coins per band in canonical order.
	if len(msg.MinPrice) == 0 && len(msg.MaxPrice) == 0 {
		pool.MinPrice = sdk.NewCoins()
		pool.MaxPrice = sdk.NewCoins()
	} else {
		// Sanitize band vectors first to drop zeros and canonicalize ordering
		msg.MinPrice = sdk.NewCoins(msg.MinPrice...)
		msg.MaxPrice = sdk.NewCoins(msg.MaxPrice...)
		if len(pool.Coins) != 2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid pool coins")
		}
		baseDenom, quoteDenom := pool.Coins[0].Denom, pool.Coins[1].Denom
		// Require both bands set
		if len(msg.MinPrice) == 0 || len(msg.MaxPrice) == 0 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "must set both min_price and max_price or neither")
		}
		// Already canonical via NewCoins; extract amounts for pool pair
		minBase := msg.MinPrice.AmountOf(baseDenom)
		minQuote := msg.MinPrice.AmountOf(quoteDenom)
		maxBase := msg.MaxPrice.AmountOf(baseDenom)
		maxQuote := msg.MaxPrice.AmountOf(quoteDenom)
		if !minBase.IsPositive() || !minQuote.IsPositive() || !maxBase.IsPositive() || !maxQuote.IsPositive() {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "band amounts must be > 0 for both denoms")
		}
		// Enforce max > min strictly: maxQuote/maxBase > minQuote/minBase => maxQuote*minBase > minQuote*maxBase
		if !maxQuote.Mul(minBase).GT(minQuote.Mul(maxBase)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_price [%s] must be > min_price [%s]", msg.MaxPrice.String(), msg.MinPrice.String())
		}
		// Current price within [min, max]
		rBase := pool.Coins[0].Amount
		rQuote := pool.Coins[1].Amount
		// Enforce strictly within (min, max):
		// P > min => rQuote*minBase > rBase*minQuote
		if !rQuote.Mul(minBase).GT(rBase.Mul(minQuote)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "current price [%s] must be greater than min_price [%s]", rQuote.Mul(minBase).String(), rBase.Mul(minQuote).String())
		}
		// P < max => rQuote*maxBase < rBase*maxQuote
		if !rQuote.Mul(maxBase).LT(rBase.Mul(maxQuote)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "current price [%s] must be less than max_price [%s]", rQuote.Mul(maxBase).String(), rBase.Mul(maxQuote).String())
		}
		// Store only the two relevant coins in canonical pool order
		pool.MinPrice = sdk.NewCoins(sdk.NewCoin(baseDenom, minBase), sdk.NewCoin(quoteDenom, minQuote))
		pool.MaxPrice = sdk.NewCoins(sdk.NewCoin(baseDenom, maxBase), sdk.NewCoin(quoteDenom, maxQuote))
	}

	// Save and emit
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	t := sdkCtx.BlockTime()
	pool.Updated = &t
	if err := k.PoolsMap.Set(ctx, pool.PoolId, pool); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set pool: %d", pool.PoolId)
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolUpdate{PoolId: pool.PoolId}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPoolUpdate")
	}
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err,
			"AMM invariant after UpdatePoolConfig: pool_id=%d min=%s max=%s",
			pool.PoolId,
			pool.MinPrice.String(),
			pool.MaxPrice.String(),
		)
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after UpdatePoolConfig")
	}
	return &whaleswapv1.MsgUpdatePoolConfigResponse{}, nil
}
