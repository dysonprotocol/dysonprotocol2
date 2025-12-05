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
		// Valid cases
		{name: "valid dysname", memo: "alice.dys", expected: "alice.dys"},
		{name: "uppercase dysname", memo: "ALICE.DYS", expected: "alice.dys"},
		{name: "mixed case", memo: "AlIcE.DyS", expected: "alice.dys"},
		{name: "with spaces", memo: "  alice.dys  ", expected: "alice.dys"},
		{name: "subdomain", memo: "sub.domain.dys", expected: "sub.domain.dys"},
		{name: "numeric", memo: "test123.dys", expected: "test123.dys"},

		// Invalid cases
		{name: "empty memo", memo: "", expected: ""},
		{name: "no .dys suffix", memo: "alice", expected: ""},
		{name: "wrong suffix .com", memo: "alice.com", expected: ""},
		{name: "wrong suffix .eth", memo: "alice.eth", expected: ""},
		{name: "only .dys", memo: ".dys", expected: ".dys"},
		{name: "just spaces", memo: "   ", expected: ""},
		{name: "too long", memo: string(make([]byte, 200)), expected: ""},
		{name: "exactly 128 chars with .dys", memo: string(make([]byte, 124)) + ".dys", expected: string(make([]byte, 124)) + ".dys"},
		{name: "129 chars - too long", memo: string(make([]byte, 125)) + ".dys", expected: ""},
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
	// Test exact boundary at 128 characters
	memo128 := string(make([]byte, 124)) + ".dys" // 124 + 4 = 128
	result := ParseAffiliateName(memo128)
	if result == "" {
		t.Errorf("ParseAffiliateName with 128 chars should succeed, got empty")
	}

	memo129 := string(make([]byte, 125)) + ".dys" // 125 + 4 = 129
	result = ParseAffiliateName(memo129)
	if result != "" {
		t.Errorf("ParseAffiliateName with 129 chars should fail, got %q", result)
	}
}
