package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// UpdatePoolConfig updates a pool's dynamic configuration (fees, leverage/threshold
// params, interest, optional max_borrow_percent, and bound_percent); majority-owner only.
//
// Semantics:
//   - Loads pool; validates signer and majority-ownership.
//   - Fee rates: optional; normalizes to two DecCoins (pool order); 0 <= x < 1.
//   - Leverage config: required `min_collateral_ratio` and `max_leverage_ratio`
//     with exactly two entries matching pool denoms; each > 1.
//   - Liquidation threshold: required with exactly two entries; each > 1.
//   - Interest rate: allows 0/1/2 entries; normalizes to two; each >= 0.
//   - Max borrow percent: optional; if provided exactly two entries; 0 <= x < 1.
//   - Bound percent: optional; when provided must contain exactly two DecCoins
//     matching pool denoms with amounts in (0,1]; 1 disables the bound. Omit to
//     leave existing bounds unchanged.
//   - Persists pool with `updated` timestamp; emits EventPoolUpdate; asserts AMM
//     and module invariants.
//
// Validation:
//   - Pool must exist.
//   - Signer must be valid address and hold majority of pool shares.
//   - Fee rates when provided must satisfy 0 <= x < 1 for both denoms.
//   - Leverage config (min_collateral_ratio, max_leverage_ratio) must have
//     exactly two entries (> 1) matching pool denoms in canonical order.
//   - Liquidation threshold must have exactly two entries (> 1) matching pool
//     denoms in canonical order.
//   - Interest rates when provided must be >= 0 for both denoms.
//   - Max borrow percent when provided must have exactly two entries with amounts
//     in [0,1) matching pool denoms in canonical order.
//   - Bound percent when provided must contain at most two entries with amounts
//     in (0,1] matching pool denoms.
//
// State Updates:
//   - Updates pool configuration fields in PoolsMap.
//   - Sets pool.Updated timestamp to current block time.
//
// Emits:
//   - EventPoolUpdate(pool_id)
//
// Returns:
//   - *whaleswapv1.MsgUpdatePoolConfigResponse (empty).
//
// Errors are returned on missing pool, invalid signer/ownership, malformed
// inputs (denom/order mismatches, invalid ratios), persistence or event emission
// failures, or invariant violations; no panics.
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
		denomA, denomB := pool.Coins[0].Denom, pool.Coins[1].Denom
		one := math.LegacyNewDec(1)
		inFee := sdk.NewDecCoins(msg.FeeRate...)
		fr1 := inFee.AmountOf(denomA)
		fr2 := inFee.AmountOf(denomB)
		if fr1.IsNegative() || !fr1.LT(one) || fr2.IsNegative() || !fr2.LT(one) {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "fee_rate amounts must satisfy 0 <= x < 1")
		}
		pool.FeeRate = sdk.DecCoins{
			sdk.NewDecCoinFromDec(denomA, fr1),
			sdk.NewDecCoinFromDec(denomB, fr2),
		}
	}

	// MinCollateralRatio: required; per-denom; > 1
	denomA, denomB := pool.Coins[0].Denom, pool.Coins[1].Denom
	one := math.LegacyNewDec(1)
	zero := math.LegacyZeroDec()
	inMinCR := sdk.NewDecCoins(msg.MinCollateralRatio...)
	if len(inMinCR) != 2 || inMinCR[0].Denom != denomA || inMinCR[1].Denom != denomB {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_collateral_ratio must have exactly two entries matching pool denoms [%s,%s] in canonical order", denomA, denomB)
	}
	if inMinCR[0].Amount.LTE(one) || inMinCR[1].Amount.LTE(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "min_collateral_ratio amounts must be > 1 for both denoms")
	}
	pool.MinCollateralRatio = inMinCR

	inMaxLev := sdk.NewDecCoins(msg.MaxLeverageRatio...)
	if len(inMaxLev) != 2 || inMaxLev[0].Denom != denomA || inMaxLev[1].Denom != denomB {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_leverage_ratio must have exactly two entries matching pool denoms [%s,%s] in canonical order", denomA, denomB)
	}
	if inMaxLev[0].Amount.LTE(one) || inMaxLev[1].Amount.LTE(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "max_leverage_ratio amounts must be > 1 for both denoms")
	}
	pool.MaxLeverageRatio = inMaxLev

	// Liquidation threshold (required; per-denom; > 1)
	inLiq := sdk.NewDecCoins(msg.LiquidationThreshold...)
	if len(inLiq) != 2 || inLiq[0].Denom != denomA || inLiq[1].Denom != denomB {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "liquidation_threshold must have exactly two entries matching pool denoms [%s,%s] in canonical order", denomA, denomB)
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
	ir1 := inIR.AmountOf(denomA)
	ir2 := inIR.AmountOf(denomB)
	if ir1.IsNegative() || ir2.IsNegative() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "interest_rate amounts must be >= 0")
	}
	pool.InterestRate = sdk.DecCoins{
		sdk.NewDecCoinFromDec(denomA, ir1),
		sdk.NewDecCoinFromDec(denomB, ir2),
	}

	// MaxBorrowPercent (optional). Accept exactly two DecCoins in canonical order; amounts in [0,1).
	if len(msg.MaxBorrowPercent) > 0 {
		if len(pool.Coins) != 2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid pool coins")
		}
		if len(msg.MaxBorrowPercent) != 2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_borrow_percent must contain exactly two entries when provided")
		}
		denomA, denomB := pool.Coins[0].Denom, pool.Coins[1].Denom
		dec := sdk.NewDecCoins(msg.MaxBorrowPercent...)
		if len(dec) != 2 || dec[0].Denom != denomA || dec[1].Denom != denomB {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_borrow_percent denoms must match pool coins in canonical order: want [%s,%s]", denomA, denomB)
		}
		one := math.LegacyNewDec(1)
		if dec[0].Amount.IsNegative() || dec[0].Amount.GTE(one) ||
			dec[1].Amount.IsNegative() || dec[1].Amount.GTE(one) {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "max_borrow_percent amounts must satisfy 0 <= x < 1")
		}
		pool.MaxBorrowPercent = dec
	}

	// BoundPercent (optional). When provided, accept up to two entries in pool order with amounts in (0,1].
	if len(msg.BoundPercent) > 0 {
		if len(msg.BoundPercent) > 2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "bound_percent supports at most two entries, got %d", len(msg.BoundPercent))
		}
		seen := make(map[string]struct{}, len(msg.BoundPercent))
		for _, bc := range msg.BoundPercent {
			if bc.Denom != denomA && bc.Denom != denomB {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "bound_percent denom %s must match pool denoms [%s,%s]", bc.Denom, denomA, denomB)
			}
			if _, exists := seen[bc.Denom]; exists {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "duplicate bound_percent entry for denom %s", bc.Denom)
			}
			seen[bc.Denom] = struct{}{}
			if !bc.Amount.GT(zero) || bc.Amount.GT(one) {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "bound_percent amounts must satisfy 0 < x <= 1 for provided denoms")
			}
		}
		bounds := sdk.NewDecCoins(msg.BoundPercent...)
		b1 := bounds.AmountOf(denomA)
		b2 := bounds.AmountOf(denomB)
		if b1.IsZero() {
			current := pool.BoundPercent.AmountOf(denomA)
			if current.IsZero() {
				current = one
			}
			b1 = current
		}
		if b2.IsZero() {
			current := pool.BoundPercent.AmountOf(denomB)
			if current.IsZero() {
				current = one
			}
			b2 = current
		}
		pool.BoundPercent = sdk.DecCoins{
			sdk.NewDecCoinFromDec(denomA, b1),
			sdk.NewDecCoinFromDec(denomB, b2),
		}
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
			"AMM invariant after UpdatePoolConfig: pool_id=%d bound_percent=%s",
			pool.PoolId,
			pool.BoundPercent.String(),
		)
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after UpdatePoolConfig")
	}
	return &whaleswapv1.MsgUpdatePoolConfigResponse{}, nil
}
