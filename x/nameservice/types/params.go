package types

import (
	_ "embed"
	"fmt"
	"regexp"
	"strings"
	"sync"
	"time"

	"cosmossdk.io/math"
)

//go:embed reserved_dysnames.txt
var defaultReservedNamesFile string

// MinBidTimeout is the minimum allowed value for the class bid timeout parameter
const MinBidTimeout = 0 // 0 seconds
// MaxBidTimeout is the maximum allowed value for the class bid timeout parameter
const MaxBidTimeout = time.Hour * 24 * 90 // 90 days

// DefaultMintFeePerCoin is the default fee in udys charged per coin minted
var DefaultMintFeePerCoin = "0.01" // 1 udys == 100 base denoms

// DefaultNameSuffix is the default suffix for registered names.
// This is set in genesis and should NOT be changed after chain launch.
var DefaultNameSuffix = ".dys"

// LabelRegexString matches a single DNS-like label (used for regex compilation)
const LabelRegexString = `[a-z](?:[a-z0-9-]*[a-z0-9])?`

// NewParams creates a new Params instance with given values
func NewParams(
	mintFeePerCoin string,
	nameSuffix string,
) Params {
	return Params{
		MintFeePerCoin: mintFeePerCoin,
		NameSuffix:     nameSuffix,
	}
}

