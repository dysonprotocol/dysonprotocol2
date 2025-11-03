package dwapp

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/cosmos/cosmos-sdk/client"

	nameservicev1 "dysonprotocol.com/x/nameservice/types"
)

// VerifyAndExtract validates an ADR-36 (DIRECT) Tx JSON against topic rules and
// returns the recovered signer and payload_b64 if valid.
func VerifyAndExtract(ctx context.Context, clientCtx client.Context, topic string, adr36TxJSON string) (string, string, error) {
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

	var data struct {
		PayloadB64 string `json:"payload_b64"`
		Ts         int64  `json:"ts"`
		NonceB64   string `json:"nonce_b64"`
		PeerID     string `json:"peerId"`
	}
	if err := json.Unmarshal([]byte(dataJSON), &data); err != nil {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: invalid data json: %v\n", err)
		return "", "", fmt.Errorf("invalid data json: %w", err)
	}
	if data.PayloadB64 == "" {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: missing payload_b64\n")
		return "", "", fmt.Errorf("missing payload_b64")
	}
	if data.NonceB64 == "" {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: missing nonce_b64\n")
		return "", "", fmt.Errorf("missing nonce_b64")
	}
	if data.Ts == 0 {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: missing ts\n")
		return "", "", fmt.Errorf("missing ts")
	}

	payloadBytes, err := base64.StdEncoding.DecodeString(data.PayloadB64)
	if err != nil {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: payload base64 decode: %v\n", err)
		return "", "", fmt.Errorf("payload base64 decode: %w", err)
	}
	if len(payloadBytes) > maxPayloadSize {
		err := fmt.Errorf("payload too large: %d bytes", len(payloadBytes))
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: %v\n", err)
		return "", "", err
	}

	nonceBytes, err := base64.StdEncoding.DecodeString(data.NonceB64)
	if err != nil {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: nonce base64 decode: %v\n", err)
		return "", "", fmt.Errorf("nonce base64 decode: %w", err)
	}
	if len(nonceBytes) == 0 {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: nonce cannot be empty\n")
		return "", "", fmt.Errorf("nonce cannot be empty")
	}

	now := time.Now()
	msgTime := time.Unix(data.Ts, 0)
	if msgTime.Before(now.Add(-maxClockSkew)) || msgTime.After(now.Add(maxClockSkew)) {
		err := fmt.Errorf("timestamp out of range: %d", data.Ts)
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: %v\n", err)
		return "", "", err
	}
	if !rememberNonce(topic, signer, data.NonceB64, now) {
		fmt.Printf("[DWApp] VerifyAndExtract REJECT: duplicate nonce\n")
		return "", "", fmt.Errorf("duplicate nonce")
	}

	fmt.Printf("[DWApp] VerifyAndExtract ACCEPT: topic=%s signer=%s\n", topic, signer)
	return signer, data.PayloadB64, nil
}
