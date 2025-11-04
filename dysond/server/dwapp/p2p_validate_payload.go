package dwapp

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/telemetry"
)

// ValidatePubSubPayload parses a pubsub payload, extracts adr36_tx_json, and
// applies VerifyAndExtract. It returns the signer address and the JSON payload body.
func (s *P2PService) ValidatePubSubPayload(ctx context.Context, clientCtx client.Context, topic string, payload []byte, peerID string) (string, string, error) {
	if s == nil {
		return "", "", fmt.Errorf("p2p service unavailable")
	}
	if len(payload) > s.cfg.MaxEnvelope {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "envelope_size")
		return "", "", fmt.Errorf("envelope too large: %d bytes", len(payload))
	}

	var envelope struct {
		ADR36TxJSON string `json:"adr36_tx_json"`
		V           int    `json:"v"`
	}
	if err := json.Unmarshal(payload, &envelope); err != nil {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "malformed_json")
		return "", "", fmt.Errorf("invalid payload json: %w", err)
	}
	if envelope.ADR36TxJSON == "" {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "missing_tx")
		return "", "", fmt.Errorf("missing adr36_tx_json")
	}
	signer, payloadB64, err := s.VerifyAndExtract(ctx, clientCtx, topic, peerID, envelope.ADR36TxJSON)
	if err != nil {
		return "", "", err
	}
	return signer, payloadB64, nil
}
