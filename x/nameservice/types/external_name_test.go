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
		{"no dots (single word)", "example", true}, // External names can be single words
		{"single letter", "a", true},               // Minimal valid external name

		// Invalid cases
		{"starts with dot", ".com", false},
		{"ends with dot", "example.", false},
		{"starts with dash", "-example.com", false},
		{"ends with dash", "example-.com", false},
		{"consecutive dashes", "ex--ample.com", false},
		{"uppercase", "Example.com", false},
		{"empty string", "", false},
		{"single dot", ".", false},
		{"multiple consecutive dots", "example..com", false},
		{"starts with dash after dot", "example.-com", false},
		{"ends with dash before dot", "example-.com", false},
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
