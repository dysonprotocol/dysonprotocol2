package types

import (
	"testing"
)

func TestExternalNameRegex(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected bool
	}{
		// Valid cases
		{"simple domain", "example.com", true},
		{"subdomain", "sub.domain.org", true},
		{"minimal domain", "a.b", true},
		{"multiple subdomains", "www.sub.example.com", true},
		{"domain with numbers", "site1.example2.org", true},
		{"domain with dashes", "my-site.example-domain.com", true},
		{"no dots (single word)", "example", true},
		{"single letter", "a", true},

		// Punycode support (internationalized domain names)
		{"punycode domain", "xn--nxasmq5a.com", true},           // Greek "κόσμε"
		{"punycode subdomain", "www.xn--n3h.com", true},         // Emoji domain
		{"punycode only", "xn--80akhbyknj4f", true},             // Russian word
		{"consecutive dashes mid-label", "ex--ample.com", true}, // Allowed for punycode compat

		// Invalid cases
		{"starts with dot", ".com", false},
		{"ends with dot", "example.", false},
		{"starts with dash", "-example.com", false},
		{"ends with dash in label", "example-.com", false},
		{"uppercase", "Example.com", false},
		{"empty string", "", false},
		{"single dot", ".", false},
		{"multiple consecutive dots", "example..com", false},
		{"starts with dash after dot", "example.-com", false},
		{"starts with number", "1example.com", false},
		{"label starts with number", "example.1com", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ExternalNameRegex.MatchString(tt.input)
			if result != tt.expected {
				t.Errorf("ExternalNameRegex.MatchString(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}

func TestNameRegex(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected bool
	}{
		// Valid .dys names
		{"simple name", "foo.dys", true},
		{"single letter", "a.dys", true},
		{"with numbers", "foo123.dys", true},
		{"with dashes", "my-name.dys", true},
		{"punycode name", "xn--test.dys", true},

		// Invalid cases
		{"no suffix", "foo", false},
		{"wrong suffix", "foo.com", false},
		{"starts with number", "1foo.dys", false},
		{"starts with dash", "-foo.dys", false},
		{"ends with dash", "foo-.dys", false},
		{"uppercase", "Foo.dys", false},
		{"empty", "", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := GetNameRegex(DefaultNameSuffix).MatchString(tt.input)
			if result != tt.expected {
				t.Errorf("GetNameRegex(DefaultNameSuffix).MatchString(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}

func TestExternalNameIsSupersetOfName(t *testing.T) {
	// Any valid .dys name (without the .dys suffix) should match ExternalNameRegex
	dysNames := []string{"foo", "a", "my-name", "xn--test", "abc123"}
	for _, name := range dysNames {
		// Verify it's a valid .dys name
		if !GetNameRegex(DefaultNameSuffix).MatchString(name + ".dys") {
			t.Errorf("%q.dys should be valid GetNameRegex(DefaultNameSuffix)", name)
			continue
		}
		// Verify the base name matches ExternalNameRegex
		if !ExternalNameRegex.MatchString(name) {
			t.Errorf("%q should match ExternalNameRegex (superset property)", name)
		}
	}
}

func TestValidDenomRegex(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected bool
	}{
		// .dys name denoms
		{"dys name", "foo.dys", true},
		{"dys name with subdenom", "foo.dys/token", true},
		{"dys name with multi subdenom", "foo.dys/lp/v2", true},

		// External name denoms
		{"external domain", "example.com", true},
		{"external with subdenom", "example.com/token", true},
		{"external multi subdenom", "uniswap.org/lp/eth-usdc", true},
		{"punycode denom", "xn--nxasmq5a.com/token", true},

		// Single label (no dots)
		{"single label", "mytoken", true},
		{"single label with subdenom", "mytoken/v2", true},

		// Invalid cases
		{"starts with number", "1example.com", false},
		{"empty", "", false},
		{"just slash", "/token", false},
		{"starts with slash", "/foo.dys", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ValidDenomRegex.MatchString(tt.input)
			if result != tt.expected {
				t.Errorf("ValidDenomRegex.MatchString(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}
