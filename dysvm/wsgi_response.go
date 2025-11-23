package dysvm

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
)

type wsgiResponsePayload struct {
	ResponseB64 string `json:"response_b64"`
	Logs        string `json:"logs"`
}

func decodeWsgiResponse(raw []byte) ([]byte, string, error) {
	raw = bytes.TrimSpace(raw)
	if len(raw) == 0 {
		return nil, "", fmt.Errorf("empty response")
	}
	var payload wsgiResponsePayload
	if err := json.Unmarshal(raw, &payload); err != nil {
		return nil, "", fmt.Errorf("invalid json: %w", err)
	}
	if payload.ResponseB64 == "" {
		return nil, payload.Logs, fmt.Errorf("missing response_b64")
	}
	body, err := base64.StdEncoding.DecodeString(payload.ResponseB64)
	if err != nil {
		return nil, payload.Logs, fmt.Errorf("failed to decode response: %w", err)
	}
	return body, payload.Logs, nil
}
