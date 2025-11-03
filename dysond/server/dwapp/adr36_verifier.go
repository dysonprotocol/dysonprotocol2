package dwapp

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/cosmos/cosmos-sdk/client"

	scriptv1 "dysonprotocol.com/x/script/types"
)

// VerifyADR36TxJSON uses the module's VerifyTx query to validate a DIRECT-signed
// MsgArbitraryData transaction (ADR-36 semantics). It returns the recovered signer
// address, the app_domain, and the raw data string from the first message.
func VerifyADR36TxJSON(ctx context.Context, clientCtx client.Context, txJSON string) (string, string, string, error) {
	// Call in-process query to verify the signature per ADR-36 rules
	req := &scriptv1.QueryVerifyTxRequest{TxJson: txJSON}
	resp := &scriptv1.QueryVerifyTxResponse{}
	if err := clientCtx.Invoke(ctx, "/dysonprotocol.script.v1.Query/VerifyTx", req, resp); err != nil {
		return "", "", "", fmt.Errorf("verify tx failed: %w", err)
	}

	// Parse app_domain and data fields from the first message
	type msgArbitrary struct {
		Type      string `json:"@type"`
		Signer    string `json:"signer"`
		Data      string `json:"data"`
		AppDomain string `json:"app_domain"`
	}

	type txBody struct {
		Body struct {
			Messages []json.RawMessage `json:"messages"`
		} `json:"body"`
	}

	var tb txBody
	if err := json.Unmarshal([]byte(txJSON), &tb); err != nil {
		return "", "", "", fmt.Errorf("invalid tx json: %w", err)
	}
	if len(tb.Body.Messages) != 1 {
		return "", "", "", fmt.Errorf("tx must contain exactly one message")
	}
	var msg msgArbitrary
	if err := json.Unmarshal(tb.Body.Messages[0], &msg); err != nil {
		return "", "", "", fmt.Errorf("invalid message json: %w", err)
	}
	if msg.Type != "/dysonprotocol.script.v1.MsgArbitraryData" {
		return "", "", "", fmt.Errorf("unexpected message type: %s", msg.Type)
	}
	// Cross-check recovered signer matches message signer for sanity
	if resp.Signer != msg.Signer {
		return "", "", "", fmt.Errorf("signer mismatch: verified %s != msg %s", resp.Signer, msg.Signer)
	}

	return resp.Signer, msg.AppDomain, msg.Data, nil
}
