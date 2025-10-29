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

func (k Keeper) AddLiquidity(ctx context.Context, msg *whaleswapv1.MsgAddLiquidity) (*whaleswapv1.MsgAddLiquidityResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("AddLiquidity starting", "pool_id", msg.PoolId, "signer", msg.Signer, "amounts", msg.Amounts)

	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", msg.PoolId)
	}
	logger.Info("	 loaded pool", "pool_id", pool.PoolId, "reserves", pool.Coins, "shares_denom", pool.SharesDenom, "bounded", len(pool.MinPrice) == 2)
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
	var dL math.LegacyDec

	if len(pool.MinPrice) == 2 { // concentrated mode
		// compute L contribution based on band math
		L, sa, sb, err := k.liquidityForReserves(pool)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to compute current sqrt price")
		}
		sp, err := k.poolSqrtPrice(pool, exR1.Denom, exR2.Denom)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to compute liquidity for reserves")
		}
		logger.Info("AddLiquidity concentrated math", "sqrt_price", sp.String(), "sa", sa.String(), "sb", sb.String(), "L", L.String())
		// contributions
		// if sp <= sa: only token1 contributes → ΔL = dx * (sa*sb)/(sb-sa)
		// if sp >= sb: only token2 contributes → ΔL = dy / (sb - sa)
		// if sa < sp < sb: ΔL0 from dx and ΔL1 from dy; take min
		one := math.LegacyNewDec(1)
		_ = one // silence linter if unused in this snippet
		dx := add1.Amount.ToLegacyDec()
		dy := add2.Amount.ToLegacyDec()
		// dL will be set by the branch below and later used to mint shares

		// NOTE: Lines 87-96 (boundary conditions sp <= sa and sp >= sb) are unreachable
		// in practice because:
		// 1. Pool creation validates initial price must be strictly within (sa, sb)
		// 2. MsgPoolSwap validates resulting price must remain within [min_price, max_price]
		// These branches are defensive code for edge cases (manual state manipulation,
		// future features, or mathematical completeness). They cannot be triggered via
		// normal AddLiquidity calls following standard pool creation and swaps.
		if sp.LTE(sa) {
			// UNREACHABLE via normal operations: price cannot go below min_price
			dL = dx.Mul(sa).Mul(sb).Quo(sb.Sub(sa))
			// token2 ignored; full refund
			refund2 = add2.Amount
			add2 = sdk.NewCoin(add2.Denom, math.NewInt(0))
		} else if sp.GTE(sb) {
			// UNREACHABLE via normal operations: price cannot go above max_price
			dL = dy.Quo(sb.Sub(sa))
			refund1 = add1.Amount
			add1 = sdk.NewCoin(add1.Denom, math.NewInt(0))
		} else {
			// NORMAL CASE: price within band (sa < sp < sb)
			dL0 := dx.Mul(sp).Mul(sb).Quo(sb.Sub(sp))
			dL1 := dy.Quo(sp.Sub(sa))
			if dL0.LTE(dL1) {
				dL = dL0
				// compute required dy to match dL: dy* = dL * (sp - sa)
				reqDy := dL.Mul(sp.Sub(sa)).TruncateInt()
				if add2.Amount.GT(reqDy) {
					refund2 = add2.Amount.Sub(reqDy)
					add2 = sdk.NewCoin(add2.Denom, reqDy)
				}
			} else {
				dL = dL1
				// compute required dx to match dL: dx* = dL * (sb - sp) / (sp*sb)
				reqDx := dL.Mul(sb.Sub(sp)).Quo(sp.Mul(sb)).TruncateInt()
				if add1.Amount.GT(reqDx) {
					refund1 = add1.Amount.Sub(reqDx)
					add1 = sdk.NewCoin(add1.Denom, reqDx)
				}
			}
		}
		_ = L // L only used for share ratio below
	} else {
		// Non-concentrated: compute refunds after minted via Dec math
		// (escrow/refund happens later after we derive exact used amounts)
	}

	totalShares := k.bank.GetSupply(ctx, pool.SharesDenom).Amount
	var minted math.Int
	if len(pool.MinPrice) == 2 {
		// Δshares = floor(ΔL * totalShares / Lcur)
		Lcur, _, _, err := k.liquidityForReserves(pool)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to compute current sqrt price")
		}
		if !Lcur.IsPositive() {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool liquidity")
		}
		minted = dL.MulInt(totalShares).Quo(Lcur).TruncateInt()
	} else {
		s1 := add1.Amount.ToLegacyDec().MulInt(totalShares).Quo(exR1.Amount.ToLegacyDec()).TruncateInt()
		s2 := add2.Amount.ToLegacyDec().MulInt(totalShares).Quo(exR2.Amount.ToLegacyDec()).TruncateInt()
		minted = s1
		if s2.LT(s1) {
			minted = s2
		}
		// Compute exact required amounts for minted shares using ceil to avoid underfunding
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
	}

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
	if !minted.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "shares must be > 0")
	}
	logger.Info("AddLiquidity minted shares computed", "minted", minted)

	pool.Coins = sdk.NewCoins(exR1.Add(add1), exR2.Add(add2))
	logger.Info("AddLiquidity new reserves", "r1", pool.Coins[0], "r2", pool.Coins[1])

	// Enforce price band after add
	if len(pool.MinPrice) == 2 {
		rBase := pool.Coins[0].Amount
		rQuote := pool.Coins[1].Amount
		minBase := pool.MinPrice.AmountOf(pool.Coins[0].Denom)
		minQuote := pool.MinPrice.AmountOf(pool.Coins[1].Denom)
		maxBase := pool.MaxPrice.AmountOf(pool.Coins[0].Denom)
		maxQuote := pool.MaxPrice.AmountOf(pool.Coins[1].Denom)
		if rQuote.Mul(minBase).LT(rBase.Mul(minQuote)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price below band after add")
		}
		if rQuote.Mul(maxBase).GT(rBase.Mul(maxQuote)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price above band after add")
		}
	}
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

