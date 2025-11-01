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

// CreatePool creates a two-asset pool with per-denom fee/interest/leverage
// parameters and optional directional bound_percent limits.
//
// Semantics:
//   - Input normalization: canonicalizes msg.Coins (exactly two positive coins) to
//     the pool's denom order.
//   - Fees and rates: normalizes fee_rate and interest_rate to exactly two
//     DecCoins in pool order; requires 0 <= fee_rate < 1 per denom and
//     interest_rate >= 0 per denom.
//   - Leverage configuration (required): validates min_collateral_ratio and
//     max_leverage_ratio have exactly two entries (> 1) matching pool denoms;
//     validates liquidation_threshold has exactly two entries (> 1) and
//     max_borrow_percent has exactly two entries with amounts in [0,1).
//   - Bound percent (optional): when omitted defaults to 1 (unbounded) for both
//     denoms. When provided, must contain exactly two DecCoins matching pool
//     denoms with amounts in (0,1]; 1 disables the bound for that denom.
//   - Funds and shares: sends initial reserves from creator → module; allocates
//     a new pool id; persists the pool; computes initial shares as
//     floor(sqrt(x*y)); ensures at least 1 share; mints pool shares under the
//     name service into the module and sends the minted shares to the creator.
//   - Invariants: asserts AMM invariants (AssertAMMInvariants) and module
//     invariants (AssertInvariants) before returning.
//
// Validation:
//   - msg.Coins must contain exactly two positive coins with valid denoms.
//   - Fee rates must satisfy 0 <= x < 1 for both denoms when provided.
//   - Interest rates must be >= 0 for both denoms when provided.
//   - Leverage config (min_collateral_ratio, max_leverage_ratio) must have
//     exactly two entries (> 1) matching pool denoms in canonical order.
//   - Liquidation threshold must have exactly two entries (> 1) matching pool
//     denoms in canonical order.
//   - Max borrow percent must have exactly two entries with amounts in [0,1)
//     matching pool denoms in canonical order.
//   - Bound percent when provided must contain at most two entries with amounts
//     in (0,1] matching pool denoms.
//
// State Updates:
//   - Allocates new pool ID from sequence.
//   - Persists pool with all configuration to PoolsMap.
//   - Transfers initial reserves from creator to module account.
//   - Mints initial shares via nameservice and transfers to creator.
//   - Updates pool accounting (reserves, shares supply).
//
// Emits:
//   - EventPoolCreated with pool_id
//   - EventPoolUpdate with pool_id
//
// Returns:
//   - *whaleswapv1.MsgCreatePoolResponse with pool_id of the newly created pool.
//
// Errors are returned on validation failures (invalid coins, fees/rates,
// leverage/threshold/cap vectors), address resolution, bank sends, minting
// shares, sequence allocation, or invariant violations; no panics.
func (k Keeper) CreatePool(ctx context.Context, msg *whaleswapv1.MsgCreatePool) (*whaleswapv1.MsgCreatePoolResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)

	logger.Info("CreatePool starting", "creator", msg.Creator, "coins", msg.Coins, "fee_rate", msg.FeeRate, "bound_percent", msg.BoundPercent)

	if len(msg.Coins) != 2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "coins must contain exactly 2 entries, got %d", len(msg.Coins))
	}

	logger.Info("CreatePool sorting/validating inputs")
	// Sanitize user-provided repeated coin vectors to ensure canonical order and no zero coins.
	msg.Coins = sdk.NewCoins(msg.Coins...)
	err := msg.Coins.Validate()
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid coins: %v", err)
	}
	denom1, denom2 := msg.Coins[0].Denom, msg.Coins[1].Denom
	logger.Info("CreatePool canonicalized denoms", "denom1", denom1, "denom2", denom2)

	// Pools accept only solid denoms; wrappers removed

	// BoundPercent: optional; default to 1 (unbounded) per denom; when provided must
	// contain at most two entries matching pool denoms with amounts in (0,1].
	one := math.LegacyNewDec(1)
	zero := math.LegacyZeroDec()
	if len(msg.BoundPercent) > 2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "bound_percent supports at most two entries, got %d", len(msg.BoundPercent))
	}
	seenBounds := make(map[string]struct{}, len(msg.BoundPercent))
	for _, bc := range msg.BoundPercent {
		if bc.Denom != denom1 && bc.Denom != denom2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "bound_percent denom %s must match pool denoms [%s,%s]", bc.Denom, denom1, denom2)
		}
		if _, exists := seenBounds[bc.Denom]; exists {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "duplicate bound_percent entry for denom %s", bc.Denom)
		}
		seenBounds[bc.Denom] = struct{}{}
		if !bc.Amount.GT(zero) || bc.Amount.GT(one) {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "bound_percent amounts must satisfy 0 < x <= 1 for provided denoms")
		}
	}
	bounds := sdk.NewDecCoins(msg.BoundPercent...)
	b1 := bounds.AmountOf(denom1)
	b2 := bounds.AmountOf(denom2)
	if b1.IsZero() {
		b1 = one
	}
	if b2.IsZero() {
		b2 = one
	}
	msg.BoundPercent = sdk.DecCoins{
		sdk.NewDecCoinFromDec(denom1, b1),
		sdk.NewDecCoinFromDec(denom2, b2),
	}

	// FeeRate: allow 0, 1, or 2 entries. Normalize using DecCoins helpers and store exactly two entries.
	// one already defined above
	inFee := sdk.NewDecCoins(msg.FeeRate...)
	fr1 := inFee.AmountOf(denom1)
	fr2 := inFee.AmountOf(denom2)
	if fr1.IsNegative() || !fr1.LT(one) || fr2.IsNegative() || !fr2.LT(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "fee_rate amounts must satisfy 0 <= x < 1 for both denoms")
	}
	// Use slice literal to preserve two entries even when zero
	msg.FeeRate = sdk.DecCoins{
		sdk.NewDecCoinFromDec(denom1, fr1),
		sdk.NewDecCoinFromDec(denom2, fr2),
	}

	// Validate leverage configuration fields (required; per-denom DecCoins)
	inMinCR := sdk.NewDecCoins(msg.MinCollateralRatio...)
	if len(inMinCR) != 2 || inMinCR[0].Denom != denom1 || inMinCR[1].Denom != denom2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_collateral_ratio must have exactly two entries matching pool denoms [%s,%s] in canonical order", denom1, denom2)
	}
	if inMinCR[0].Amount.LTE(one) || inMinCR[1].Amount.LTE(one) { // require strictly > 1
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "min_collateral_ratio amounts must be > 1 for both denoms")
	}
	msg.MinCollateralRatio = inMinCR

	inMaxLev := sdk.NewDecCoins(msg.MaxLeverageRatio...)
	if len(inMaxLev) != 2 || inMaxLev[0].Denom != denom1 || inMaxLev[1].Denom != denom2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_leverage_ratio must have exactly two entries matching pool denoms [%s,%s] in canonical order", denom1, denom2)
	}
	if inMaxLev[0].Amount.LTE(one) || inMaxLev[1].Amount.LTE(one) { // require strictly > 1
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "max_leverage_ratio amounts must be > 1 for both denoms")
	}
	msg.MaxLeverageRatio = inMaxLev

	// Liquidation threshold: required and must be > 1 (per-denom DecCoins)
	inLiq := sdk.NewDecCoins(msg.LiquidationThreshold...)
	if len(inLiq) != 2 || inLiq[0].Denom != denom1 || inLiq[1].Denom != denom2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "liquidation_threshold must have exactly two entries matching pool denoms [%s,%s] in canonical order", denom1, denom2)
	}
	if inLiq[0].Amount.LTE(one) || inLiq[1].Amount.LTE(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "liquidation_threshold amounts must be > 1 for both denoms")
	}
	msg.LiquidationThreshold = inLiq

	// InterestRate: allow 0, 1, or 2 entries. Normalize using DecCoins helpers and store exactly two entries.
	inIR := sdk.NewDecCoins(msg.InterestRate...)
	ir1 := inIR.AmountOf(denom1)
	ir2 := inIR.AmountOf(denom2)
	if ir1.IsNegative() || ir2.IsNegative() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "interest_rate amounts must be >= 0")
	}
	msg.InterestRate = sdk.DecCoins{
		sdk.NewDecCoinFromDec(denom1, ir1),
		sdk.NewDecCoinFromDec(denom2, ir2),
	}

	// MaxBorrowPercent: required; exactly two DecCoins matching pool denoms; amounts in [0,1)
	if len(msg.MaxBorrowPercent) != 2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_borrow_percent must have exactly 2 entries")
	}
	msg.MaxBorrowPercent = sdk.NewDecCoins(msg.MaxBorrowPercent...)
	if msg.MaxBorrowPercent[0].Denom != denom1 || msg.MaxBorrowPercent[1].Denom != denom2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_borrow_percent denoms must match pool coins in canonical order: want [%s,%s]", denom1, denom2)
	}
	if msg.MaxBorrowPercent[0].Amount.IsNegative() || msg.MaxBorrowPercent[0].Amount.GTE(one) ||
		msg.MaxBorrowPercent[1].Amount.IsNegative() || msg.MaxBorrowPercent[1].Amount.GTE(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "max_borrow_percent amounts must satisfy 0 <= x < 1")
	}

	if len(msg.Coins) != 2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "coins must have exactly 2 coins")
	}

	if msg.Coins[0].Amount.IsZero() || msg.Coins[1].Amount.IsZero() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "initial reserves must be positive: msg: %+v coins: %+v", msg, msg.Coins)
	}

	from, err := k.addr(ctx, msg.Creator)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get creator address: %s", msg.Creator)
	}

	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	beforeBal1 := k.bank.GetBalance(ctx, moduleAddr, denom1).Amount
	beforeBal2 := k.bank.GetBalance(ctx, moduleAddr, denom2).Amount
	logger.Info("CreatePool sending funds to module", "creator_addr", from, "coins", msg.Coins,
		"module_before_denom1", beforeBal1.String(), "module_before_denom2", beforeBal2.String())
	if err := k.sendToModule(ctx, from, msg.Coins); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send funds to module: %s: %+v", from.String(), msg)
	}
	afterBal1 := k.bank.GetBalance(ctx, moduleAddr, denom1).Amount
	afterBal2 := k.bank.GetBalance(ctx, moduleAddr, denom2).Amount
	logger.Info("CreatePool module balances after fund transfer", "module_after_denom1", afterBal1.String(), "module_after_denom2", afterBal2.String())

	logger.Info("CreatePool allocating pool ID")
	id, err := k.poolSeq.Next(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to allocate new pool id: %+v", msg)
	}
	logger.Info("CreatePool allocated pool ID", "pool_id", id)
	sharesDenom := whaleswapv1.PoolSharesDenom(id)

	t := sdkCtx.BlockTime()
	pool := whaleswapv1.Pool{
		PoolId:               id,
		Coins:                msg.Coins,
		SharesDenom:          sharesDenom,
		FeeRate:              msg.FeeRate,
		BoundPercent:         msg.BoundPercent,
		BlockHeight:          uint64(sdkCtx.BlockHeight()),
		Created:              &t,
		Updated:              &t,
		NumTrades:            0,
		MinCollateralRatio:   msg.MinCollateralRatio,
		MaxLeverageRatio:     msg.MaxLeverageRatio,
		LiquidationThreshold: msg.LiquidationThreshold,
		InterestRate:         msg.InterestRate,
		MaxBorrowPercent:     msg.MaxBorrowPercent,
	}

	logger.Info("CreatePool calculating initial shares (constant-product)")
	prod := math.LegacyNewDecFromInt(msg.Coins[0].Amount).Mul(math.LegacyNewDecFromInt(msg.Coins[1].Amount))
	sqrt, err := prod.ApproxSqrt()
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to compute sqrt of initial product: %+v", msg)
	}
	initialShares := sqrt.TruncateInt()
	logger.Info("CreatePool calculated liquidity", "initial_shares", initialShares, "product", prod, "sqrt", sqrt)
	if !initialShares.IsPositive() {
		initialShares = math.NewInt(1)
		logger.Info("CreatePool adjusted initial shares to minimum", "initial_shares", initialShares)
	}

	logger.Info("CreatePool saving pool", "pool_id", id, "shares_denom", sharesDenom)
	if err := k.PoolsMap.Set(ctx, id, pool); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set pool: %+v", msg)
	}

	if err := k.ensureWhaleswapRootName(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed ensuring whaleswap.dys root before minting shares for pool %d: %+v", id, msg)
	}

	logger.Info("CreatePool minting shares", "shares_denom", sharesDenom, "initial_shares", initialShares)
	mintMsg := &nameservicev1.MsgMintCoins{
		NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(),
		Amount:          sdk.NewCoins(sdk.NewCoin(sharesDenom, initialShares)),
		MintFee:         sdk.NewCoin(whaleswapv1.MintFeeDenom, math.NewInt(0)),
	}
	if _, err := k.nameSvc.MintCoins(ctx, mintMsg); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to mint shares: %+v", msg)
	}

	logger.Info("CreatePool sending shares to creator", "creator_addr", from, "shares_amount", initialShares)
	if err := k.sendFromModule(ctx, from, sdk.NewCoins(sdk.NewCoin(sharesDenom, initialShares))); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send minted shares: %+v", msg)
	}

	logger.Info("CreatePool emitting events", "pool_id", id)
	sdkCtx.EventManager().EmitTypedEvents(
		&whaleswapv1.EventPoolCreated{PoolId: id},
		&whaleswapv1.EventPoolUpdate{PoolId: id},
	)

	// Snapshot module balances just before invariants
	snapBal1 := k.bank.GetBalance(ctx, moduleAddr, denom1).Amount
	snapBal2 := k.bank.GetBalance(ctx, moduleAddr, denom2).Amount
	logger.Info("CreatePool checking AMM invariants", "module_bal_denom1", snapBal1.String(), "module_bal_denom2", snapBal2.String())
	if err := k.AssertAMMInvariants(ctx); err != nil {
		logger.Error("CreatePool AMM invariant check failed", "error", err)
		return nil, cosmossdkerrors.Wrapf(err, "AMM invariant failed after CreatePool: pool_id=%d coins=%s shares_denom=%s", id, msg.Coins.String(), sharesDenom)
	}

	logger.Info("CreatePool checking invariants")
	if err := k.AssertInvariants(ctx); err != nil {
		logger.Error("CreatePool invariant check failed", "error", err)
		return nil, cosmossdkerrors.Wrapf(err, "invariant after CreatePool")
	}

	logger.Info("CreatePool completed successfully", "pool_id", id)
	return &whaleswapv1.MsgCreatePoolResponse{PoolId: id}, nil
}
