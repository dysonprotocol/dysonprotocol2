package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// AddLiquidity mints pool shares to the signer in exchange for adding two
// reserve coins to a two-asset pool.
//
// Semantics:
//   - Ownership: the signer must be a majority owner of the pool shares.
//   - Inputs: exactly two positive coin amounts whose denoms match the pool
//     reserves (order is canonicalized to the pool's denom order).
//   - Escrow/Refund: the full provided amounts are escrowed first; any unused
//     surplus is refunded after the precise amounts used are derived.
//   - Minting: compute shares from the limiting side min(add1/existingR1,
//     add2/existingR2) * totalShares; refund the difference required to exactly
//     fund the minted shares.
//   - State updates: pool reserves are updated, the pool is persisted, shares
//     are minted via the nameservice module and transferred to the signer, an
//     EventPoolLiquidityAdded is emitted, and AMM/intra-module invariants are
//     asserted.
//
// Emits:
//   - EventPoolUpdate (after persisting pool state)
//   - EventPoolLiquidityAdded (on successful add)
//
// Returns:
//   - *whaleswapv1.MsgAddLiquidityResponse with minted shares encoded as a
//     decimal string in Shares.
//
// Errors are returned on validation or invariant violations; no panics.
func (k Keeper) AddLiquidity(ctx context.Context, msg *whaleswapv1.MsgAddLiquidity) (*whaleswapv1.MsgAddLiquidityResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("AddLiquidity starting", "pool_id", msg.PoolId, "signer", msg.Signer, "amounts", msg.Amounts)

	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", msg.PoolId)
	}
	logger.Info("\t loaded pool", "pool_id", pool.PoolId, "reserves", pool.Coins, "shares_denom", pool.SharesDenom)
	signer, err := k.addr(ctx, msg.Signer)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}
	if err := k.ensureMajorityOwner(ctx, pool, signer); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to compute liquidity for reserves")
	}
	if len(pool.Coins) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
	}

	// Sanitize user-provided repeated coin vectors for amounts
	msg.Amounts = sdk.NewCoins(msg.Amounts...)
	// Validate amounts: must have exactly 2 denoms matching pool (already sorted)
	if len(msg.Amounts) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "must provide exactly 2 denoms")
	}
	if !msg.Amounts.IsValid() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "amounts must be valid sorted coins")
	}
	if msg.Amounts[0].Denom != pool.Coins[0].Denom || msg.Amounts[1].Denom != pool.Coins[1].Denom {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "amount denoms must match pool denoms in canonical order: expected %s,%s got %s,%s", pool.Coins[0].Denom, pool.Coins[1].Denom, msg.Amounts[0].Denom, msg.Amounts[1].Denom)
	}
	if !msg.Amounts[0].IsPositive() || !msg.Amounts[1].IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "amounts must be > 0")
	}

	exR1 := pool.Coins[0]
	exR2 := pool.Coins[1]
	logger.Info("AddLiquidity current reserves", "r1", exR1, "r2", exR2)
	if !exR1.IsPositive() || !exR2.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
	}

	add1 := msg.Amounts[0]
	add2 := msg.Amounts[1]
	orig1 := add1.Amount
	orig2 := add2.Amount
	refund1 := math.NewInt(0)
	refund2 := math.NewInt(0)

	totalShares := k.bank.GetSupply(ctx, pool.SharesDenom).Amount
	if !totalShares.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid total shares supply")
	}

	s1 := add1.Amount.ToLegacyDec().MulInt(totalShares).Quo(exR1.Amount.ToLegacyDec()).TruncateInt()
	s2 := add2.Amount.ToLegacyDec().MulInt(totalShares).Quo(exR2.Amount.ToLegacyDec()).TruncateInt()
	minted := s1
	if s2.LT(s1) {
		minted = s2
	}
	if !minted.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "shares must be > 0")
	}

	req1 := math.LegacyNewDecFromInt(minted).MulInt(exR1.Amount).QuoInt(totalShares).Ceil().TruncateInt()
	req2 := math.LegacyNewDecFromInt(minted).MulInt(exR2.Amount).QuoInt(totalShares).Ceil().TruncateInt()
	if req1.IsNegative() || req2.IsNegative() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid required amounts")
	}
	if req1.GT(orig1) || req2.GT(orig2) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "insufficient provided amounts for minted shares")
	}

	refund1 = orig1.Sub(req1)
	refund2 = orig2.Sub(req2)
	add1 = sdk.NewCoin(add1.Denom, req1)
	add2 = sdk.NewCoin(add2.Denom, req2)

	// Escrow the full user-provided amounts, then refund the unused difference.
	escrow1 := sdk.NewCoin(exR1.Denom, orig1)
	escrow2 := sdk.NewCoin(exR2.Denom, orig2)
	logger.Info("AddLiquidity escrow/refund before moves", "escrow1", escrow1, "escrow2", escrow2, "refund1", sdk.NewCoin(exR1.Denom, refund1), "refund2", sdk.NewCoin(exR2.Denom, refund2))
	if err := k.sendToModule(ctx, signer, sdk.NewCoins(escrow1, escrow2)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to escrow adds %s,%s", escrow1.String(), escrow2.String())
	}
	refunds := sdk.NewCoins()
	if refund1.IsPositive() {
		refunds = refunds.Add(sdk.NewCoin(exR1.Denom, refund1))
	}
	if refund2.IsPositive() {
		refunds = refunds.Add(sdk.NewCoin(exR2.Denom, refund2))
	}
	if !refunds.Empty() {
		if err := k.sendFromModule(ctx, signer, refunds); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to refund %s", refunds.String())
		}
		logger.Info("AddLiquidity refunds sent", "refunds", refunds)
	}

	pool.Coins = sdk.NewCoins(exR1.Add(add1), exR2.Add(add2))
	logger.Info("AddLiquidity new reserves", "r1", pool.Coins[0], "r2", pool.Coins[1])

	// Persist and emit poolupdate
	if err := k.updatePool(ctx, &pool); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update pool %d after add", pool.PoolId)
	}
	logger.Info("AddLiquidity pool updated", "pool_id", pool.PoolId)

	mintMsg := &nameservicev1.MsgMintCoins{
		NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(),
		Amount:          sdk.NewCoins(sdk.NewCoin(pool.SharesDenom, minted)),
		MintFee:         sdk.NewCoin(whaleswapv1.MintFeeDenom, math.NewInt(0)),
	}
	if _, err := k.nameSvc.MintCoins(ctx, mintMsg); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to mint shares %s", sdk.NewCoin(pool.SharesDenom, minted).String())
	}
	if err := k.sendFromModule(ctx, signer, sdk.NewCoins(sdk.NewCoin(pool.SharesDenom, minted))); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send shares %s to %s", sdk.NewCoin(pool.SharesDenom, minted).String(), msg.Signer)
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolLiquidityAdded{PoolId: pool.PoolId, Shares: minted.String()}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPoolLiquidityAdded")
	}
	logger.Info("AddLiquidity emitted EventPoolLiquidityAdded", "pool_id", pool.PoolId, "shares", minted.String())
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err,
			"AMM invariant after AddLiquidity: pool_id=%d add1=%s add2=%s minted=%s newR=(%s,%s)",
			pool.PoolId,
			add1.String(),
			add2.String(),
			minted.String(),
			pool.Coins[0].String(),
			pool.Coins[1].String(),
		)
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after AddLiquidity")
	}
	logger.Info("AddLiquidity completed successfully", "pool_id", pool.PoolId, "minted_shares", minted.String())
	return &whaleswapv1.MsgAddLiquidityResponse{Shares: minted.String()}, nil
}

// RemoveLiquidity removes liquidity from a pool by burning the caller's shares
// and returning the underlying reserves. It supports two modes:
//   - Full exit: if the caller burns all outstanding shares, the pool is
//     deleted and the full reserves are paid out.
//   - Partial exit: the caller burns a subset of shares and receives a payout
//     proportional to that share using pro-rata DecCoins math.
//
// Validation and safety guarantees:
//   - The pool must exist and the signer must hold at least msg.Shares.
//   - Partial exits cannot deplete any reserve; withdrawing the last liquidity
//     requires a full exit.
//
// On success, an EventPoolLiquidityRemoved event is emitted and the updated
// pool state is persisted. Errors are returned; no panics.
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
