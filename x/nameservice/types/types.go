package types

import (
	"regexp"
	"strings"

	sdkerrors "cosmossdk.io/errors"
)

// DNS Label regex components (single point of truth)
// A valid label: starts with letter, optionally followed by alphanumeric/dashes, must end with alphanumeric
// Supports punycode domains (e.g., xn--nxasmq5a for internationalized domain names)
const (
	// ExternalNameRegexString defines the regex for valid external domain names
	// One or more labels separated by dots; superset of NameRegexString
	ExternalNameRegexString = `^` + LabelRegexString + `(?:\.` + LabelRegexString + `)*$`
)

var (
	// ExternalNameRegex is the compiled regex for valid external names
	// Accepts any valid name (minus the suffix) plus standard domain formats
	ExternalNameRegex = regexp.MustCompile(ExternalNameRegexString)
)

// ValidDenomRegexString validates coin denoms for both nameservice and external names
// Format: name[/subdenom1/subdenom2/...] where name matches ExternalNameRegexString
const ValidDenomRegexString = `^` + LabelRegexString + `(?:\.` + LabelRegexString + `)*(?:/[0-9A-Za-z:_.-]+)*$`

// ValidDenomRegex is the compiled regex for validating nameservice coin denoms
var ValidDenomRegex = regexp.MustCompile(ValidDenomRegexString)

// ValidateBasic performs basic validation of NFTData
func (d *NFTData) ValidateBasic() error {

	// Validate metadata size if present
	if len(d.Metadata) > 1024 { // 1KB limit
		return ErrMetadataTooLarge.Wrap("metadata exceeds 1KB limit")
	}

	return nil
}

// ValidateNameWithSuffix validates a name string for the commit-reveal registration process.
// This is intentionally restrictive to prevent namespace confusion and squatting.
// The suffix parameter is the configured name suffix (e.g., ".dys").
func ValidateNameWithSuffix(name string, suffix string) error {
	if len(name) == 0 {
		return sdkerrors.Wrap(ErrInvalidName, "name cannot be empty")
	}

	suffixBase := GetNameSuffixBase(suffix)
	nameRegex := GetNameRegex(suffix)

	// must only contain the configured suffix at the end
	if !strings.HasSuffix(name, suffix) {
		return sdkerrors.Wrap(ErrInvalidName, "name must end with "+suffix)
	}
	// Check name format
	if !nameRegex.MatchString(name) {
		return sdkerrors.Wrap(ErrInvalidName, "invalid name format: must be lowercase, start with a letter, contain only alphanumeric and dash characters, and end with "+suffix)
	}

	// Names cannot contain the suffix base substring (e.g., "odyssey.dys", "analysis.dys" are invalid for ".dys" suffix).
	// This is BY DESIGN to:
	// 1. Prevent confusion with the native token denomination
	// 2. Reserve suffix-containing names for protocol use (governance can create via CreateExternalName)
	// 3. Avoid namespace squatting on protocol-related terms
	if strings.Contains(strings.TrimSuffix(name, suffix), suffixBase) {
		return sdkerrors.Wrap(ErrInvalidName, "name cannot contain '"+suffixBase+"'")
	}

	return nil
}
