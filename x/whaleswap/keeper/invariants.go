package keeper

import (
	"context"
	"strings"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// InvariantsRebuildReport captures the actions taken while reconciling module balances.
type InvariantsRebuildReport struct {
	FeesCleared sdk.Coins
	Burned      sdk.Coins
	Expected    sdk.Coins
	Actual      sdk.Coins
}

// AssertInvariants checks core whaleswap module invariants that are safe to check mid-operation:
// - Module balances match expected (AMM reserves + escrow + pfand + auction + collateral)
// - Index consistency for offers and auctions
//
// Note: Borrow vault invariant is NOT checked here because AssertInvariants is called from
// MakeTrade which may be invoked mid-operation (e.g., from OpenPosition before position is persisted).
// Use AssertBorrowVaultInvariant explicitly at operation boundaries where state is consistent.
func (k Keeper) AssertInvariants(ctx context.Context) error {
	// Unified whaleswap module balance invariant with explicit breakdown
	if err := k.checkModuleBalancesInvariant(ctx); err != nil {
		return err
	}
	// Reverse indexes must be consistent with primary maps
	if err := k.checkIndexConsistency(ctx); err != nil {
		return err
	}
	return nil
}

// AssertBorrowVaultInvariant checks that borrow vault holds exactly what open positions require.
// Call this at the END of leverage operations (OpenPosition, ClosePosition, etc.) after
// position state is fully persisted. Do NOT call mid-operation.
func (k Keeper) AssertBorrowVaultInvariant(ctx context.Context) error {
	return k.checkBorrowVaultInvariant(ctx)
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
		if strings.HasPrefix(d, k.PoolsDenomPrefix(ctx)) && c.Amount.IsPositive() {
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

// RebuildModuleInvariants normalizes whaleswap bookkeeping by clearing stale fee ledgers,
// burning surplus balances, and ensuring the module account exactly matches on-chain state.
// It must be invoked from an upgrade handler while the chain is halted.
func (k Keeper) RebuildModuleInvariants(ctx context.Context) (InvariantsRebuildReport, error) {
	report := InvariantsRebuildReport{
		FeesCleared: sdk.NewCoins(),
		Burned:      sdk.NewCoins(),
		Expected:    sdk.NewCoins(),
		Actual:      sdk.NewCoins(),
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)

	// Zero-out per-pool fee ledgers; they were accumulated under the broken invariant tracking.
	if err := k.PoolsMap.Walk(ctx, nil, func(id uint64, pool whaleswapv1.Pool) (bool, error) {
		if len(pool.FeesEarned) == 0 {
			return false, nil
		}
		report.FeesCleared = report.FeesCleared.Add(pool.FeesEarned...)
		pool.FeesEarned = sdk.NewCoins()
		if err := k.PoolsMap.Set(ctx, id, pool); err != nil {
			return true, cosmossdkerrors.Wrapf(err, "clear fees_earned for pool %d", id)
		}
		return false, nil
	}); err != nil {
		return report, err
	}

	// Recompute expected requirements from live state.
	ammRequired, err := k.tallyAMMReserves(ctx)
	if err != nil {
		return report, err
	}
	escrowRequired, err := k.tallyEscrowRequired(ctx)
	if err != nil {
		return report, err
	}
	pfandRequired, err := k.tallyPfandRequired(ctx)
	if err != nil {
		return report, err
	}
	auctionRequired, err := k.tallyAuctionRequired(ctx)
	if err != nil {
		return report, err
	}
	leverageCollateral, _, _, err := k.tallyLeveragePositions(ctx)
	if err != nil {
		return report, err
	}

	expectedMap := map[string]math.Int{}
	accumulate := func(coins sdk.Coins) {
		for _, c := range coins {
			if !c.Amount.IsPositive() {
				continue
			}
			if cur, ok := expectedMap[c.Denom]; ok {
				expectedMap[c.Denom] = cur.Add(c.Amount)
			} else {
				expectedMap[c.Denom] = c.Amount
			}
		}
	}
	accumulate(ammRequired)
	accumulate(escrowRequired)
	accumulate(pfandRequired)
	accumulate(auctionRequired)
	accumulate(leverageCollateral)

	toCoins := func(m map[string]math.Int) sdk.Coins {
		out := sdk.NewCoins()
		for denom, amt := range m {
			if amt.IsPositive() {
				out = out.Add(sdk.NewCoin(denom, amt))
			}
		}
		return out
	}
	report.Expected = toCoins(expectedMap)

	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	actual := k.bank.SpendableCoins(ctx, moduleAddr)
	report.Actual = actual

	denomSet := map[string]struct{}{}
	for denom := range expectedMap {
		denomSet[denom] = struct{}{}
	}
	for _, coin := range actual {
		denomSet[coin.Denom] = struct{}{}
	}

	burn := sdk.NewCoins()
	deficit := sdk.NewCoins()
	for denom := range denomSet {
		expAmt, has := expectedMap[denom]
		if !has {
			expAmt = math.NewInt(0)
		}
		actAmt := actual.AmountOf(denom)
		switch {
		case actAmt.GT(expAmt):
			burn = burn.Add(sdk.NewCoin(denom, actAmt.Sub(expAmt)))
		case expAmt.GT(actAmt):
			deficit = deficit.Add(sdk.NewCoin(denom, expAmt.Sub(actAmt)))
		}
	}

	if !deficit.Empty() {
		return report, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "whaleswap module deficit detected: %s", deficit.String())
	}

	if !burn.Empty() {
		if err := k.bank.BurnCoins(ctx, whaleswap.ModuleName, burn); err != nil {
			return report, cosmossdkerrors.Wrap(err, "burn whaleswap excess balances")
		}
		report.Burned = burn
		logger.Info("burned whaleswap excess balances", "coins", burn.String())
		report.Actual = k.bank.SpendableCoins(ctx, moduleAddr)
	} else {
		report.Burned = sdk.NewCoins()
	}

	if err := k.AssertInvariants(ctx); err != nil {
		return report, err
	}

	logger.Info("reconciled whaleswap module balances",
		"expected", report.Expected.String(),
		"actual", report.Actual.String(),
		"fees_cleared", report.FeesCleared.String(),
		"burned", report.Burned.String(),
	)
	return report, nil
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

// checkBorrowVaultInvariant verifies that the leverage borrow vault balance EXACTLY matches
// the sum of all open/liquidating position held amounts. The borrow vault holds the
// "held" asset after the borrowed tokens are swapped during position opening.
func (k Keeper) checkBorrowVaultInvariant(ctx context.Context) error {
	_, heldRequired, _, err := k.tallyLeveragePositions(ctx)
	if err != nil {
		return err
	}

	borrowVaultAddr := k.accKeeper.GetModuleAddress(whaleswap.LeverageBorrowVaultModuleName)
	actual := k.bank.SpendableCoins(ctx, borrowVaultAddr)

	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)
	logger.Info("Borrow vault invariant check", "vault", borrowVaultAddr.String(), "actual", actual.String(), "expected_held", heldRequired.String())

	// Build denom set from both expected and actual
	denomSet := map[string]struct{}{}
	for _, c := range heldRequired {
		denomSet[c.Denom] = struct{}{}
	}
	for _, c := range actual {
		denomSet[c.Denom] = struct{}{}
	}

	for denom := range denomSet {
		expected := heldRequired.AmountOf(denom)
		have := actual.AmountOf(denom)
		if !have.Equal(expected) {
			logger.Info("Borrow vault mismatch", "denom", denom, "have", have.String(), "expected", expected.String())
			return cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"borrow vault balance mismatch for %s: have=%s expected=%s",
				denom, have.String(), expected.String())
		}
	}
	return nil
}

// checkIndexConsistency verifies bidirectional consistency between primary maps and reverse indexes.
// For offers: each open offer must have all index entries, and each index entry must point to a valid open offer.
// For auctions: each auction must have both reverse index entries, and vice versa.
func (k Keeper) checkIndexConsistency(ctx context.Context) error {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)

	// --- Offer Index Consistency ---
	// 1. Forward check: each open offer must have all required index entries
	openOfferIDs := map[uint64]struct{}{}
	if err := k.OffersMap.Walk(ctx, nil, func(id uint64, offer whaleswapv1.OfferData) (bool, error) {
		if offer.Status != whaleswapv1.OfferStatusOpen {
			return false, nil
		}
		openOfferIDs[id] = struct{}{}

		// Check OffersByHave index exists
		if _, err := k.OffersByHave.Get(ctx, collections.Join(offer.RemainingHave.Denom, id)); err != nil {
			logger.Info("Missing OffersByHave index", "offer_id", id, "have_denom", offer.RemainingHave.Denom)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"missing OffersByHave index for open offer %d (have_denom=%s)", id, offer.RemainingHave.Denom)
		}

		// Check OffersByWant index exists
		if _, err := k.OffersByWant.Get(ctx, collections.Join(offer.RemainingWant.Denom, id)); err != nil {
			logger.Info("Missing OffersByWant index", "offer_id", id, "want_denom", offer.RemainingWant.Denom)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"missing OffersByWant index for open offer %d (want_denom=%s)", id, offer.RemainingWant.Denom)
		}

		// Check OffersByOwnerStatus index exists
		if _, err := k.OffersByOwnerStatus.Get(ctx, collections.Join3(offer.Maker, offer.Status, id)); err != nil {
			logger.Info("Missing OffersByOwnerStatus index", "offer_id", id, "maker", offer.Maker, "status", offer.Status)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"missing OffersByOwnerStatus index for open offer %d (maker=%s status=%s)", id, offer.Maker, offer.Status)
		}

		return false, nil
	}); err != nil {
		return err
	}

	// 2. Backward check: each OffersByHave entry must point to a valid open offer
	if err := k.OffersByHave.Walk(ctx, nil, func(_ collections.Pair[string, uint64], offerID uint64) (bool, error) {
		if _, ok := openOfferIDs[offerID]; !ok {
			// Check if offer exists at all
			offer, err := k.OffersMap.Get(ctx, offerID)
			if err != nil {
				logger.Info("Dangling OffersByHave index: offer not found", "offer_id", offerID)
				return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
					"dangling OffersByHave index: offer %d not found", offerID)
			}
			logger.Info("Dangling OffersByHave index: offer not open", "offer_id", offerID, "status", offer.Status)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"dangling OffersByHave index: offer %d has status %s (not open)", offerID, offer.Status)
		}
		return false, nil
	}); err != nil {
		return err
	}

	// 3. Backward check: each OffersByWant entry must point to a valid open offer
	if err := k.OffersByWant.Walk(ctx, nil, func(_ collections.Pair[string, uint64], offerID uint64) (bool, error) {
		if _, ok := openOfferIDs[offerID]; !ok {
			offer, err := k.OffersMap.Get(ctx, offerID)
			if err != nil {
				logger.Info("Dangling OffersByWant index: offer not found", "offer_id", offerID)
				return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
					"dangling OffersByWant index: offer %d not found", offerID)
			}
			logger.Info("Dangling OffersByWant index: offer not open", "offer_id", offerID, "status", offer.Status)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"dangling OffersByWant index: offer %d has status %s (not open)", offerID, offer.Status)
		}
		return false, nil
	}); err != nil {
		return err
	}

	// --- Auction Index Consistency ---
	// 1. Forward check: each auction must have both reverse index entries
	auctionIDs := map[uint64]struct{}{}
	if err := k.AuctionsMap.Walk(ctx, nil, func(id uint64, auction whaleswapv1.AuctionRecord) (bool, error) {
		auctionIDs[id] = struct{}{}

		// Check AuctionsBySellBid index exists
		if _, err := k.AuctionsBySellBid.Get(ctx, collections.Join3(auction.Sell.Denom, auction.BidDenom, id)); err != nil {
			logger.Info("Missing AuctionsBySellBid index", "auction_id", id, "sell", auction.Sell.Denom, "bid", auction.BidDenom)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"missing AuctionsBySellBid index for auction %d (sell=%s bid=%s)", id, auction.Sell.Denom, auction.BidDenom)
		}

		// Check AuctionsByBidSell index exists
		if _, err := k.AuctionsByBidSell.Get(ctx, collections.Join3(auction.BidDenom, auction.Sell.Denom, id)); err != nil {
			logger.Info("Missing AuctionsByBidSell index", "auction_id", id, "bid", auction.BidDenom, "sell", auction.Sell.Denom)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"missing AuctionsByBidSell index for auction %d (bid=%s sell=%s)", id, auction.BidDenom, auction.Sell.Denom)
		}

		return false, nil
	}); err != nil {
		return err
	}

	// 2. Backward check: each AuctionsBySellBid entry must point to a valid auction
	if err := k.AuctionsBySellBid.Walk(ctx, nil, func(_ collections.Triple[string, string, uint64], auctionID uint64) (bool, error) {
		if _, ok := auctionIDs[auctionID]; !ok {
			logger.Info("Dangling AuctionsBySellBid index", "auction_id", auctionID)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"dangling AuctionsBySellBid index: auction %d not found", auctionID)
		}
		return false, nil
	}); err != nil {
		return err
	}

	// 3. Backward check: each AuctionsByBidSell entry must point to a valid auction
	if err := k.AuctionsByBidSell.Walk(ctx, nil, func(_ collections.Triple[string, string, uint64], auctionID uint64) (bool, error) {
		if _, ok := auctionIDs[auctionID]; !ok {
			logger.Info("Dangling AuctionsByBidSell index", "auction_id", auctionID)
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"dangling AuctionsByBidSell index: auction %d not found", auctionID)
		}
		return false, nil
	}); err != nil {
		return err
	}

	logger.Info("Index consistency check passed", "open_offers", len(openOfferIDs), "auctions", len(auctionIDs))
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
		// Module should never hold pool shares (would indicate failed distribution)
		moduleShareBal := k.bank.GetBalance(ctx, k.accKeeper.GetModuleAddress(whaleswap.ModuleName), p.SharesDenom).Amount
		if moduleShareBal.IsPositive() {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"module unexpectedly holds %s shares of pool %d (denom=%s)",
				moduleShareBal.String(), p.PoolId, p.SharesDenom)
		}
		// Borrow vault should never hold pool shares
		borrowVaultShareBal := k.bank.GetBalance(ctx, k.accKeeper.GetModuleAddress(whaleswap.LeverageBorrowVaultModuleName), p.SharesDenom).Amount
		if borrowVaultShareBal.IsPositive() {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"borrow vault unexpectedly holds %s shares of pool %d (denom=%s)",
				borrowVaultShareBal.String(), p.PoolId, p.SharesDenom)
		}
		// Leverage vault should never hold pool shares
		leverageVaultShareBal := k.bank.GetBalance(ctx, k.accKeeper.GetModuleAddress(whaleswap.LeverageVaultModuleName), p.SharesDenom).Amount
		if leverageVaultShareBal.IsPositive() {
			return true, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic,
				"leverage vault unexpectedly holds %s shares of pool %d (denom=%s)",
				leverageVaultShareBal.String(), p.PoolId, p.SharesDenom)
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
