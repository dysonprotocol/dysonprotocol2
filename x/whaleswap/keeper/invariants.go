package keeper

import (
	"context"
	"strings"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// AssertInvariants checks orderbook escrow and pfand invariants.
// - Sum(escrowed have by open normal offers) == module balances per denom
// - Sum(pfand_locked by open liquid offers) == module pfand balance (per denom)
func (k Keeper) AssertInvariants(ctx context.Context) error {
	// Unified whaleswap module balance invariant with explicit breakdown
	if err := k.checkModuleBalancesInvariant(ctx); err != nil {
		return err
	}
	return nil
}

// checkModuleBalancesInvariant verifies that the whaleswap module account balances equal the
// sum of all expected components managed by the module (AMM reserves + escrowed have + pfand locked)
// for every denom, with no deficit or excess. Any mismatch is an invariant failure with a detailed breakdown.
func (k Keeper) checkModuleBalancesInvariant(ctx context.Context) error {
	ammRequired, err := k.tallyAMMReserves(ctx)
	if err != nil {
		return err
	}
	escrowRequired, err := k.tallyEscrowRequired(ctx)
	if err != nil {
		return err
	}
	pfandRequired, err := k.tallyPfandRequired(ctx)
	if err != nil {
		return err
	}
	auctionRequired, err := k.tallyAuctionRequired(ctx)
	if err != nil {
		return err
	}

	// Leverage components (only collateral affects module balances; held/borrowed are not bank movements)
	leverageCollateral, _, _, err := k.tallyLeveragePositions(ctx)
	if err != nil {
		return err
	}

	// Actual module balances (AMM reserves and internal escrows) — exclude vaults
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	actual := k.bank.SpendableCoins(ctx, moduleAddr)

	// Logging snapshot for diagnostics
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("Invariant snapshot: module balances", "module", moduleAddr.String(), "balances", actual.String())
	logger.Info("Invariant snapshot: components", "amm", ammRequired.String(), "escrow", escrowRequired.String(), "auction", auctionRequired.String(), "pfand", pfandRequired.String())

	// Hard constraints: module must not hold pool share denoms
	for _, c := range actual {
		d := c.Denom
		if strings.HasPrefix(d, whaleswapv1.PoolsDenomPrefix) && c.Amount.IsPositive() {
			return cosmossdkerrors.Wrapf(
				sdkerrors.ErrLogic,
				"module holds pool shares unexpectedly: %s=%s",
				d, c.Amount.String(),
			)
		}
	}
	// Build expected totals per denom including leverage collateral.
	// expected[d] = ammRequired[d] + escrowRequired[d] + auctionRequired[d] + pfandRequired[d] + leverageCollateral[d]

	// No special-casing PFAND here: it's already included in pfandRequired and
	// therefore in 'expected'. Per-denom equality below covers all pfand denoms
	// that exist across open offers (supports historical changes to pfand params).

	// Actual module balances (spendable equals total for module accounts)
	// reuse moduleAddr and actual from above

	// Compare per-denom for exact equality; any deficit or excess is an invariant failure
	denomSet := map[string]struct{}{}
	for _, c := range ammRequired {
		denomSet[c.Denom] = struct{}{}
	}
	for _, c := range escrowRequired {
		denomSet[c.Denom] = struct{}{}
	}
	for _, c := range pfandRequired {
		denomSet[c.Denom] = struct{}{}
	}
	for _, c := range auctionRequired {
		denomSet[c.Denom] = struct{}{}
	}
	for _, c := range leverageCollateral {
		denomSet[c.Denom] = struct{}{}
	}
	for _, c := range actual {
		denomSet[c.Denom] = struct{}{}
	}
	for denom := range denomSet {
		// Compute expected per denom with leverage collateral
		amm := ammRequired.AmountOf(denom)
		esc := escrowRequired.AmountOf(denom)
		pfd := pfandRequired.AmountOf(denom)
		auc := auctionRequired.AmountOf(denom)
		coll := leverageCollateral.AmountOf(denom)
		exp := amm.Add(esc).Add(auc).Add(pfd).Add(coll)
		act := actual.AmountOf(denom)
		if !act.Equal(exp) {
			logger.Info("Invariant mismatch detail", "denom", denom, "have", act.String(), "expected", exp.String(), "amm", amm.String(), "escrow", esc.String(), "auction", auc.String(), "pfand", pfd.String(), "collateral", coll.String())
			return cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"module balance mismatch for %s: have=%s expected=%s (amm=%s escrow=%s auction=%s pfand=%s collateral=%s)",
				denom, act.String(), exp.String(), amm.String(), esc.String(), auc.String(), pfd.String(), coll.String())
		}
	}
	return nil
}

