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
		// Accepted - has .dys suffix (resolution will validate further)
		{name: "valid dysname", memo: "alice.dys", expected: "alice.dys"},
		{name: "uppercase dysname", memo: "ALICE.DYS", expected: "alice.dys"},
		{name: "mixed case", memo: "AlIcE.DyS", expected: "alice.dys"},
		{name: "with spaces", memo: "  alice.dys  ", expected: "alice.dys"},
		{name: "with numbers", memo: "test123.dys", expected: "test123.dys"},
		{name: "with dash", memo: "my-name.dys", expected: "my-name.dys"},
		{name: "only .dys", memo: ".dys", expected: ".dys"},                          // resolution will fail
		{name: "starts with number", memo: "123abc.dys", expected: "123abc.dys"},     // resolution will fail
		{name: "subdomain dots", memo: "sub.domain.dys", expected: "sub.domain.dys"}, // resolution will fail

		// Rejected - no .dys suffix
		{name: "empty memo", memo: "", expected: ""},
		{name: "no .dys suffix", memo: "alice", expected: ""},
		{name: "wrong suffix .com", memo: "alice.com", expected: ""},
		{name: "wrong suffix .eth", memo: "alice.eth", expected: ""},
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
	// Test exactly 128 chars (max allowed)
	longName := string(make([]byte, 124)) + ".dys" // 124 + 4 = 128
	result := ParseAffiliateName(longName)
	// Returns lowercased version (null bytes become valid after ToLower)
	if result == "" {
		t.Errorf("ParseAffiliateName with 128 chars should return non-empty")
	}

	// Test 129 chars (too long)
	tooLong := string(make([]byte, 125)) + ".dys" // > 128
	result = ParseAffiliateName(tooLong)
	if result != "" {
		t.Errorf("ParseAffiliateName with >128 chars should fail, got %q", result)
	}
}