// DefaultParams returns a default set of parameters
func DefaultParams() Params {
	p := NewParams(
		DefaultMintFeePerCoin,
		DefaultNameSuffix,
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
	// ReservedNames is empty by default - governance can add custom reserved names
	// Default reserved names from the embedded file are always enforced separately
	p.ReservedNames = ""
	return p
}

// Validate validates the params
func (p Params) Validate() error {
	if err := validateMintFeePerCoin(p.MintFeePerCoin); err != nil {
		return err
	}

	// Validate name suffix
	if err := validateNameSuffix(p.NameSuffix); err != nil {
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

	// Validate reserved names using the params' own suffix
	if err := validateReservedNamesWithSuffix(p.ReservedNames, p.NameSuffix); err != nil {
		return err
	}

	return nil
}

// validateNameSuffix validates the name suffix parameter
func validateNameSuffix(suffix string) error {
	if suffix == "" {
		return fmt.Errorf("name suffix cannot be empty")
	}
	if !strings.HasPrefix(suffix, ".") {
		return fmt.Errorf("name suffix must start with '.' (got %q)", suffix)
	}
	if len(suffix) < 2 {
		return fmt.Errorf("name suffix must have at least one character after '.' (got %q)", suffix)
	}
	// Validate the suffix base (part after the dot) is valid alphanumeric
	suffixBase := suffix[1:]
	for _, c := range suffixBase {
		if !((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) {
			return fmt.Errorf("name suffix must contain only lowercase letters and digits after '.' (got %q)", suffix)
		}
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

// validateReservedNamesWithSuffix validates the reserved_names field against a specific suffix.
// It parses the newline-separated string, ignores blank lines and lines starting with #,
// and validates that each name matches the NameRegex format for the given suffix.
func validateReservedNamesWithSuffix(reservedNamesStr string, suffix string) error {
	if reservedNamesStr == "" {
		return nil
	}

	nameRegex := CompileNameRegex(suffix)

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
		// Validate name format - must match NameRegex (ends with configured suffix)
		if !nameRegex.MatchString(line) {
			return fmt.Errorf("invalid reserved name at line %d: %s (must be lowercase, start with a letter, contain only alphanumeric and dash characters, and end with %s)", i+1, line, suffix)
		}
	}

	return nil
}

// NormalizeReservedNames filters out comments and blank lines from a reserved names string.
// This should be called before storing the reserved names to keep stored values clean.
func NormalizeReservedNames(reservedNamesStr string) string {
	if reservedNamesStr == "" {
		return ""
	}

	lines := strings.Split(reservedNamesStr, "\n")
	var validNames []string

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
		validNames = append(validNames, line)
	}

	return strings.Join(validNames, "\n")
}

// CompileNameRegex compiles the regex for valid names with the given suffix.
// Pattern: ^[a-z](?:[a-z0-9-]*[a-z0-9])?\.<suffix>$
func CompileNameRegex(suffix string) *regexp.Regexp {
	escapedSuffix := regexp.QuoteMeta(suffix)
	nameRegexStr := `^` + LabelRegexString + escapedSuffix + `$`
	return regexp.MustCompile(nameRegexStr)
}

// nameRegexCache caches compiled name regexes by suffix for efficiency
var (
	nameRegexCache   = make(map[string]*regexp.Regexp)
	nameRegexCacheMu sync.RWMutex
)

// GetNameRegex returns a cached compiled regex for the given suffix.
func GetNameRegex(suffix string) *regexp.Regexp {
	nameRegexCacheMu.RLock()
	if r, ok := nameRegexCache[suffix]; ok {
		nameRegexCacheMu.RUnlock()
		return r
	}
	nameRegexCacheMu.RUnlock()

	// Compile and cache
	nameRegexCacheMu.Lock()
	defer nameRegexCacheMu.Unlock()
	// Double-check after acquiring write lock
	if r, ok := nameRegexCache[suffix]; ok {
		return r
	}
	r := CompileNameRegex(suffix)
	nameRegexCache[suffix] = r
	return r
}

// LoadDefaultReservedNames loads and processes the default reserved names file.
// It reads the embedded file, filters out comments and blank lines, validates names,
// and adds the configured name suffix to valid names. Invalid names are skipped.
func LoadDefaultReservedNames(suffix string) string {
	if defaultReservedNamesFile == "" {
		return ""
	}

	nameRegex := GetNameRegex(suffix)

	lines := strings.Split(defaultReservedNamesFile, "\n")
	var reservedNames []string

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
		// Add suffix if not already present
		nameWithSuffix := line
		if !strings.HasSuffix(line, suffix) {
			nameWithSuffix = line + suffix
		}
		// Validate name format - skip invalid names (e.g., containing @ or other invalid chars)
		if !nameRegex.MatchString(nameWithSuffix) {
			continue
		}
		reservedNames = append(reservedNames, nameWithSuffix)
	}

	return strings.Join(reservedNames, "\n")
}

// defaultReservedNamesCache caches the processed default reserved names per suffix
var (
	defaultReservedNamesCache   = make(map[string]string)
	defaultReservedNamesCacheMu sync.RWMutex
)

// GetDefaultReservedNames returns the cached default reserved names for the given suffix.
func GetDefaultReservedNames(suffix string) string {
	defaultReservedNamesCacheMu.RLock()
	if names, ok := defaultReservedNamesCache[suffix]; ok {
		defaultReservedNamesCacheMu.RUnlock()
		return names
	}
	defaultReservedNamesCacheMu.RUnlock()

	// Load and cache
	defaultReservedNamesCacheMu.Lock()
	defer defaultReservedNamesCacheMu.Unlock()
	// Double-check after acquiring write lock
	if names, ok := defaultReservedNamesCache[suffix]; ok {
		return names
	}
	names := LoadDefaultReservedNames(suffix)
	defaultReservedNamesCache[suffix] = names
	return names
}

// IsReservedName checks if a name is reserved.
// It checks BOTH the default reserved names from the embedded file AND
// any additional reserved names passed in reservedNamesStr (from params).
// The name parameter should have the configured suffix, which will be trimmed before comparison.
func IsReservedName(name string, reservedNamesStr string, suffix string) bool {
	// Trim suffix from the input name for comparison
	nameBase := strings.TrimSuffix(name, suffix)

	// Check against default reserved names (always enforced)
	if isNameInList(nameBase, GetDefaultReservedNames(suffix), suffix) {
		return true
	}

	// Check against additional reserved names from params
	if reservedNamesStr != "" && isNameInList(nameBase, reservedNamesStr, suffix) {
		return true
	}

	return false
}

// isNameInList checks if a name (without suffix) is in a newline-separated list
func isNameInList(nameBase string, list string, suffix string) bool {
	if list == "" {
		return false
	}

	lines := strings.Split(list, "\n")
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

		// Trim suffix from list entry for comparison
		lineBase := strings.TrimSuffix(line, suffix)

		// Exact match (case-sensitive) on base names
		if lineBase == nameBase {
			return true
		}
	}

	return false
}

// GetNameSuffixBase returns the suffix without the leading dot (e.g., "dys" from ".dys").
func GetNameSuffixBase(suffix string) string {
	if len(suffix) > 0 && suffix[0] == '.' {
		return suffix[1:]
	}
	return suffix
}