// tallyLeveragePositions aggregates leverage-related coin components across all open positions.
// Returns (collateral, held, borrowed) per denom.
func (k Keeper) tallyLeveragePositions(ctx context.Context) (sdk.Coins, sdk.Coins, sdk.Coins, error) {
	collReq := map[string]math.Int{}
	heldReq := map[string]math.Int{}
	borrReq := map[string]math.Int{}

	if err := k.LeveragePositions.Walk(ctx, nil, func(_ uint64, pos whaleswapv1.LeveragePosition) (bool, error) {
		if pos.Status != whaleswapv1.PositionStatus_POSITION_STATUS_OPEN && pos.Status != whaleswapv1.PositionStatus_POSITION_STATUS_LIQUIDATING {
			return false, nil
		}
		if pos.Collateral.Amount.IsPositive() {
			d := pos.Collateral.Denom
			if cur, ok := collReq[d]; ok {
				collReq[d] = cur.Add(pos.Collateral.Amount)
			} else {
				collReq[d] = pos.Collateral.Amount
			}
		}
		if pos.Held.Amount.IsPositive() {
			d := pos.Held.Denom
			if cur, ok := heldReq[d]; ok {
				heldReq[d] = cur.Add(pos.Held.Amount)
			} else {
				heldReq[d] = pos.Held.Amount
			}
		}
		if pos.Borrowed.Amount.IsPositive() {
			d := pos.Borrowed.Denom
			if cur, ok := borrReq[d]; ok {
				borrReq[d] = cur.Add(pos.Borrowed.Amount)
			} else {
				borrReq[d] = pos.Borrowed.Amount
			}
		}
		return false, nil
	}); err != nil {
		return nil, nil, nil, cosmossdkerrors.Wrap(err, "walk leverage positions")
	}

	toCoins := func(m map[string]math.Int) sdk.Coins {
		out := sdk.NewCoins()
		for d, v := range m {
			if v.IsPositive() {
				out = out.Add(sdk.NewCoin(d, v))
			}
		}
		return out
	}

	return toCoins(collReq), toCoins(heldReq), toCoins(borrReq), nil
}

func (k Keeper) tallyAuctionRequired(ctx context.Context) (sdk.Coins, error) {
	required := sdk.NewCoins()
	if err := k.AuctionsMap.Walk(ctx, nil, func(_ uint64, a whaleswapv1.AuctionRecord) (bool, error) {
		if a.Sell.Amount.IsPositive() {
			required = required.Add(a.Sell)
		}
		return false, nil
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "walk auctions")
	}
	return required, nil
}

func (k Keeper) tallyAMMReserves(ctx context.Context) (sdk.Coins, error) {
	required := map[string]math.Int{}
	if err := k.PoolsMap.Walk(ctx, nil, func(_ uint64, p whaleswapv1.Pool) (bool, error) {
		for _, c := range p.Coins {
			if cur, ok := required[c.Denom]; ok {
				required[c.Denom] = cur.Add(c.Amount)
			} else {
				required[c.Denom] = c.Amount
			}
		}
		return false, nil
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "walk pools")
	}
	out := sdk.NewCoins()
	for d, v := range required {
		if v.IsPositive() {
			out = out.Add(sdk.NewCoin(d, v))
		}
	}
	return out, nil
}

