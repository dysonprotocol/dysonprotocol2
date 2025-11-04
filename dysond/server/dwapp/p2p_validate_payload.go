package dwapp

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/telemetry"
)

const (
	maxEnvelopeSize = 64 * 1024
	maxPayloadSize  = 48 * 1024
)

// ValidatePubSubPayload parses a pubsub payload, extracts adr36_tx_json, and
// applies VerifyAndExtract. It returns the signer address and the JSON payload body.
func ValidatePubSubPayload(ctx context.Context, clientCtx client.Context, topic string, payload []byte, peerID string) (string, string, error) {
	fmt.Printf("[DWApp] ValidatePubSubPayload: topic=%s payloadLen=%d\n", topic, len(payload))
	if len(payload) > maxEnvelopeSize {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "envelope_size")
		err := fmt.Errorf("envelope too large: %d bytes", len(payload))
		fmt.Printf("[DWApp] ValidatePubSubPayload REJECT: %v\n", err)
		return "", "", err
	}

	var envelope struct {
		ADR36TxJSON string `json:"adr36_tx_json"`
		V           int    `json:"v"`
	}
	if err := json.Unmarshal(payload, &envelope); err != nil {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "malformed_json")
		fmt.Printf("[DWApp] ValidatePubSubPayload REJECT: invalid json: %v\n", err)
		return "", "", fmt.Errorf("invalid payload json: %w", err)
	}
	if envelope.ADR36TxJSON == "" {
		telemetry.IncrCounter(1, "libp2p", "validator", "reject", "missing_tx")
		fmt.Printf("[DWApp] ValidatePubSubPayload REJECT: missing adr36_tx_json\n")
		return "", "", fmt.Errorf("missing adr36_tx_json")
	}
	signer, payloadB64, err := VerifyAndExtract(ctx, clientCtx, topic, peerID, envelope.ADR36TxJSON)
	if err != nil {
		fmt.Printf("[DWApp] ValidatePubSubPayload REJECT: VerifyAndExtract failed: %v\n", err)
		return "", "", err
	}
	fmt.Printf("[DWApp] ValidatePubSubPayload ACCEPT: topic=%s signer=%s\n", topic, signer)
	return signer, payloadB64, nil
}
