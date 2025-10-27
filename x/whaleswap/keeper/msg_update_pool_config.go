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

	// Apply optional updates
	if msg.FeePct != "" {
		fee, ferr := math.LegacyNewDecFromStr(msg.FeePct)
		if ferr != nil || fee.IsNegative() || fee.GTE(math.LegacyNewDec(1)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid fee_pct: %s", msg.FeePct)
		}
		pool.FeePct = msg.FeePct
	}

	// Update leverage configuration fields if provided
	if msg.MinCollateralRatio != "" {
		minCR, err := math.LegacyNewDecFromStr(msg.MinCollateralRatio)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid min_collateral_ratio: %v", err)
		}
		if minCR.LTE(math.LegacyNewDec(1)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_collateral_ratio must be > 1: %s", minCR.String())
		}
		pool.MinCollateralRatio = msg.MinCollateralRatio
	}
	if msg.MaxLeverageRatio != "" {
		maxLev, err := math.LegacyNewDecFromStr(msg.MaxLeverageRatio)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid max_leverage_ratio: %v", err)
		}
		if maxLev.LTE(math.LegacyNewDec(1)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_leverage_ratio must be > 1: %s", maxLev.String())
		}
		pool.MaxLeverageRatio = msg.MaxLeverageRatio
	}
	if msg.MaxBorrowPercent != "" {
		maxBorrow, err := math.LegacyNewDecFromStr(msg.MaxBorrowPercent)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid max_borrow_percent: %v", err)
		}
		if maxBorrow.IsNegative() || maxBorrow.GT(math.LegacyNewDec(1)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_borrow_percent must be in [0,1]: %s", maxBorrow.String())
		}
		pool.MaxBorrowPercent = msg.MaxBorrowPercent
	}

	// Bands: compare prices using cross-multiplication on ints; avoid Decs
	if len(msg.MinPrice) > 0 || len(msg.MaxPrice) > 0 {
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
		// Sort for canonical order then extract amounts for pool pair
		msg.MinPrice.Sort()
		msg.MaxPrice.Sort()
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
			"AMM invariant after UpdatePoolConfig: pool_id=%d fee_pct=%s min=%s max=%s",
			pool.PoolId,
			pool.FeePct,
			pool.MinPrice.String(),
			pool.MaxPrice.String(),
		)
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after UpdatePoolConfig")
	}
	return &whaleswapv1.MsgUpdatePoolConfigResponse{}, nil
}