func (k Keeper) tallyEscrowRequired(ctx context.Context) (sdk.Coins, error) {
	required := map[string]math.Int{}
	if err := k.OffersMap.Walk(ctx, nil, func(_ uint64, o whaleswapv1.OfferData) (bool, error) {
		if o.Status != whaleswapv1.OfferStatusOpen {
			return false, nil
		}
		if o.SettlementMode == whaleswapv1.SettlementMode_SETTLEMENT_LIQUID {
			return false, nil
		}
		if o.RemainingHave.Amount.IsPositive() {
			denom := o.RemainingHave.Denom
			if cur, ok := required[denom]; ok {
				required[denom] = cur.Add(o.RemainingHave.Amount)
			} else {
				required[denom] = o.RemainingHave.Amount
			}
		}
		return false, nil
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "walk offers escrow")
	}
	out := sdk.NewCoins()
	for d, v := range required {
		if v.IsPositive() {
			out = out.Add(sdk.NewCoin(d, v))
		}
	}
	return out, nil
}

func (k Keeper) tallyPfandRequired(ctx context.Context) (sdk.Coins, error) {
	required := map[string]math.Int{}
	if err := k.OffersMap.Walk(ctx, nil, func(_ uint64, o whaleswapv1.OfferData) (bool, error) {
		if o.Status != whaleswapv1.OfferStatusOpen {
			return false, nil
		}
		if o.SettlementMode != whaleswapv1.SettlementMode_SETTLEMENT_LIQUID {
			return false, nil
		}
		if o.PfandLocked.Amount.IsPositive() {
			denom := o.PfandLocked.Denom
			if cur, ok := required[denom]; ok {
				required[denom] = cur.Add(o.PfandLocked.Amount)
			} else {
				required[denom] = o.PfandLocked.Amount
			}
		}
		return false, nil
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "walk offers pfand")
	}
	out := sdk.NewCoins()
	for d, v := range required {
		if v.IsPositive() {
			out = out.Add(sdk.NewCoin(d, v))
		}
	}
	return out, nil
}

func (k Keeper) checkEscrowInvariant(ctx context.Context) error {
	// Tally required escrow by denom from open normal offers
	required := map[string]math.Int{}
	if err := k.OffersMap.Walk(ctx, nil, func(_ uint64, o whaleswapv1.OfferData) (bool, error) {
		if o.Status != whaleswapv1.OfferStatusOpen {
			return false, nil
		}
		// Only escrow-mode offers escrow base have in module
		if o.SettlementMode == whaleswapv1.SettlementMode_SETTLEMENT_LIQUID {
			return false, nil
		}
		if !o.RemainingHave.Amount.IsPositive() {
			return false, nil
		}
		denom := o.RemainingHave.Denom
		if cur, ok := required[denom]; ok {
			required[denom] = cur.Add(o.RemainingHave.Amount)
		} else {
			required[denom] = o.RemainingHave.Amount
		}
		return false, nil
	}); err != nil {
		return cosmossdkerrors.Wrap(err, "walk offers for escrow invariant failed")
	}

	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	for denom, need := range required {
		bal := k.bank.GetBalance(ctx, moduleAddr, denom).Amount
		if bal.LT(need) {
			return cosmossdkerrors.Wrapf(
				sdkerrors.ErrLogic,
				"escrow invariant failed for %s: module=%s required=%s",
				denom, bal.String(), need.String(),
			)
		}
	}
	return nil
}