func (k Keeper) RemoveLiquidity(ctx context.Context, msg *whaleswapv1.MsgRemoveLiquidity) (*whaleswapv1.MsgRemoveLiquidityResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("RemoveLiquidity starting", "pool_id", msg.PoolId, "signer", msg.Signer, "shares", msg.Shares)
	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", msg.PoolId)
	}
	logger.Info("RemoveLiquidity loaded pool", "pool_id", pool.PoolId, "reserves", pool.Coins, "shares_denom", pool.SharesDenom, "bounded", len(pool.MinPrice) == 2)
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
	var out1, out2 sdk.Coin
	var Lbefore math.LegacyDec
	var dLExpected math.LegacyDec
	if len(pool.MinPrice) == 2 {
		// Concentrated removal by ΔL
		Lcur, sa, sb, err := k.liquidityForReserves(pool)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to send outputs to signer")
		}
		if !Lcur.IsPositive() {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool liquidity")
		}
		sp, err := k.poolSqrtPrice(pool, pool.Coins[0].Denom, pool.Coins[1].Denom)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to recompute liquidity after remove")
		}
		// record before-state liquidity and expected delta
		Lbefore = Lcur
		dLExpected = Lcur.MulInt(sharesAmt).QuoInt(totalShares)
		dL := dLExpected
		if sp.LTE(sa) {
			// out1 = floor(ΔL * (sb - sa) / (sa*sb)); out2 = 0
			out1 = sdk.NewCoin(pool.Coins[0].Denom, dL.Mul(sb.Sub(sa)).Quo(sa.Mul(sb)).TruncateInt())
			out2 = sdk.NewCoin(pool.Coins[1].Denom, math.NewInt(0))
		} else if sp.GTE(sb) {
			// out1 = 0; out2 = floor(ΔL * (sb - sa))
			out1 = sdk.NewCoin(pool.Coins[0].Denom, math.NewInt(0))
			out2 = sdk.NewCoin(pool.Coins[1].Denom, dL.Mul(sb.Sub(sa)).TruncateInt())
		} else {
			// within band
			out1 = sdk.NewCoin(pool.Coins[0].Denom, dL.Mul(sb.Sub(sp)).Quo(sp.Mul(sb)).TruncateInt())
			out2 = sdk.NewCoin(pool.Coins[1].Denom, dL.Mul(sp.Sub(sa)).TruncateInt())
		}
	} else {
		// Pro-rata removal using DecCoins for robust denom-safe math
		reservesDec := sdk.NewDecCoinsFromCoins(pool.Coins...)
		ratio := math.LegacyNewDecFromInt(sharesAmt).QuoInt(totalShares)
		payoutsDec := reservesDec.MulDecTruncate(ratio)
		payouts, _ := payoutsDec.TruncateDecimal()
		out1 = sdk.NewCoin(pool.Coins[0].Denom, payouts.AmountOf(pool.Coins[0].Denom))
		out2 = sdk.NewCoin(pool.Coins[1].Denom, payouts.AmountOf(pool.Coins[1].Denom))
	}
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
	// L consistency (concentrated mode): ensure L decreases by ~ΔL within tolerance
	if len(pool.MinPrice) == 2 {
		Lafter, _, _, err := k.liquidityForReserves(pool)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to recompute liquidity after remove")
		}
		if Lbefore.IsZero() {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pre-remove liquidity state")
		}
		delta := Lbefore.Sub(Lafter)
		if delta.IsNegative() {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "liquidity increased on remove")
		}
		tol := math.LegacyNewDecWithPrec(1, 6)
		allowed := dLExpected.Mul(math.LegacyOneDec().Add(tol))
		if delta.GT(allowed) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "liquidity delta too large: %s > %s", delta.String(), allowed.String())
		}
	}
	// Prevent reserve depletion on partial exits
	if pool.Coins[0].IsZero() || pool.Coins[1].IsZero() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "would deplete reserve; use full exit to withdraw all liquidity")
	}

	// Enforce price band after remove
	if len(pool.MinPrice) == 2 {
		rBase := pool.Coins[0].Amount
		rQuote := pool.Coins[1].Amount
		denomA, denomB := pool.Coins[0].Denom, pool.Coins[1].Denom
		minBase := pool.MinPrice.AmountOf(denomA)
		minQuote := pool.MinPrice.AmountOf(denomB)
		maxBase := pool.MaxPrice.AmountOf(denomA)
		maxQuote := pool.MaxPrice.AmountOf(denomB)
		if rQuote.Mul(minBase).LT(rBase.Mul(minQuote)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price below band after remove")
		}
		if rQuote.Mul(maxBase).GT(rBase.Mul(maxQuote)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price above band after remove")
		}
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
