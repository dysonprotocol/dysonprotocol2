package types

import (
	"fmt"
	"time"

	"cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// Defaults: empty denom means PFAND disabled by default.
var DefaultPfandPerOffer = sdk.Coin{Denom: "udys", Amount: math.NewInt(1)}

func NewParams(pfandPerOffer sdk.Coin, valuationFeePct, minBidPctIncrease string, valuationPeriod time.Duration, bidTimeout time.Duration, maxNoteLength uint32, blockDelayBeforeClose, blockDelayBeforeLiquidation uint64) Params {
	return Params{
		PfandPerOffer:               pfandPerOffer,
		ValuationFeePct:             valuationFeePct,
		ValuationPeriod:             valuationPeriod,
		BidTimeout:                  bidTimeout,
		MinimumBidPercentIncrease:   minBidPctIncrease,
		MaxNoteLength:               maxNoteLength,
		BlockDelayBeforeClose:       blockDelayBeforeClose,
		BlockDelayBeforeLiquidation: blockDelayBeforeLiquidation,
	}
}

func DefaultParams() Params {
	p := NewParams(DefaultPfandPerOffer, "0", "0", time.Hour, time.Second*5, 128, 1, 1)
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
	if p.BlockDelayBeforeClose == 0 {
		return fmt.Errorf("block_delay_before_close must be > 0")
	}
	if p.BlockDelayBeforeLiquidation == 0 {
		return fmt.Errorf("block_delay_before_liquidation must be > 0")
	}
	return nil
}