func (k Keeper) checkPfandInvariant(ctx context.Context) error {
	// Tally across offers in a single pass to derive both escrow(solid) and pfand(liquid) requirements
	escrowRequired := map[string]math.Int{} // solid have escrow for normal offers
	pfandRequired := map[string]math.Int{}  // pfand locked for liquid-have offers
	if err := k.OffersMap.Walk(ctx, nil, func(_ uint64, o whaleswapv1.OfferData) (bool, error) {
		if o.Status != whaleswapv1.OfferStatusOpen {
			return false, nil
		}
		if o.SettlementMode == whaleswapv1.SettlementMode_SETTLEMENT_LIQUID {
			// Liquid-have: require pfand
			if o.PfandLocked.Amount.IsPositive() {
				denom := o.PfandLocked.Denom
				if cur, ok := pfandRequired[denom]; ok {
					pfandRequired[denom] = cur.Add(o.PfandLocked.Amount)
				} else {
					pfandRequired[denom] = o.PfandLocked.Amount
				}
			}
			return false, nil
		}
		// Normal offer: escrow solid have in module
		if o.RemainingHave.Amount.IsPositive() {
			denom := o.RemainingHave.Denom
			if cur, ok := escrowRequired[denom]; ok {
				escrowRequired[denom] = cur.Add(o.RemainingHave.Amount)
			} else {
				escrowRequired[denom] = o.RemainingHave.Amount
			}
		}
		return false, nil
	}); err != nil {
		return cosmossdkerrors.Wrap(err, "walk offers for pfand invariant failed")
	}

	// Tally AMM reserves by denom (module holds pool reserves)
	ammRequired := map[string]math.Int{}
	if err := k.PoolsMap.Walk(ctx, nil, func(_ uint64, p whaleswapv1.Pool) (bool, error) {
		for _, c := range p.Coins {
			if cur, ok := ammRequired[c.Denom]; ok {
				ammRequired[c.Denom] = cur.Add(c.Amount)
			} else {
				ammRequired[c.Denom] = c.Amount
			}
		}
		return false, nil
	}); err != nil {
		return cosmossdkerrors.Wrap(err, "walk pools for pfand invariant failed")
	}

	// Now ensure module balance minus AMM reserves and escrow is sufficient to cover pfand
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	for denom, need := range pfandRequired {
		bal := k.bank.GetBalance(ctx, moduleAddr, denom).Amount
		amm := ammRequired[denom]
		esc := escrowRequired[denom]
		available := bal.Sub(amm).Sub(esc)
		if available.LT(need) {
			return cosmossdkerrors.Wrapf(
				sdkerrors.ErrLogic,
				"pfand invariant failed for %s: module=%s amm=%s escrow=%s pfand_required=%s available=%s",
				denom, bal.String(), amm.String(), esc.String(), need.String(), available.String(),
			)
		}
	}
	return nil
}

