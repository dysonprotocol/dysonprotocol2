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

// AddLiquidity (owner-only) escrows provided amounts, refunds any unused
// amounts, mints shares, and asserts AMM invariants.
//
// Behavior:
//   - Loads pool; validates signer majority ownership.
//   - Escrows full provided amounts first, then refunds unused surplus.
//   - Computes shares as floor(min(add1/R1, add2/R2) × totalShares).
//   - Updates pool reserves with used amounts.
//   - Mints computed shares via nameservice and transfers to signer.
//   - Persists pool with updated reserves/timestamp; emits events; asserts AMM
//     and module invariants.
//
// Validation:
//   - Pool must exist and have exactly two positive reserves.
//   - Signer must be valid address and hold majority of pool shares.
//   - Amounts must contain exactly two positive coins matching pool denoms in
//     canonical order.
//
// State Updates:
//   - Transfers provided amounts from signer to module (then refunds surplus).
//   - Updates pool reserves in PoolsMap.
//   - Sets pool.Updated timestamp to current block time.
//   - Mints new shares via nameservice and transfers to signer.
//
// Emits:
//   - EventPoolUpdate (after persisting pool state)
//   - EventPoolLiquidityAdded (pool_id, shares_minted)
//
// Returns:
//   - *whaleswapv1.MsgAddLiquidityResponse with shares minted as decimal string.
//
// Errors are returned on pool not found, invalid signer/ownership, malformed
// amounts (wrong denoms/order, non-positive), insufficient provided amounts for
// share calculation, minting/transfer failures, event emission, or invariant
// violations; no panics.
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
