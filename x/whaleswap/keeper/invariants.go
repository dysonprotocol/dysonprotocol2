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

	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	actual := k.bank.SpendableCoins(ctx, moduleAddr)

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
	// Build expected totals per denom (no liquid-backing component now)
	expected := sdk.NewCoins().Add(ammRequired...).Add(escrowRequired...).Add(auctionRequired...).Add(pfandRequired...)

	// No special-casing PFAND here: it's already included in pfandRequired and
	// therefore in 'expected'. Per-denom equality below covers all pfand denoms
	// that exist across open offers (supports historical changes to pfand params).

	// Actual module balances (spendable equals total for module accounts)
	// reuse moduleAddr and actual from above

	// Compare per-denom for exact equality; any deficit or excess is an invariant failure
	denomSet := map[string]struct{}{}
	for _, c := range expected {
		denomSet[c.Denom] = struct{}{}
	}
	for _, c := range actual {
		denomSet[c.Denom] = struct{}{}
	}
	// Build quick lookup maps for breakdown reporting
	toMap := func(cs sdk.Coins) map[string]math.Int {
		m := make(map[string]math.Int, len(cs))
		for _, c := range cs {
			m[c.Denom] = c.Amount
		}
		return m
	}
	ammMap := toMap(ammRequired)
	escMap := toMap(escrowRequired)
	pfdMap := toMap(pfandRequired)

	for denom := range denomSet {
		exp := expected.AmountOf(denom)
		act := actual.AmountOf(denom)
		if !act.Equal(exp) {
			amm := ammMap[denom]
			esc := escMap[denom]
			pfd := pfdMap[denom]
			auc := auctionRequired.AmountOf(denom)
			return cosmossdkerrors.Wrapf(
				sdkerrors.ErrLogic,
				"module balance mismatch for %s: have=%s expected=%s (amm=%s escrow=%s auction=%s pfand=%s)",
				denom, act.String(), exp.String(), amm.String(), esc.String(), auc.String(), pfd.String(),
			)
		}
	}
	return nil
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
		// If band set, liquidity must be positive
		if len(p.MinPrice) == 2 {
			if len(p.Coins) != 2 {
				return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "invalid pool coins: pool_id=%d", p.PoolId)
			}
			Lcur, _, _, err := k.liquidityForReserves(p)
			if err != nil {
				return true, cosmossdkerrors.Wrapf(err, "failed liquidity calc: pool_id=%d", p.PoolId)
			}
			if !Lcur.IsPositive() {
				return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "invalid pool liquidity: pool_id=%d", p.PoolId)
			}
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
	for denom, need := range required {
		have := k.bank.GetBalance(ctx, moduleAddr, denom).Amount
		if have.LT(need) {
			return cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "module balance below AMM reserves for %s: have=%s need=%s", denom, have.String(), need.String())
		}
	}
	return nil
}
