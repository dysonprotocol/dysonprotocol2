package types

import (
	"fmt"
	"strings"
	"time"

	"cosmossdk.io/math"
)

// MinBidTimeout is the minimum allowed value for the class bid timeout parameter
const MinBidTimeout = 0 // 0 seconds
// MaxBidTimeout is the maximum allowed value for the class bid timeout parameter
const MaxBidTimeout = time.Hour * 24 * 90 // 90 days

// DefaultMintFeePerCoin is the default fee in udys charged per coin minted
var DefaultMintFeePerCoin = "0.01" // 1 udys == 100 base denoms

// NewParams creates a new Params instance with given values
func NewParams(
	mintFeePerCoin string,
) Params {
	return Params{
		MintFeePerCoin: mintFeePerCoin,
	}
}

// DefaultParams returns a default set of parameters
func DefaultParams() Params {
	p := NewParams(
		DefaultMintFeePerCoin,
	)
	// Set permissive but safe defaults for class parameter bounds
	p.MinBidTimeoutClass = time.Second * 0
	p.MaxBidTimeoutClass = MaxBidTimeout
	p.MinRejectBidValuationFeePercent = "0.0"
	p.MaxRejectBidValuationFeePercent = "1.0"
	p.MinMinimumBidPercentIncrease = "0.0"
	p.MaxMinimumBidPercentIncrease = "1.0"
	// New valuation fee/period bounds
	p.MinValuationFeePct = "0.0"
	p.MaxValuationFeePct = "1.0"
	p.MinValuationPeriod = time.Hour * 1
	p.MaxValuationPeriod = time.Hour * 24 * 365
	// Reserved names defaults to empty (no restrictions)
	p.ReservedNames = ""
	return p
}

// Validate validates the params
func (p Params) Validate() error {
	if err := validateMintFeePerCoin(p.MintFeePerCoin); err != nil {
		return err
	}

	// Validate class bounds
	if err := validateBidTimeoutBounds(p.MinBidTimeoutClass, p.MaxBidTimeoutClass); err != nil {
		return err
	}
	if err := validateDecBounds(p.MinRejectBidValuationFeePercent, p.MaxRejectBidValuationFeePercent); err != nil {
		return err
	}
	if err := validateDecBounds(p.MinMinimumBidPercentIncrease, p.MaxMinimumBidPercentIncrease); err != nil {
		return err
	}
	if err := validateDecBounds(p.MinValuationFeePct, p.MaxValuationFeePct); err != nil {
		return err
	}
	if err := validateDurationBounds(p.MinValuationPeriod, p.MaxValuationPeriod); err != nil {
		return err
	}

	// Validate reserved names
	if err := validateReservedNames(p.ReservedNames); err != nil {
		return err
	}

	return nil
}

// removed: global bid timeout validation (now class-bounded only)

func validateAllowedDenoms(denoms []string) error {
	// Check if the denoms list is empty
	if len(denoms) == 0 {
		return fmt.Errorf("allowed denoms list cannot be empty, it must contain at least 'udys'")
	}

	// Check if "udys" is in the allowed denoms list
	dysDenomExists := false
	for _, denom := range denoms {
		// Check that no denom is empty
		if denom == "" {
			return fmt.Errorf("denom cannot be empty")
		}

		if denom == "udys" {
			dysDenomExists = true
		}
	}

	// Ensure "udys" is in the list
	if !dysDenomExists {
		return fmt.Errorf("allowed denoms list must contain 'udys'")
	}

	return nil
}

func validateBidTimeoutBounds(min time.Duration, max time.Duration) error {
	if min < MinBidTimeout {
		return fmt.Errorf("min bid timeout class must be >= %v", MinBidTimeout)
	}
	if max > MaxBidTimeout {
		return fmt.Errorf("max bid timeout class must be <= %v", MaxBidTimeout)
	}
	if max < min {
		return fmt.Errorf("max bid timeout class must be >= min bid timeout class")
	}
	return nil
}

func validateDurationBounds(min time.Duration, max time.Duration) error {
	if min < 0 {
		return fmt.Errorf("min duration must be >= 0")
	}
	if max < 0 {
		return fmt.Errorf("max duration must be >= 0")
	}
	if max < min {
		return fmt.Errorf("max duration must be >= min duration")
	}
	return nil
}

func validateDecBounds(minStr, maxStr string) error {
	min, err := math.LegacyNewDecFromStr(minStr)
	if err != nil {
		return fmt.Errorf("invalid min bound: %s", err)
	}
	max, err := math.LegacyNewDecFromStr(maxStr)
	if err != nil {
		return fmt.Errorf("invalid max bound: %s", err)
	}
	if max.LT(min) {
		return fmt.Errorf("max bound must be >= min bound")
	}
	if min.IsNegative() {
		return fmt.Errorf("min bound cannot be negative")
	}
	return nil
}

// removed: legacy global percent validators and helpers (now class-bounded)

func validateMintFeePerCoin(mintFeePerCoinStr string) error {
	mintFeePerCoin, err := math.LegacyNewDecFromStr(mintFeePerCoinStr)
	if err != nil {
		return fmt.Errorf("invalid mint fee per coin: %s", err)
	}

	if mintFeePerCoin.IsNegative() {
		return fmt.Errorf("mint fee per coin cannot be negative: %s", mintFeePerCoinStr)
	}

	return nil
}

// GetMintFeePerCoinAsDec returns the mint fee per coin as a math.LegacyDec
func (p Params) GetMintFeePerCoinAsDec() (math.LegacyDec, error) {
	return math.LegacyNewDecFromStr(p.MintFeePerCoin)
}

// validateReservedNames validates the reserved_names field.
// It parses the newline-separated string, ignores blank lines and lines starting with #,
// and validates that each name matches the NameRegex format.
func validateReservedNames(reservedNamesStr string) error {
	if reservedNamesStr == "" {
		return nil
	}

	lines := strings.Split(reservedNamesStr, "\n")
	for i, line := range lines {
		line = strings.TrimSpace(line)
		// Skip blank lines
		if line == "" {
			continue
		}
		// Skip comment lines
		if strings.HasPrefix(line, "#") {
			continue
		}
		// Validate name format - must match NameRegex (ends with .dys)
		if !NameRegex.MatchString(line) {
			return fmt.Errorf("invalid reserved name at line %d: %s (must be lowercase, start with a letter, contain only alphanumeric and dash characters, and end with .dys)", i+1, line)
		}
	}

	return nil
}

// IsReservedName checks if a name is in the reserved names list.
// It parses the newline-separated string, ignores blank lines and lines starting with #,
// and returns true if the name exactly matches any reserved name (case-sensitive).
func IsReservedName(name string, reservedNamesStr string) bool {
	if reservedNamesStr == "" {
		return false
	}

	lines := strings.Split(reservedNamesStr, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		// Skip blank lines
		if line == "" {
			continue
		}
		// Skip comment lines
		if strings.HasPrefix(line, "#") {
			continue
		}
		// Exact match (case-sensitive)
		if line == name {
			return true
		}
	}

	return false
}
