package types

import (
	"regexp"
	"strings"

	sdkerrors "cosmossdk.io/errors"
)

var (
	// NameRegexString defines the regex string for valid name strings
	// Must be lowercase alphanumeric, start with a letter, may contain dashes, and must end with ".dys"
	NameRegexString = `^[a-z]([-a-z0-9]*[a-z0-9])?\.dys$`

	// NameRegex is the compiled regex for valid name strings
	NameRegex = regexp.MustCompile(NameRegexString)

	// ExternalNameRegex defines the regex for valid external domain names
	// Must be lowercase alphanumeric with dashes, optionally following domain/subdomain format
	// Single words without dots are allowed (e.g., "example", "myapp")
	// No consecutive dashes allowed
	ExternalNameRegex = regexp.MustCompile(`^[a-z]([a-z0-9]|-[a-z0-9])*(\.[a-z0-9]([a-z0-9]|-[a-z0-9])*)*$`)
)

// ValidDenomRegexString composes a coin denom regex based on NameRegexString,
// allowing optional subdenoms separated by '/'
var ValidDenomRegexString = func() string {
	// embed NameRegexString without start/end anchors
	core := strings.TrimSuffix(strings.TrimPrefix(NameRegexString, "^"), "$")
	return "^" + core + `(?:/[0-9A-Za-z:_.-]+)*$`
}()

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

// ValidateName validates a name string
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

	// must not contain "udys" anywhere else after stripping the .dys suffix
	if strings.Contains(strings.TrimSuffix(name, ".dys"), "dys") {
		return sdkerrors.Wrap(ErrInvalidName, "name cannot contain 'dys'")
	}

	return nil
}
