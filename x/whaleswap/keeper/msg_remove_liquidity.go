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
 * RemoveLiquidity removes liquidity from a pool by burning the caller's shares
 * and returning the underlying reserves proportional to the share burned.
 *
 * Behavior:
 * - Supports two modes: full exit and partial exit.
 * - Full exit: when burning all outstanding shares, the pool is deleted and
 *   the full reserves are paid out to the caller.
 * - Partial exit: burns a subset of shares and receives a payout proportional
 *   to that share using pro-rata DecCoins math; pool remains active with
 *   reduced reserves.
 * - Ensures partial exits cannot deplete any reserve below zero; full exit
 *   required to withdraw the last liquidity.
 *
 * Validation:
 * - Pool must exist.
 * - Signer must hold at least msg.Shares.
 * - Shares must be a positive integer string.
 * - Partial exits cannot deplete any reserve; withdrawing the last liquidity
 *   requires a full exit (burning all shares).
 *
 * Emits:
 * - EventPoolLiquidityRemoved (pool_id, shares)
 *
 * Returns:
 * - *whaleswapv1.MsgRemoveLiquidityResponse with Amount (coins returned to
 *   the caller).
 *
 * Errors are returned on validation failures, insufficient balance, reserve
 * depletion attempts, or state update failures; no panics.
 */
func (k Keeper) RemoveLiquidity(ctx context.Context, msg *whaleswapv1.MsgRemoveLiquidity) (*whaleswapv1.MsgRemoveLiquidityResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("RemoveLiquidity starting", "pool_id", msg.PoolId, "signer", msg.Signer, "shares", msg.Shares)
	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", msg.PoolId)
	}
	logger.Info("RemoveLiquidity loaded pool", "pool_id", pool.PoolId, "reserves", pool.Coins, "shares_denom", pool.SharesDenom)
	sharesAmt, ok := math.NewIntFromString(msg.Shares)
	if !ok || !sharesAmt.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid shares")
	}
	signer, err := k.addr(ctx, msg.Signer)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}
	bal := k.bank.GetBalance(ctx, signer, pool.SharesDenom).Amount
	if bal.LT(sharesAmt) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient shares: %s < %s", bal.String(), sharesAmt.String())
	}
	totalShares := k.bank.GetSupply(ctx, pool.SharesDenom).Amount
	// Full exit special-case: allow zeroing reserves only if burning all shares
	if sharesAmt.Equal(totalShares) {
		// Payout full reserves and delete the pool
		out1 := pool.Coins[0]
		out2 := pool.Coins[1]
		logger.Info("RemoveLiquidity full exit", "pool_id", pool.PoolId, "out1", out1, "out2", out2, "burn_shares", sharesAmt.String())
		if err := k.sendToModule(ctx, signer, sdk.NewCoins(sdk.NewCoin(pool.SharesDenom, sharesAmt))); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to escrow shares %s", sharesAmt.String())
		}
		if err := k.burnModule(ctx, sdk.NewCoins(sdk.NewCoin(pool.SharesDenom, sharesAmt))); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to burn shares %s", sharesAmt.String())
		}
		// Remove pool from state (no poolupdate emitted on deletion)
		if err := k.PoolsMap.Remove(ctx, msg.PoolId); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to escrow shares to module")
		}
		outs := sdk.NewCoins()
		if out1.IsPositive() {
			outs = outs.Add(out1)
		}
		if out2.IsPositive() {
			outs = outs.Add(out2)
		}
		if !outs.Empty() {
			if err := k.sendFromModule(ctx, signer, outs); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to burn shares from module")
			}
		}
		sdkCtx := sdk.UnwrapSDKContext(ctx)
		_ = sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolLiquidityRemoved{PoolId: pool.PoolId, Shares: sharesAmt.String()})
		logger.Info("RemoveLiquidity emitted EventPoolLiquidityRemoved", "pool_id", pool.PoolId, "shares", sharesAmt.String())
		return &whaleswapv1.MsgRemoveLiquidityResponse{Amount: outs}, nil
	}
	out1 := sdk.NewCoin(pool.Coins[0].Denom, math.NewInt(0))
	out2 := sdk.NewCoin(pool.Coins[1].Denom, math.NewInt(0))

	reservesDec := sdk.NewDecCoinsFromCoins(pool.Coins...)
	ratio := math.LegacyNewDecFromInt(sharesAmt).QuoInt(totalShares)
	payoutsDec := reservesDec.MulDecTruncate(ratio)
	payouts, _ := payoutsDec.TruncateDecimal()
	out1 = sdk.NewCoin(pool.Coins[0].Denom, payouts.AmountOf(pool.Coins[0].Denom))
	out2 = sdk.NewCoin(pool.Coins[1].Denom, payouts.AmountOf(pool.Coins[1].Denom))

	if !out1.IsPositive() && !out2.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "shares too small to exit")
	}
	logger.Info("RemoveLiquidity partial exit amounts", "out1", out1, "out2", out2)
	if err := k.sendToModule(ctx, signer, sdk.NewCoins(sdk.NewCoin(pool.SharesDenom, sharesAmt))); err != nil {
		return nil, err
	}
	if err := k.burnModule(ctx, sdk.NewCoins(sdk.NewCoin(pool.SharesDenom, sharesAmt))); err != nil {
		return nil, err
	}
	// Compute new reserves safely using Coins.SafeSub
	payoutsCoins := sdk.NewCoins()
	if out1.IsPositive() {
		payoutsCoins = payoutsCoins.Add(out1)
	}
	if out2.IsPositive() {
		payoutsCoins = payoutsCoins.Add(out2)
	}
	newReserves, hasNeg := pool.Coins.SafeSub(payoutsCoins...)
	if hasNeg {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "would deplete reserve")
	}
	// Apply updates
	pool.Coins = newReserves
	logger.Info("RemoveLiquidity new reserves", "r1", pool.Coins[0], "r2", pool.Coins[1])
	// Prevent reserve depletion on partial exits
	if pool.Coins[0].IsZero() || pool.Coins[1].IsZero() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "would deplete reserve; use full exit to withdraw all liquidity")
	}

	if err := k.updatePool(ctx, &pool); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update pool %d after remove", pool.PoolId)
	}
	logger.Info("RemoveLiquidity pool updated", "pool_id", pool.PoolId)
	outs := sdk.NewCoins()
	if out1.IsPositive() {
		outs = outs.Add(out1)
	}
	if out2.IsPositive() {
		outs = outs.Add(out2)
	}
	if err := k.sendFromModule(ctx, signer, outs); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send outputs %s to %s", outs.String(), msg.Signer)
	}
	sdkCtx2 := sdk.UnwrapSDKContext(ctx)
	if err := sdkCtx2.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolLiquidityRemoved{PoolId: pool.PoolId, Shares: sharesAmt.String()}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPoolLiquidityRemoved")
	}
	logger.Info("RemoveLiquidity emitted EventPoolLiquidityRemoved", "pool_id", pool.PoolId, "shares", sharesAmt.String())
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err,
			"AMM invariant after RemoveLiquidity: pool_id=%d burn_shares=%s out=(%s,%s) newR=(%s,%s)",
			pool.PoolId,
			sharesAmt.String(),
			out1.String(),
			out2.String(),
			pool.Coins[0].String(),
			pool.Coins[1].String(),
		)
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after RemoveLiquidity")
	}
	logger.Info("RemoveLiquidity completed successfully", "pool_id", pool.PoolId, "burned_shares", sharesAmt.String(), "outs", outs)
	return &whaleswapv1.MsgRemoveLiquidityResponse{Amount: outs}, nil
}
