package keeper

import (
	"fmt"
	"strings"

	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

const maxAffiliateNameLen = 128

// ParseAffiliateName extracts and validates an affiliate dysname from a memo.
// Returns empty string if memo is empty, too long, or not a valid dysname.
func ParseAffiliateName(memo string) string {
	memo = strings.TrimSpace(memo)
	if memo == "" || len(memo) > maxAffiliateNameLen {
		return ""
	}
	// Must end with .dys to be a dysname
	lower := strings.ToLower(memo)
	if !strings.HasSuffix(lower, ".dys") {
		return ""
	}
	return lower
}

// ProcessAffiliatePayment calculates and sends affiliate fees from arbitrage profit.
// Returns (remaining, paid, affiliateAddr, error).
// - If affiliate_fee_pct is zero or name is invalid/unresolvable, returns (profit, nil, "", nil).
// - If payment fails, returns an error (caller should fail the tx).
func (k Keeper) ProcessAffiliatePayment(ctx sdk.Context, profit sdk.Coins, affiliateName string) (remaining sdk.Coins, paid sdk.Coins, affiliateAddr string, err error) {
	logger := k.ArbitrageLogger(ctx)

	// Get fee percentage from params
	params := k.GetParams(ctx)
	if params.AffiliateFeePct == "" || params.AffiliateFeePct == "0" {
		return profit, nil, "", nil
	}

	feePct, parseErr := math.LegacyNewDecFromStr(params.AffiliateFeePct)
	if parseErr != nil || feePct.IsZero() || feePct.IsNegative() {
		return profit, nil, "", nil
	}

	// Resolve dysname to address
	affiliateAddr, resolveErr := k.nameSvc.ResolveNameOrAddress(ctx, affiliateName)
	if resolveErr != nil {
		logger.Debug("affiliate name resolution failed", "name", affiliateName, "err", resolveErr)
		return profit, nil, "", nil
	}

	// Parse address for operations
	addr, addrErr := sdk.AccAddressFromBech32(affiliateAddr)
	if addrErr != nil {
		logger.Debug("affiliate address parse failed", "addr", affiliateAddr, "err", addrErr)
		return profit, nil, "", nil
	}

	// Don't pay affiliate if it's the arb module itself
	arbModuleAddr := k.accKeeper.GetModuleAddress(whaleswap.ArbRevenueModuleName)
	if addr.Equals(arbModuleAddr) {
		logger.Debug("affiliate is arb module, skipping", "name", affiliateName)
		return profit, nil, "", nil
	}

	// Calculate affiliate share using DecCoins for precision
	profitDec := sdk.NewDecCoinsFromCoins(profit...)
	affiliateDec := profitDec.MulDecTruncate(feePct)
	affiliateCoins, _ := affiliateDec.TruncateDecimal()

	if affiliateCoins.IsZero() {
		return profit, nil, affiliateAddr, nil
	}

	// Calculate remaining after subtracting affiliate share
	remainingCoins, hasNeg := profit.SafeSub(affiliateCoins...)
	if hasNeg {
		// Rounding edge case: affiliate share exceeds profit, skip payment
		return profit, nil, affiliateAddr, nil
	}

	// Send from arb revenue module to affiliate
	if sendErr := k.bank.SendCoinsFromModuleToAccount(ctx, whaleswap.ArbRevenueModuleName, addr, affiliateCoins); sendErr != nil {
		return nil, nil, affiliateAddr, fmt.Errorf("affiliate payment failed: %w", sendErr)
	}

	// Update affiliate metrics
	if metricsErr := k.incrementAffiliateEarned(ctx, affiliateAddr, affiliateCoins); metricsErr != nil {
		logger.Error("failed to update affiliate metrics", "err", metricsErr)
	}

	return remainingCoins, affiliateCoins, affiliateAddr, nil
}
