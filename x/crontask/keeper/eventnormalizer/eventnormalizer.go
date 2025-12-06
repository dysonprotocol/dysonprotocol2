package eventnormalizer

import (
	"encoding/json"
	"strings"
)

// Event represents the structure of an input event from the blockchain response.
type Event struct {
	Type       string      `json:"type"`
	Attributes []Attribute `json:"attributes"`
}

// Attribute represents a key-value pair within an event.
type Attribute struct {
	Key   string `json:"key"`
	Value string `json:"value"`
	Index bool   `json:"index"`
}

// NormalizedEvents is a map where keys are event types and values are lists of normalized attribute maps.
// This structure handles multiple events of the same type.
type NormalizedEvent struct {
	Type       string         `json:"type"`
	Attributes map[string]any `json:"attributes"`
}

// NormalizeEvents processes a list of events, normalizing their attributes and grouping by type.
// Attributes are parsed recursively: quoted strings are unquoted, and JSON-like values are decoded into maps or arrays.
func NormalizeEvent(event Event) NormalizedEvent {
	result := NormalizedEvent{
		Type:       event.Type,
		Attributes: make(map[string]any),
	}

	attrs := make(map[string]any)
	for _, attr := range event.Attributes {
		parsed := parseValue(attr.Value)
		attrs[attr.Key] = parsed
	}
	result.Attributes = attrs

	return result
}

// parseValue attempts to parse a raw string value into a more structured form.
func parseValue(raw string) interface{} {
	trimmed := strings.TrimSpace(raw)

	// Check for JSON object or array.
	if strings.HasPrefix(trimmed, "{") || strings.HasPrefix(trimmed, "[") {
		var v interface{}
		if err := json.Unmarshal([]byte(raw), &v); err == nil {
			return deepParse(v)
		}
	}

	// Check for quoted string.
	if strings.HasPrefix(trimmed, "\"") && strings.HasSuffix(trimmed, "\"") {
		var s string
		if err := json.Unmarshal([]byte(raw), &s); err == nil {
			return deepParse(s)
		}
	}

	// Fallback: attempt general JSON unmarshal (e.g., for bare numbers, booleans).
	var v interface{}
	if err := json.Unmarshal([]byte(raw), &v); err == nil {
		return deepParse(v)
	}

	// If nothing matches, return the raw string.
	return raw
}

// maxParseDepth limits recursion depth to prevent stack overflow on maliciously nested JSON.
const maxParseDepth = 100

// deepParse recursively parses values, decoding nested JSON strings into structures where appropriate.
func deepParse(v interface{}) interface{} {
	return deepParseWithDepth(v, 0)
}

func deepParseWithDepth(v interface{}, depth int) interface{} {
	if depth > maxParseDepth {
		return v // Stop recursing, return as-is
	}
	switch vv := v.(type) {
	case string:
		trimmed := strings.TrimSpace(vv)
		if strings.HasPrefix(trimmed, "{") || strings.HasPrefix(trimmed, "[") {
			var inner interface{}
			if err := json.Unmarshal([]byte(vv), &inner); err == nil {
				return deepParseWithDepth(inner, depth+1)
			}
		}
		return vv
	case map[string]interface{}:
		for key, val := range vv {
			vv[key] = deepParseWithDepth(val, depth+1)
		}
		return vv
	case []interface{}:
		for i, val := range vv {
			vv[i] = deepParseWithDepth(val, depth+1)
		}
		return vv
	default:
		return vv
	}
}
