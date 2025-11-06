package dwapp

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/cosmos/cosmos-sdk/client"
)

// VerifyAndExtract validates an ADR-36 (DIRECT) Tx JSON against topic rules and
// returns the recovered signer and payload_b64 if valid.
func (s *P2PService) VerifyAndExtract(ctx context.Context, clientCtx client.Context, topic string, expectedPeerID string, adr36TxJSON string) (string, string, error) {
	if s == nil {
		return "", "", fmt.Errorf("p2p service unavailable")
	}
	signer, _, dataJSON, metadataJSON, err := VerifyADR36TxJSON(ctx, clientCtx, adr36TxJSON)
	if err != nil {
		return "", "", err
	}

	// Extract peerId from metadata
	var metadata map[string]json.RawMessage
	if err := json.Unmarshal([]byte(metadataJSON), &metadata); err != nil {
		return "", "", fmt.Errorf("invalid metadata json: %w", err)
	}

	peerRaw, ok := metadata["peerId"]
	if !ok {
		return "", "", fmt.Errorf("missing peerId in metadata")
	}
	var peerID string
	if err := json.Unmarshal(peerRaw, &peerID); err != nil {
		return "", "", fmt.Errorf("invalid peerId field in metadata: %w", err)
	}
	peerID = strings.TrimSpace(peerID)
	if peerID == "" {
		return "", "", fmt.Errorf("missing peerId in metadata")
	}
	if trimmedExpected := strings.TrimSpace(expectedPeerID); trimmedExpected != "" && peerID != trimmedExpected {
		return "", "", fmt.Errorf("peerId mismatch: payload=%s sender=%s", peerID, trimmedExpected)
	}

	return signer, dataJSON, nil
}
