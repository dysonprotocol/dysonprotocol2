package keeper

import (
	"testing"
)

func TestParseAffiliateName(t *testing.T) {
	tests := []struct {
		name     string
		memo     string
		expected string
	}{
		// Valid cases - must match nameservice regex: ^[a-z]([-a-z0-9]*[a-z0-9])?\.dys$
		{name: "valid dysname", memo: "alice.dys", expected: "alice.dys"},
		{name: "uppercase dysname", memo: "ALICE.DYS", expected: "alice.dys"},
		{name: "mixed case", memo: "AlIcE.DyS", expected: "alice.dys"},
		{name: "with spaces", memo: "  alice.dys  ", expected: "alice.dys"},
		{name: "with numbers", memo: "test123.dys", expected: "test123.dys"},
		{name: "with dash", memo: "my-name.dys", expected: "my-name.dys"},
		{name: "single letter", memo: "a.dys", expected: "a.dys"},
		{name: "letter and number", memo: "a1.dys", expected: "a1.dys"},

		// Invalid cases - rejected by nameservice regex
		{name: "empty memo", memo: "", expected: ""},
		{name: "no .dys suffix", memo: "alice", expected: ""},
		{name: "wrong suffix .com", memo: "alice.com", expected: ""},
		{name: "wrong suffix .eth", memo: "alice.eth", expected: ""},
		{name: "only .dys", memo: ".dys", expected: ""},                // must start with letter
		{name: "starts with number", memo: "123abc.dys", expected: ""}, // must start with letter
		{name: "starts with dash", memo: "-alice.dys", expected: ""},   // must start with letter
		{name: "ends with dash", memo: "alice-.dys", expected: ""},     // must end with alphanumeric
		{name: "subdomain dots", memo: "sub.domain.dys", expected: ""}, // dots not allowed in name part
		{name: "underscore", memo: "alice_bob.dys", expected: ""},      // underscore not allowed
		{name: "just spaces", memo: "   ", expected: ""},
		{name: "too long", memo: string(make([]byte, 200)), expected: ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ParseAffiliateName(tt.memo)
			if result != tt.expected {
				t.Errorf("ParseAffiliateName(%q) = %q, want %q", tt.memo, result, tt.expected)
			}
		})
	}
}

func TestParseAffiliateNameEdgeCases(t *testing.T) {
	// Test max length with valid characters (a + 122 alphanumeric + .dys = 127 chars)
	// Nameservice regex requires: start with letter, alphanumeric/dash middle, end with alphanumeric
	longName := "a" + string(makeAlphanumeric(122)) + ".dys" // 1 + 122 + 4 = 127
	result := ParseAffiliateName(longName)
	if result == "" {
		t.Errorf("ParseAffiliateName with valid 127-char name should succeed, got empty")
	}

	// Test that length limit still applies
	tooLong := "a" + string(makeAlphanumeric(130)) + ".dys" // > 128
	result = ParseAffiliateName(tooLong)
	if result != "" {
		t.Errorf("ParseAffiliateName with >128 chars should fail, got %q", result)
	}
}

// makeAlphanumeric creates a byte slice of lowercase letters/numbers
func makeAlphanumeric(n int) []byte {
	b := make([]byte, n)
	for i := range b {
		b[i] = 'a' + byte(i%26)
	}
	return b
}
