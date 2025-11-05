package dwapp

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/telemetry"
)

// ValidatePubSubPayload parses a pubsub payload with flat MsgArbitraryData structure,
// reconstructs the tx JSON for verification, and applies VerifyAndExtract.
// It returns the signer address and the JSON payload body.
func (s *P2PService) ValidatePubSubPayload(ctx context.Context, clientCtx client.Context, topic string, payload []byte, peerID string) (string, string, error) {
	if s == nil {
		return "", "", fmt.Errorf("p2p service unavailable")
	}
	if len(payload) > s.cfg.MaxEnvelope {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "envelope_size")
		return "", "", fmt.Errorf("envelope too large: %d bytes", len(payload))
	}

	var envelope struct {
		Body       json.RawMessage `json:"body"`
		AuthInfo   json.RawMessage `json:"auth_info"`
		Signatures []string        `json:"signatures"`
	}
	if err := json.Unmarshal(payload, &envelope); err != nil {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "malformed_json")
		return "", "", fmt.Errorf("invalid payload json: %w", err)
	}
	if len(envelope.Body) == 0 || len(envelope.AuthInfo) == 0 || len(envelope.Signatures) == 0 {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "missing_fields")
		return "", "", fmt.Errorf("missing required fields: body, auth_info, or signatures")
	}

	// Reconstruct tx JSON for verification
	txJSON := map[string]interface{}{
		"body":       json.RawMessage(envelope.Body),
		"auth_info":  json.RawMessage(envelope.AuthInfo),
		"signatures": envelope.Signatures,
	}
	txJSONBytes, err := json.Marshal(txJSON)
	if err != nil {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "marshal_failed")
		return "", "", fmt.Errorf("failed to marshal tx json: %w", err)
	}

	signer, payloadB64, err := s.VerifyAndExtract(ctx, clientCtx, topic, peerID, string(txJSONBytes))
	if err != nil {
		return "", "", err
	}
	return signer, payloadB64, nil
}
