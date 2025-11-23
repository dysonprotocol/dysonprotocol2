package keeper

import (
	"bytes"
	"encoding/json"
	"sort"
	"strings"

	errorsmod "cosmossdk.io/errors"
)

// minifyJSONArray validates that the input is a JSON array and returns a compact representation
func minifyJSONArray(raw string) (string, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "[]", nil
	}
	var v []any
	if err := json.Unmarshal([]byte(trimmed), &v); err != nil {
		return "", errorsmod.Wrapf(err, "invalid JSON array")
	}
	b, err := marshalDeterministic(v)
	if err != nil {
		return "", errorsmod.Wrapf(err, "failed to encode JSON array")
	}
	return string(b), nil
}

// minifyJSONObject validates that the input is a JSON object and returns a compact representation
func minifyJSONObject(raw string) (string, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "{}", nil
	}
	var v map[string]any
	if err := json.Unmarshal([]byte(trimmed), &v); err != nil {
		return "", errorsmod.Wrapf(err, "invalid JSON object")
	}
	b, err := marshalDeterministic(v)
	if err != nil {
		return "", errorsmod.Wrapf(err, "failed to encode JSON object")
	}
	return string(b), nil
}

// marshalDeterministic encodes JSON with lexicographically-sorted object keys for deterministic bytes.
func marshalDeterministic(v any) ([]byte, error) {
	switch vv := v.(type) {
	case map[string]any:
		keys := make([]string, 0, len(vv))
		for k := range vv {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		buf := bytes.NewBuffer(make([]byte, 0, 256))
		buf.WriteByte('{')
		for i, k := range keys {
			kb, _ := json.Marshal(k)
			buf.Write(kb)
			buf.WriteByte(':')
			vb, err := marshalDeterministic(vv[k])
			if err != nil {
				return nil, err
			}
			buf.Write(vb)
			if i < len(keys)-1 {
				buf.WriteByte(',')
			}
		}
		buf.WriteByte('}')
		return buf.Bytes(), nil
	case []any:
		buf := bytes.NewBuffer(make([]byte, 0, 256))
		buf.WriteByte('[')
		for i, el := range vv {
			eb, err := marshalDeterministic(el)
			if err != nil {
				return nil, err
			}
			buf.Write(eb)
			if i < len(vv)-1 {
				buf.WriteByte(',')
			}
		}
		buf.WriteByte(']')
		return buf.Bytes(), nil
	default:
		return json.Marshal(v)
	}
}
