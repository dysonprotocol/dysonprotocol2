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
	// LabelRegexString matches a single DNS-like label
	// Examples: "a", "abc", "my-site", "xn--nxasmq5a" (punycode)
	LabelRegexString = `[a-z](?:[a-z0-9-]*[a-z0-9])?`

	// NameRegexString defines the regex for valid .dys names (label + ".dys")
	NameRegexString = `^` + LabelRegexString + `\.dys$`

	// ExternalNameRegexString defines the regex for valid external domain names
	// One or more labels separated by dots; superset of NameRegexString
	ExternalNameRegexString = `^` + LabelRegexString + `(?:\.` + LabelRegexString + `)*$`
)

var (
	// NameRegex is the compiled regex for valid .dys name strings
	NameRegex = regexp.MustCompile(NameRegexString)

	// ExternalNameRegex is the compiled regex for valid external names
	// Accepts any valid .dys name (minus the .dys suffix) plus standard domain formats
	ExternalNameRegex = regexp.MustCompile(ExternalNameRegexString)
)

// ValidDenomRegexString validates coin denoms for both .dys and external names
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

// ValidateName validates a name string for the commit-reveal registration process.
// This is intentionally restrictive to prevent namespace confusion and squatting.
func ValidateName(name string) error {
	if len(name) == 0 {
		return sdkerrors.Wrap(ErrInvalidName, "name cannot be empty")
	}

	// must only contain ".dys" at the end
	if !strings.HasSuffix(name, ".dys") {
		return sdkerrors.Wrap(ErrInvalidName, "name must end with .dys")
	}
	// Check name format
	if !NameRegex.MatchString(name) {
		return sdkerrors.Wrap(ErrInvalidName, "invalid name format: must be lowercase, start with a letter, contain only alphanumeric and dash characters, and end with .dys")
	}

	// Names cannot contain "dys" substring (e.g., "odyssey.dys", "analysis.dys" are invalid).
	// This is BY DESIGN to:
	// 1. Prevent confusion with the native "dys" token denomination
	// 2. Reserve "dys"-containing names for protocol use (governance can create via CreateExternalName)
	// 3. Avoid namespace squatting on protocol-related terms
	if strings.Contains(strings.TrimSuffix(name, ".dys"), "dys") {
		return sdkerrors.Wrap(ErrInvalidName, "name cannot contain 'dys'")
	}

	return nil
}
