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
func VerifyAndExtract(ctx context.Context, clientCtx client.Context, topic string, expectedPeerID string, adr36TxJSON string) (string, string, error) {
	fmt.Printf("[DWApp] VerifyAndExtract: topic=%s\n", topic)
	// Expect topic format with at least three segments: /{chainId}/v1/{address_or_name}/...
	// Node does not enforce chainId or version values; it only ensures an address/name segment exists.
	parts := strings.Split(strings.TrimPrefix(topic, "/"), "/")
	if len(parts) < 3 {
		err := fmt.Errorf("invalid topic structure: %s", topic)
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: %v\n", err)
		return "", "", err
	}
	addressOrName := parts[2]
	fmt.Printf("[DWApp] VerifyAndExtract: resolving addressOrName=%s\n", addressOrName)
	// Resolve name or address via nameservice on every message (no cache)
	rnReq := &nameservicev1.QueryResolveNameRequest{NameOrAddress: strings.ToLower(strings.TrimSpace(addressOrName))}
	rnResp := &nameservicev1.QueryResolveNameResponse{}
	if err := clientCtx.Invoke(ctx, "/dysonprotocol.nameservice.v1.Query/ResolveName", rnReq, rnResp); err != nil {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: resolve failed: %v\n", err)
		return "", "", fmt.Errorf("resolve failed: %w", err)
	}
	resolvedAddr := strings.ToLower(strings.TrimSpace(rnResp.Address))
	fmt.Printf("[DWApp] VerifyAndExtract: resolved=%s\n", resolvedAddr)

	// Verify ADR-36 and extract fields
	signer, appDomain, dataJSON, err := VerifyADR36TxJSON(ctx, clientCtx, adr36TxJSON)
	if err != nil {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: ADR36 verification failed: %v\n", err)
		return "", "", err
	}
	fmt.Printf("[DWApp] VerifyAndExtract: signer=%s appDomain=%s\n", signer, appDomain)

	if signer != resolvedAddr {
		err := fmt.Errorf("signer mismatch: %s != %s", signer, resolvedAddr)
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: %v\n", err)
		return "", "", err
	}

	// app_domain must equal the full topic
	if appDomain != topic {
		err := fmt.Errorf("app_domain mismatch: %s != %s", appDomain, topic)
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: %v\n", err)
		return "", "", err
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal([]byte(dataJSON), &raw); err != nil {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: invalid data json: %v\n", err)
		return "", "", fmt.Errorf("invalid data json: %w", err)
	}

	peerRaw, ok := raw["peerId"]
	if !ok {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: missing peerId\n")
		return "", "", fmt.Errorf("missing peerId")
	}
	var peerID string
	if err := json.Unmarshal(peerRaw, &peerID); err != nil {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: invalid peerId field: %v\n", err)
		return "", "", fmt.Errorf("invalid peerId field: %w", err)
	}
	peerID = strings.TrimSpace(peerID)
	if peerID == "" {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: missing peerId\n")
		return "", "", fmt.Errorf("missing peerId")
	}
	if trimmedExpected := strings.TrimSpace(expectedPeerID); trimmedExpected != "" && peerID != trimmedExpected {
		err := fmt.Errorf("peerId mismatch: payload=%s sender=%s", peerID, trimmedExpected)
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: %v\n", err)
		return "", "", err
	}

	if len(dataJSON) > maxPayloadSize {
		err := fmt.Errorf("payload too large: %d bytes", len(dataJSON))
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: %v\n", err)
		return "", "", err
	}

	fmt.Printf("[DWApp] VerifyAndExtract ACCEPT: topic=%s signer=%s\n", topic, signer)
	return signer, dataJSON, nil
}
