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
	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", msg.PoolId)
	}
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
	if msg.Amount1.Denom != pool.Coins[0].Denom || msg.Amount2.Denom != pool.Coins[1].Denom {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "amount denoms must match pool denoms")
	}
	if !msg.Amount1.Amount.IsPositive() || !msg.Amount2.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "amounts must be > 0")
	}

	exR1 := pool.Coins[0].Amount
	exR2 := pool.Coins[1].Amount
	if !exR1.IsPositive() || !exR2.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
	}

	add1 := msg.Amount1.Amount
	add2 := msg.Amount2.Amount
	orig1 := add1
	orig2 := add2
	refund1 := math.NewInt(0)
	refund2 := math.NewInt(0)
	var dL math.LegacyDec

	if len(pool.MinPrice) == 2 { // concentrated mode
		// compute L contribution based on band math
		L, sa, sb, err := k.liquidityForReserves(pool)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to compute current sqrt price")
		}
		sp, err := k.poolSqrtPrice(pool, pool.Coins[0].Denom, pool.Coins[1].Denom)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to compute liquidity for reserves")
		}
		// contributions
		// if sp <= sa: only token1 contributes → ΔL = dx * (sa*sb)/(sb-sa)
		// if sp >= sb: only token2 contributes → ΔL = dy / (sb - sa)
		// if sa < sp < sb: ΔL0 from dx and ΔL1 from dy; take min
		one := math.LegacyNewDec(1)
		_ = one // silence linter if unused in this snippet
		dx := math.LegacyNewDecFromInt(add1)
		dy := math.LegacyNewDecFromInt(add2)
		// dL will be set by the branch below and later used to mint shares
		if sp.LTE(sa) {
			dL = dx.Mul(sa).Mul(sb).Quo(sb.Sub(sa))
			// token2 ignored; full refund
			refund2 = add2
			add2 = math.NewInt(0)
		} else if sp.GTE(sb) {
			dL = dy.Quo(sb.Sub(sa))
			refund1 = add1
			add1 = math.NewInt(0)
		} else {
			dL0 := dx.Mul(sp).Mul(sb).Quo(sb.Sub(sp))
			dL1 := dy.Quo(sp.Sub(sa))
			if dL0.LTE(dL1) {
				dL = dL0
				// compute required dy to match dL: dy* = dL * (sp - sa)
				reqDy := dL.Mul(sp.Sub(sa)).TruncateInt()
				if add2.GT(reqDy) {
					refund2 = add2.Sub(reqDy)
					add2 = reqDy
				}
			} else {
				dL = dL1
				// compute required dx to match dL: dx* = dL * (sb - sp) / (sp*sb)
				reqDx := dL.Mul(sb.Sub(sp)).Quo(sp.Mul(sb)).TruncateInt()
				if add1.GT(reqDx) {
					refund1 = add1.Sub(reqDx)
					add1 = reqDx
				}
			}
		}
		_ = L // L only used for share ratio below
	} else {
		targetA2 := add1.Mul(exR2).Add(exR1.Sub(math.NewInt(1))).Quo(exR1)
		if add2.GT(targetA2) {
			refund2 = add2.Sub(targetA2)
			add2 = targetA2
		} else if add2.LT(targetA2) {
			targetA1 := add2.Mul(exR1).Add(exR2.Sub(math.NewInt(1))).Quo(exR2)
			if add1.GT(targetA1) {
				refund1 = add1.Sub(targetA1)
				add1 = targetA1
			}
		}
	}

	// Escrow the full user-provided amounts, then refund the unused difference.
	if err := k.sendToModule(ctx, signer, sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, orig1), sdk.NewCoin(pool.Coins[1].Denom, orig2))); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to escrow adds %s,%s", sdk.NewCoin(pool.Coins[0].Denom, orig1).String(), sdk.NewCoin(pool.Coins[1].Denom, orig2).String())
	}
	refunds := sdk.NewCoins()
	if refund1.IsPositive() {
		refunds = refunds.Add(sdk.NewCoin(pool.Coins[0].Denom, refund1))
	}
	if refund2.IsPositive() {
		refunds = refunds.Add(sdk.NewCoin(pool.Coins[1].Denom, refund2))
	}
	if !refunds.Empty() {
		if err := k.sendFromModule(ctx, signer, refunds); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to refund %s", refunds.String())
		}
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
		s1 := math.LegacyNewDecFromInt(add1).MulInt(totalShares).Quo(math.LegacyNewDecFromInt(exR1)).TruncateInt()
		s2 := math.LegacyNewDecFromInt(add2).MulInt(totalShares).Quo(math.LegacyNewDecFromInt(exR2)).TruncateInt()
		minted = s1
		if s2.LT(s1) {
			minted = s2
		}
	}
	if !minted.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "shares must be > 0")
	}

	pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, exR1.Add(add1)), sdk.NewCoin(pool.Coins[1].Denom, exR2.Add(add2)))

	// Enforce price band after add
	if len(pool.MinPrice) == 2 {
		rBase := pool.Coins.AmountOf(pool.Coins[0].Denom)
		rQuote := pool.Coins.AmountOf(pool.Coins[1].Denom)
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
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolLiquidityAdded{PoolId: pool.PoolId, Shares: minted.String()}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPoolLiquidityAdded")
	}
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err,
			"AMM invariant after AddLiquidity: pool_id=%d add1=%s add2=%s minted=%s newR=(%s,%s)",
			pool.PoolId,
			sdk.NewCoin(pool.Coins[0].Denom, add1).String(),
			sdk.NewCoin(pool.Coins[1].Denom, add2).String(),
			minted.String(),
			sdk.NewCoin(pool.Coins[0].Denom, pool.Coins[0].Amount).String(),
			sdk.NewCoin(pool.Coins[1].Denom, pool.Coins[1].Amount).String(),
		)
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after AddLiquidity")
	}
	return &whaleswapv1.MsgAddLiquidityResponse{Shares: minted.String()}, nil
}

