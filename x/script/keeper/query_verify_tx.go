package keeper

import (
	"context"
	"fmt"

	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	txsigning "cosmossdk.io/x/tx/signing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/cosmos/cosmos-sdk/client"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	authsigning "github.com/cosmos/cosmos-sdk/x/auth/signing"
	"github.com/cosmos/cosmos-sdk/x/auth/tx"
	"google.golang.org/protobuf/types/known/anypb"
)

// VerifyTx verifies the signatures of an arbitrary transaction for MsgArbitraryData.
//
// Semantics:
//   - Parses transaction JSON into a signable transaction.
//   - Validates transaction structure (single signature, proper signers).
//   - Verifies signature using ADR-036 arbitrary signature rules.
//   - Returns the signer address if verification succeeds.
//
// Validation:
//   - Transaction JSON must be non-empty and valid.
//   - JSON size must not exceed 50,000 characters.
//   - Transaction must be properly formed with signatures.
//   - Must have exactly one signature.
//   - Signer addresses must match signature public keys.
//
// Returns:
//   - *scripttypes.QueryVerifyTxResponse with the verified signer address.
//
// Errors are returned on invalid JSON, malformed transactions, signature failures, or validation errors; no panics.
//
// Example:
//
//	A valid MsgArbitraryData transaction for verification:
//
//	{
//	  "body": {
//	    "messages": [
//	      {
//	        "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
//	        "signer": "dys1example_address",
//	        "data": "arbitrary data to sign",
//	        "app_domain": "my_app/v1.0",
//	        "metadata": "{}"
//	      }
//	    ],
//	    "memo": "",
//	    "timeout_height": "0"
//	  },
//	  "auth_info": {
//	    "signer_infos": [
//	      {
//	        "public_key": {
//	          "@type": "/cosmos.crypto.secp256k1.PubKey",
//	          "key": "base64_encoded_public_key"
//	        },
//	        "mode_info": {
//	          "single": {
//	            "mode": "SIGN_MODE_DIRECT"
//	          }
//	        },
//	        "sequence": "0"
//	      }
//	    ],
//	    "fee": {
//	      "amount": [],
//	      "gas_limit": "0"
//	    }
//	  },
//	  "signatures": [
//	    "base64_encoded_signature"
//	  ]
//	}
//
// CLI Example:
//
//	# Create a signed MsgArbitraryData transaction for verification
//	dysond tx script sign-arbitrary-data "your data to sign" --app-domain "my_app/v1.0" --from alice --chain-id "" --account-number 0 --sequence 0 --offline --output-document signed_tx.json
//
//	# Verify the signed transaction
//	dysond query script verify-tx --tx-json "$(cat signed_tx.json)" -o json
func (k Keeper) VerifyTx(ctx context.Context, req *scripttypes.QueryVerifyTxRequest) (*scripttypes.QueryVerifyTxResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "request cannot be nil")
	}
	if req.TxJson == "" {
		return nil, status.Error(codes.InvalidArgument, "empty transaction JSON")
	}

	// Maximum size check to prevent abuse
	if len(req.TxJson) > 50_000 {
		return nil, status.Error(codes.InvalidArgument, "transaction JSON too large")
	}

	// Create a new TxConfig for transaction handling
	txConfig := tx.NewTxConfig(k.cdc, tx.DefaultSignModes)

	// Create a client context with our TxConfig and codec
	clientCtx := client.Context{
		TxConfig: txConfig,
		Codec:    k.cdc,
	}

	// Parse the transaction from JSON
	txBuilder, err := clientCtx.TxConfig.TxJSONDecoder()([]byte(req.TxJson))
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "failed to decode transaction: %s", err.Error())
	}

	// Cast to a signable transaction
	sigTx, ok := txBuilder.(authsigning.SigVerifiableTx)
	if !ok {
		return nil, status.Error(codes.InvalidArgument, "transaction does not implement SigVerifiableTx")
	}

	// Get the signature data and signers
	sigs, err := sigTx.GetSignaturesV2()
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "failed to get signatures: %s", err.Error())
	}

	// Check if we have any signatures
	if len(sigs) == 0 {
		return nil, status.Error(codes.InvalidArgument, "transaction has no signatures")
	}

	if len(sigs) > 1 {
		return nil, status.Error(codes.InvalidArgument, "transaction has multiple signatures")
	}

	signers, err := sigTx.GetSigners()
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "failed to get signers: %s", err.Error())
	}

	// Check that signer length and signature length are the same
	if len(sigs) != len(signers) {
		return nil, status.Errorf(codes.InvalidArgument, "invalid number of signers; expected: %d, got %d", len(signers), len(sigs))
	}

	//chainID := sdkCtx.ChainID()
	// Chain id, account number, and account sequence must be empty for arbitrary signature
	// See: https://docs.cosmos.network/main/build/architecture/adr-036-arbitrary-signature
	chainID := ""
	accountNumber := uint64(0)
	accountSequence := uint64(0)

	// Verify each signature
	signModeHandler := clientCtx.TxConfig.SignModeHandler()

	signerAddress := ""

	fmt.Printf("[VerifyTx] verifying %d signatures with chainID=%q accountNumber=%d sequence=%d\n",
		len(sigs), chainID, accountNumber, accountSequence)

	for i, sig := range sigs {
		pubKey := sig.PubKey
		if pubKey == nil {
			return nil, status.Error(codes.InvalidArgument, "public key is missing")
		}

		signerAddr := sdk.AccAddress(pubKey.Address())
		if !signerAddr.Equals(sdk.AccAddress(signers[i])) {
			return nil, status.Errorf(codes.InvalidArgument, "signature does not match its respective signer; expected: %s, got: %s", sdk.AccAddress(signers[i]), signerAddr)
		}

		// ADR-36 does not require the account to exist on-chain; we verify against the pubkey in the TX

		// Setup signer data
		anyPk, err := codectypes.NewAnyWithValue(pubKey)
		if err != nil {
			return nil, status.Errorf(codes.Internal, "failed to pack public key: %s", err.Error())
		}

		signerData := txsigning.SignerData{
			Address:       signerAddr.String(),
			ChainID:       chainID,
			AccountNumber: accountNumber,
			Sequence:      accountSequence,
			PubKey: &anypb.Any{
				TypeUrl: anyPk.TypeUrl,
				Value:   anyPk.Value,
			},
		}

		adaptableTx, ok := txBuilder.(authsigning.V2AdaptableTx)
		if !ok {
			return nil, status.Errorf(codes.InvalidArgument, "expected tx to implement V2AdaptableTx, got %T", txBuilder)
		}
		txData := adaptableTx.GetSigningTxData()

		// Verify the signature
		fmt.Printf("[VerifyTx] verifying signature %d: signerAddr=%s pubkey=%x\n", i, signerAddr.String(), pubKey.Bytes())
		err = authsigning.VerifySignature(ctx, pubKey, signerData, sig.Data, signModeHandler, txData)
		if err != nil {
			fmt.Printf("[VerifyTx] signature verification FAILED: %v\n", err)
			return nil, status.Errorf(codes.Unauthenticated, "signature [%d] verification failed (make sure the --chain-id=\"\", --account-number=0, and --sequence=0): %s", i, err.Error())
		}

		fmt.Printf("[VerifyTx] signature %d VALID\n", i)
		signerAddress = signerAddr.String()
	}

	// All signatures have been successfully verified
	return &scripttypes.QueryVerifyTxResponse{
		Signer: signerAddress,
	}, nil
}
