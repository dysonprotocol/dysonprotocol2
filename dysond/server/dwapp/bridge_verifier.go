package dwapp

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/cosmos/cosmos-sdk/client"

	nameservicev1 "dysonprotocol.com/x/nameservice/types"
)

// VerifyAndExtract validates an ADR-36 (DIRECT) Tx JSON against topic rules and
// returns the recovered signer and payload_b64 if valid.
func (s *P2PService) VerifyAndExtract(ctx context.Context, clientCtx client.Context, topic string, expectedPeerID string, adr36TxJSON string) (string, string, error) {
	if s == nil {
		return "", "", fmt.Errorf("p2p service unavailable")
	}
	parts := strings.Split(strings.TrimPrefix(topic, "/"), "/")
	if len(parts) < 3 {
		return "", "", fmt.Errorf("invalid topic structure: %s", topic)
	}
	addressOrName := parts[2]
	rnReq := &nameservicev1.QueryResolveNameRequest{NameOrAddress: strings.ToLower(strings.TrimSpace(addressOrName))}
	rnResp := &nameservicev1.QueryResolveNameResponse{}
	if err := clientCtx.Invoke(ctx, "/dysonprotocol.nameservice.v1.Query/ResolveName", rnReq, rnResp); err != nil {
		return "", "", fmt.Errorf("resolve failed: %w", err)
	}
	resolvedAddr := strings.ToLower(strings.TrimSpace(rnResp.Address))

	signer, appDomain, dataJSON, metadataJSON, err := VerifyADR36TxJSON(ctx, clientCtx, adr36TxJSON)
	if err != nil {
		return "", "", err
	}
	if signer != resolvedAddr {
		return "", "", fmt.Errorf("signer mismatch: %s != %s", signer, resolvedAddr)
	}
	if appDomain != topic {
		return "", "", fmt.Errorf("app_domain mismatch: %s != %s", appDomain, topic)
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

	if len(dataJSON) > s.cfg.MaxPayload {
		return "", "", fmt.Errorf("payload too large: %d bytes", len(dataJSON))
	}

	return signer, dataJSON, nil
}