// AssertAMMInvariants checks AMM-related invariants across all pools:
// - Module balance per denom must cover the sum of all pool reserves for that denom
// - Shares supply must be > 0 for existing pools; if band set then Lcur > 0
// - Shares denom uniqueness across all pools
func (k Keeper) AssertAMMInvariants(ctx context.Context) error {
	required := map[string]math.Int{}
	shareDenoms := map[string]struct{}{}
	poolCount := 0

	// Accumulate requirements and per-pool sanity
	if err := k.PoolsMap.Walk(ctx, nil, func(_ uint64, p whaleswapv1.Pool) (bool, error) {
		poolCount++
		// Sum reserves by denom
		for _, c := range p.Coins {
			if cur, ok := required[c.Denom]; ok {
				required[c.Denom] = cur.Add(c.Amount)
			} else {
				required[c.Denom] = c.Amount
			}
		}

		// Shares supply must be positive
		supply := k.bank.GetSupply(ctx, p.SharesDenom).Amount
		if !supply.IsPositive() {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "shares supply must be > 0: pool_id=%d denom=%s", p.PoolId, p.SharesDenom)
		}
		// Validate bound_percent when present
		if len(p.BoundPercent) != 0 && len(p.BoundPercent) != 2 {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "invalid bound_percent length: pool_id=%d", p.PoolId)
		}
		if len(p.BoundPercent) == 2 {
			bp0 := p.BoundPercent[0].Amount
			bp1 := p.BoundPercent[1].Amount
			if bp0.IsZero() {
				bp0 = math.LegacyNewDec(1)
			}
			if bp1.IsZero() {
				bp1 = math.LegacyNewDec(1)
			}
			if !bp0.GT(math.LegacyZeroDec()) || bp0.GT(math.LegacyNewDec(1)) || !bp1.GT(math.LegacyZeroDec()) || bp1.GT(math.LegacyNewDec(1)) {
				return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "invalid bound_percent value: pool_id=%d", p.PoolId)
			}
		}

		// Ensure canonical pool denoms are available for per-denom checks
		if len(p.Coins) != 2 {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "invalid pool coins: pool_id=%d", p.PoolId)
		}
		baseDenom, quoteDenom := p.Coins[0].Denom, p.Coins[1].Denom

		// Required leverage config sanity
		if len(p.LiquidationThreshold) != 2 {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "pool liquidation_threshold must be length 2: pool_id=%d", p.PoolId)
		}
		liq1 := p.LiquidationThreshold.AmountOf(baseDenom)
		liq2 := p.LiquidationThreshold.AmountOf(quoteDenom)
		if !liq1.GT(math.LegacyNewDec(1)) || !liq2.GT(math.LegacyNewDec(1)) {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "invalid liquidation_threshold: pool_id=%d val=%s", p.PoolId, p.LiquidationThreshold.String())
		}
		if len(p.InterestRate) != 2 {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "pool interest_rate must be length 2: pool_id=%d", p.PoolId)
		}
		if len(p.MaxBorrowPercent) != 2 {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "pool max_borrow_percent must be length 2: pool_id=%d", p.PoolId)
		}
		// FeeRate must have exactly two entries matching pool denoms and amounts in [0,1)
		if len(p.FeeRate) != 2 {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "pool fee_rate must be length 2: pool_id=%d", p.PoolId)
		}
		fr1 := p.FeeRate.AmountOf(baseDenom)
		fr2 := p.FeeRate.AmountOf(quoteDenom)
		if fr1.IsNegative() || !fr1.LT(math.LegacyNewDec(1)) || fr2.IsNegative() || !fr2.LT(math.LegacyNewDec(1)) {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "invalid pool fee_rate amounts: pool_id=%d fee_rate=%s", p.PoolId, p.FeeRate.String())
		}
		// Ratios > 1 (per denom)
		if len(p.MinInitialCollateralRatio) != 2 {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "missing min_collateral_ratio entries: pool_id=%d", p.PoolId)
		}
		mcr1 := p.MinInitialCollateralRatio.AmountOf(baseDenom)
		mcr2 := p.MinInitialCollateralRatio.AmountOf(quoteDenom)
		if !mcr1.GT(math.LegacyNewDec(1)) || !mcr2.GT(math.LegacyNewDec(1)) {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "invalid min_collateral_ratio: pool_id=%d val=%s", p.PoolId, p.MinInitialCollateralRatio.String())
		}

		// Shares denom uniqueness
		if _, dup := shareDenoms[p.SharesDenom]; dup {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "duplicate shares denom: %s (pool_id=%d)", p.SharesDenom, p.PoolId)
		}
		shareDenoms[p.SharesDenom] = struct{}{}
		return false, nil
	}); err != nil {
		return cosmossdkerrors.Wrap(err, "walk pools failed")
	}

	if len(shareDenoms) != poolCount {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "shares denom uniqueness failed: unique=%d pools=%d", len(shareDenoms), poolCount)
	}

	// Coverage by module balances
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	// Build a readable coins snapshot for required reserves
	requiredCoins := sdk.NewCoins()
	for d, n := range required {
		requiredCoins = requiredCoins.Add(sdk.NewCoin(d, n))
	}
	logger.Info("AMM invariant required reserves", "required", requiredCoins.String())
	for denom, need := range required {
		have := k.bank.GetBalance(ctx, moduleAddr, denom).Amount
		if have.LT(need) {
			logger.Info("AMM invariant deficit", "denom", denom, "have", have.String(), "need", need.String())
			return cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "module balance below AMM reserves for %s: have=%s need=%s", denom, have.String(), need.String())
		}
	}
	return nil
}
