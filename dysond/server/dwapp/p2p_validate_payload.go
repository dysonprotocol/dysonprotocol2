package dwapp

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/telemetry"
)

const maxEnvelopeSize = 64 * 1024

// ValidatePubSubPayload validates a GossipSub message:
// 1. Size check (<= 64KB)
// 2. Parse envelope {body, auth_info, signatures}
// 3. Reconstruct tx JSON, call VerifyADR36TxJSON
// 4. Verify app_domain == topic
// 5. Verify metadata.peerId == senderPeerID
func (s *P2PService) ValidatePubSubPayload(ctx context.Context, clientCtx client.Context, topic string, payload []byte, senderPeerID string) (signer, data string, err error) {
	// 1. Size check
	if len(payload) > maxEnvelopeSize {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "envelope_size")
		return "", "", fmt.Errorf("envelope too large: %d bytes", len(payload))
	}

	// 2. Parse flat envelope format
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

	// 3. Reconstruct tx JSON for verification
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

	// 4. Call VerifyADR36TxJSON
	signer, appDomain, dataJSON, metadataJSON, err := VerifyADR36TxJSON(ctx, clientCtx, string(txJSONBytes))
	if err != nil {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "adr36_failed")
		return "", "", err
	}

	// 5. Validate app_domain matches topic
	if appDomain != topic {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "app_domain_mismatch")
		return "", "", fmt.Errorf("app_domain mismatch: %s != %s", appDomain, topic)
	}

	// 6. Extract and validate peerId from metadata
	var metadata map[string]json.RawMessage
	if err := json.Unmarshal([]byte(metadataJSON), &metadata); err != nil {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "invalid_metadata")
		return "", "", fmt.Errorf("invalid metadata json: %w", err)
	}

	peerRaw, ok := metadata["peerId"]
	if !ok {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "missing_peer_id")
		return "", "", fmt.Errorf("missing peerId in metadata")
	}
	var peerID string
	if err := json.Unmarshal(peerRaw, &peerID); err != nil {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "invalid_peer_id")
		return "", "", fmt.Errorf("invalid peerId field in metadata: %w", err)
	}
	peerID = strings.TrimSpace(peerID)
	if peerID == "" {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "empty_peer_id")
		return "", "", fmt.Errorf("empty peerId in metadata")
	}

	// Validate peerId matches sender (only if senderPeerID provided)
	if trimmedExpected := strings.TrimSpace(senderPeerID); trimmedExpected != "" && peerID != trimmedExpected {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "peer_id_mismatch")
		return "", "", fmt.Errorf("peerId mismatch: metadata=%s sender=%s", peerID, trimmedExpected)
	}

	// 7. Return success
	return signer, dataJSON, nil
}