func (k Keeper) RemoveLiquidity(ctx context.Context, msg *whaleswapv1.MsgRemoveLiquidity) (*whaleswapv1.MsgRemoveLiquidityResponse, error) {
	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", msg.PoolId)
	}
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
		out1 := pool.Coins.AmountOf(pool.Coins[0].Denom)
		out2 := pool.Coins.AmountOf(pool.Coins[1].Denom)
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
			outs = outs.Add(sdk.NewCoin(pool.Coins[0].Denom, out1))
		}
		if out2.IsPositive() {
			outs = outs.Add(sdk.NewCoin(pool.Coins[1].Denom, out2))
		}
		if !outs.Empty() {
			if err := k.sendFromModule(ctx, signer, outs); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to burn shares from module")
			}
		}
		sdkCtx := sdk.UnwrapSDKContext(ctx)
		_ = sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolLiquidityRemoved{PoolId: pool.PoolId, Shares: sharesAmt.String()})
		return &whaleswapv1.MsgRemoveLiquidityResponse{Amount: outs}, nil
	}
	var out1, out2 math.Int
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
			out1 = dL.Mul(sb.Sub(sa)).Quo(sa.Mul(sb)).TruncateInt()
			out2 = math.NewInt(0)
		} else if sp.GTE(sb) {
			// out1 = 0; out2 = floor(ΔL * (sb - sa))
			out1 = math.NewInt(0)
			out2 = dL.Mul(sb.Sub(sa)).TruncateInt()
		} else {
			// within band
			out1 = dL.Mul(sb.Sub(sp)).Quo(sp.Mul(sb)).TruncateInt()
			out2 = dL.Mul(sp.Sub(sa)).TruncateInt()
		}
	} else {
		r1 := math.LegacyNewDecFromInt(pool.Coins[0].Amount)
		r2 := math.LegacyNewDecFromInt(pool.Coins[1].Amount)
		out1 = r1.MulInt(sharesAmt).QuoInt(totalShares).TruncateInt()
		out2 = r2.MulInt(sharesAmt).QuoInt(totalShares).TruncateInt()
	}
	if !out1.IsPositive() && !out2.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "shares too small to exit")
	}
	if err := k.sendToModule(ctx, signer, sdk.NewCoins(sdk.NewCoin(pool.SharesDenom, sharesAmt))); err != nil {
		return nil, err
	}
	if err := k.burnModule(ctx, sdk.NewCoins(sdk.NewCoin(pool.SharesDenom, sharesAmt))); err != nil {
		return nil, err
	}
	dR1 := math.LegacyNewDecFromInt(pool.Coins[0].Amount)
	dR2 := math.LegacyNewDecFromInt(pool.Coins[1].Amount)
	newA := dR1.Sub(math.LegacyNewDecFromInt(out1)).TruncateInt()
	newB := dR2.Sub(math.LegacyNewDecFromInt(out2)).TruncateInt()
	if !newA.IsPositive() || !newB.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "would deplete reserve")
	}
	// Apply updates
	pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, newA), sdk.NewCoin(pool.Coins[1].Denom, newB))
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
	if pool.Coins[0].Amount.IsZero() || pool.Coins[1].Amount.IsZero() {
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
	outs := sdk.NewCoins()
	if out1.IsPositive() {
		outs = outs.Add(sdk.NewCoin(pool.Coins[0].Denom, out1))
	}
	if out2.IsPositive() {
		outs = outs.Add(sdk.NewCoin(pool.Coins[1].Denom, out2))
	}
	if err := k.sendFromModule(ctx, signer, outs); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send outputs %s to %s", outs.String(), msg.Signer)
	}
	sdkCtx2 := sdk.UnwrapSDKContext(ctx)
	if err := sdkCtx2.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolLiquidityRemoved{PoolId: pool.PoolId, Shares: sharesAmt.String()}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPoolLiquidityRemoved")
	}
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err,
			"AMM invariant after RemoveLiquidity: pool_id=%d burn_shares=%s out=(%s,%s) newR=(%s,%s)",
			pool.PoolId,
			sharesAmt.String(),
			sdk.NewCoin(pool.Coins[0].Denom, out1).String(),
			sdk.NewCoin(pool.Coins[1].Denom, out2).String(),
			sdk.NewCoin(pool.Coins[0].Denom, pool.Coins[0].Amount).String(),
			sdk.NewCoin(pool.Coins[1].Denom, pool.Coins[1].Amount).String(),
		)
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after RemoveLiquidity")
	}
	return &whaleswapv1.MsgRemoveLiquidityResponse{Amount: outs}, nil
}
