package types

import (
	"fmt"
	"time"

	"cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// DefaultPfandPerOffer returns the default pfand per offer using the SDK's default bond denom.
func DefaultPfandPerOffer() sdk.Coin {
	return sdk.Coin{Denom: sdk.DefaultBondDenom, Amount: math.NewInt(1)}
}

func NewParams(pfandPerOffer sdk.Coin, valuationFeePct, minBidPctIncrease string, valuationPeriod time.Duration, bidTimeout time.Duration, maxNoteLength uint32, blockDelayBeforeClose, blockDelayBeforeLiquidation uint64, arbitrageMode ArbitrageMode, arbitrageRefDenom, affiliateFeePct string) Params {
	return Params{
		PfandPerOffer:               pfandPerOffer,
		ValuationFeePct:             valuationFeePct,
		ValuationPeriod:             valuationPeriod,
		BidTimeout:                  bidTimeout,
		MinimumBidPercentIncrease:   minBidPctIncrease,
		MaxNoteLength:               maxNoteLength,
		BlockDelayBeforeClose:       blockDelayBeforeClose,
		BlockDelayBeforeLiquidation: blockDelayBeforeLiquidation,
		ArbitrageMode:               arbitrageMode,
		ArbitrageRefDenom:           arbitrageRefDenom,
		AffiliateFeePct:             affiliateFeePct,
	}
}

// DefaultParams returns default whaleswap parameters.
// Uses sdk.DefaultBondDenom which is set at genesis init time.
func DefaultParams() Params {
	p := NewParams(DefaultPfandPerOffer(), "0", "0", time.Hour, time.Second*5, 128, 1, 1, ArbitrageMode_ARBITRAGE_MODE_AUTO, sdk.DefaultBondDenom, "0")
	return p
}

func (p Params) Validate() error {
	if !p.PfandPerOffer.Amount.IsZero() && p.PfandPerOffer.Denom == "" {
		return fmt.Errorf("pfand_per_offer denom must be set when amount > 0")
	}
	if p.ValuationPeriod <= 0 {
		return fmt.Errorf("valuation_period must be > 0")
	}
	if p.BidTimeout <= 0 {
		return fmt.Errorf("bid_timeout must be > 0")
	}
	if p.ValuationFeePct != "" {
		dec, err := math.LegacyNewDecFromStr(p.ValuationFeePct)
		if err != nil {
			return fmt.Errorf("invalid valuation_fee_pct: %v", err)
		}
		if dec.IsNegative() || dec.GTE(math.LegacyNewDec(1)) {
			return fmt.Errorf("valuation_fee_pct must be in [0,1)")
		}
	}
	if p.MinimumBidPercentIncrease != "" {
		dec, err := math.LegacyNewDecFromStr(p.MinimumBidPercentIncrease)
		if err != nil {
			return fmt.Errorf("invalid minimum_bid_percent_increase: %v", err)
		}
		if dec.IsNegative() || dec.GTE(math.LegacyNewDec(1)) {
			return fmt.Errorf("minimum_bid_percent_increase must be in [0,1)")
		}
	}
	// Leverage parameter validation
	// Note: block delays can be 0 for testing (query exec scenarios where blocks don't advance).
	// Production deployments should use >= 1 via governance for safety.
	// No validation error for 0 to enable single-transaction testing.

	// Affiliate fee validation
	if p.AffiliateFeePct != "" {
		dec, err := math.LegacyNewDecFromStr(p.AffiliateFeePct)
		if err != nil {
			return fmt.Errorf("invalid affiliate_fee_pct: %v", err)
		}
		if dec.IsNegative() {
			return fmt.Errorf("affiliate_fee_pct cannot be negative")
		}
		if dec.GTE(math.LegacyOneDec()) {
			return fmt.Errorf("affiliate_fee_pct must be less than 1")
		}
	}
	return nil
}
