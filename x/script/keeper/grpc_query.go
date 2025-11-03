package keeper

import (
	"context"
	"encoding/json"
	"fmt"

	"dysonprotocol.com/dysvm"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"cosmossdk.io/collections"
	"cosmossdk.io/core/header"
	cosmossdkerrors "cosmossdk.io/errors"
	txsigning "cosmossdk.io/x/tx/signing"

	// For Any
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	// Added for marshalling proto messages

	// Transaction verification imports
	"github.com/cosmos/cosmos-sdk/client"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	authsigning "github.com/cosmos/cosmos-sdk/x/auth/signing"
	"github.com/cosmos/cosmos-sdk/x/auth/tx"
	"google.golang.org/protobuf/types/known/anypb"
)

var _ scripttypes.QueryServer = Keeper{}

// Params queries the parameters of the script module.
//
// Semantics:
//   - Retrieves current script module parameters from the parameter store.
//   - No validation or complex logic required.
//
// Returns:
//   - *scripttypes.QueryParamsResponse with current module parameters.
//
// Errors are returned on parameter retrieval failures; no panics.
func (k Keeper) Params(ctx context.Context, req *scripttypes.QueryParamsRequest) (*scripttypes.QueryParamsResponse, error) {
	params := k.GetParams(ctx)
	return &scripttypes.QueryParamsResponse{Params: params}, nil
}

// ScriptInfo queries script information by address or nameservice name.
//
// Semantics:
//   - Resolves the provided address/name using nameservice if needed.
//   - Retrieves script data including code, version, and update metadata.
//   - Returns NotFound error if script doesn't exist.
//
// Validation:
//   - Address/name parameter must be non-empty.
//   - Resolved address must be a valid bech32 address.
//
// Returns:
//   - *scripttypes.QueryScriptInfoResponse with complete script information.
//   - NotFound error if script doesn't exist at resolved address.
//
// Errors are returned on empty parameters, resolution failures, or storage errors; no panics.
func (k Keeper) ScriptInfo(ctx context.Context, req *scripttypes.QueryScriptInfoRequest) (*scripttypes.QueryScriptInfoResponse, error) {
	// Validate that an address was provided
	if req.Address == "" {
		return nil, status.Error(codes.InvalidArgument, "empty script address")
	}

	// Resolve the address parameter using the nameservice keeper
	resolvedAddress, err := k.NameserviceKeeper.ResolveNameOrAddress(ctx, req.Address)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to resolve address or name: %s", req.Address)
	}

	script, err := k.ScriptMap.Get(ctx, resolvedAddress)
	if err == nil {
		return &scripttypes.QueryScriptInfoResponse{
			Script: &scripttypes.Script{
				Address:      script.Address,
				Version:      script.Version,
				Code:         script.Code,
				UpdateHeight: script.UpdateHeight,
			},
		}, nil
	}
	if cosmossdkerrors.IsOf(err, collections.ErrNotFound) {
		return nil, status.Errorf(codes.NotFound, "script with address %s doesn't exist", resolvedAddress)
	}
	return nil, status.Error(codes.Internal, err.Error())
}

// Web queries the WSGI web application function of a script. This is used in the REST API and
// is not likely needed to use directly.
//
// Semantics:
//   - Delegates to RunWeb which handles script resolution and execution.
//   - Executes script's WSGI application in read-only mode.
//   - Returns HTTP response from the script's web application.
//   - No state changes are allowed in web requests.
//
// Validation:
//   - Either script_address or script_name must be provided.
//   - Script must exist and have a valid WSGI application.
//   - HTTP request must be valid.
//
// Returns:
//   - *scripttypes.WebResponse with HTTP response from the script.
//
// Errors are returned on script resolution failures, execution errors, or invalid requests; no panics.
func (k Keeper) Web(ctx context.Context, req *scripttypes.WebRequest) (*scripttypes.WebResponse, error) {
	// Calls RunWeb which handles name resolution via nameservice keeper
	out, err := k.RunWeb(ctx, req.ScriptAddress, req.ScriptName, req.Httprequest)
	if err != nil {
		return nil, err
	}

	return &scripttypes.WebResponse{
		Httpresponse: out,
	}, nil
}

// EncodeJson encodes a JSON string to protobuf bytes for message construction.
//
// Semantics:
//   - Parses the provided JSON string into a Cosmos SDK message.
//   - Marshals the parsed message to protobuf bytes.
//   - Enforces size limits to prevent abuse.
//
// Validation:
//   - JSON string must be valid and parseable into a known message type.
//   - JSON length must not exceed 10,000 characters.
//
// Returns:
//   - *scripttypes.QueryEncodeJsonResponse with the protobuf-encoded bytes.
//
// Errors are returned on invalid JSON, unknown message types, or size limit violations; no panics.
func (k Keeper) EncodeJson(ctx context.Context, req *scripttypes.QueryEncodeJsonRequest) (*scripttypes.QueryEncodeJsonResponse, error) {

	// too long return err
	if len(req.Json) > 10_000 {
		return nil, fmt.Errorf("json too long")
	}

	var msg sdk.Msg

	err := k.cdc.UnmarshalInterfaceJSON([]byte(req.Json), &msg)
	if err != nil {
		return nil, err
	}

	bz, err := k.cdc.Marshal(msg)
	if err != nil {
		return nil, err
	}

	return &scripttypes.QueryEncodeJsonResponse{
		Bytes: bz,
	}, nil
}

// DecodeBytes decodes protobuf bytes to JSON string for message inspection.
//
// Semantics:
//   - Creates a message instance from the provided type URL.
//   - Unmarshals the protobuf bytes into the message.
//   - Marshals the message back to JSON for human-readable inspection.
//   - Enforces size limits to prevent abuse.
//
// Validation:
//   - Type URL must be a known message type.
//   - Bytes must be valid protobuf encoding for the specified type.
//   - Bytes length must not exceed 10,000 bytes.
//
// Returns:
//   - *scripttypes.QueryDecodeBytesResponse with the JSON representation.
//
// Errors are returned on unknown types, invalid protobuf, or size limit violations; no panics.
func (k Keeper) DecodeBytes(ctx context.Context, req *scripttypes.QueryDecodeBytesRequest) (*scripttypes.QueryDecodeBytesResponse, error) {

	if len(req.Bytes) > 10_000 {
		return nil, fmt.Errorf("bytes too long")
	}

	msg, err := sdk.GetMsgFromTypeURL(k.cdc, req.TypeUrl)
	if err != nil {
		return nil, fmt.Errorf("failed to get message from type url: %s", req.TypeUrl)
	}

	err = k.cdc.Unmarshal(req.Bytes, msg)
	if err != nil {
		return nil, err
	}

	json, err := k.cdc.MarshalInterfaceJSON(msg)
	if err != nil {
		return nil, err
	}

	return &scripttypes.QueryDecodeBytesResponse{
		Json: string(json),
	}, nil
}

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
//	        "app_domain": "my_app/v1.0"
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

// Run executes a script function in read-only mode without modifying state.
//
// Semantics:
//   - Creates a cached context to prevent any state modifications.
//   - Converts RunScript request to MsgExec and delegates execution.
//   - Executes script with provided arguments in isolated context.
//   - Automatically discards all state changes after execution.
//   - Useful for testing, simulation, and read-only operations.
//
// Validation:
//   - Executor address must be provided and valid.
//   - Either script_address or script_name must be provided.
//   - Function name, args, kwargs must be valid JSON strings.
//
// Returns:
//   - *scripttypes.ResponseRunScript with execution result and attached message results.
//   - All state changes are discarded - execution has no persistent effects.
//
// Errors are returned on invalid parameters, script resolution failures, or execution errors; no panics.
func (k Keeper) Run(ctx context.Context, req *scripttypes.RunScript) (*scripttypes.ResponseRunScript, error) {
	// Validate request
	if req.ExecutorAddress == "" {
		return nil, status.Error(codes.InvalidArgument, "executor address is required")
	}
	if req.ScriptAddress == "" && req.ScriptName == "" {
		return nil, status.Error(codes.InvalidArgument, "either script_address or script_name is required")
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Create a cache context to ensure no state mutations
	cacheCtx, _ := sdkCtx.CacheContext()

	// Convert RunScript to MsgExec
	msgExec := &scripttypes.MsgExec{
		ExecutorAddress:  req.ExecutorAddress,
		ScriptAddress:    req.ScriptAddress,
		ScriptName:       req.ScriptName,
		ExtraCode:        req.ExtraCode,
		FunctionName:     req.FunctionName,
		Args:             req.Args,
		Kwargs:           req.Kwargs,
		AttachedMessages: req.AttachedMessages,
	}

	// Call ExecScript in the cache context
	resp, err := k.ExecScript(cacheCtx, msgExec)
	if err != nil {
		return nil, err
	}

	// The cached context is automatically discarded as we don't call write()
	return &scripttypes.ResponseRunScript{
		Result:                 resp.Result,
		AttachedMessageResults: resp.AttachedMessageResults,
	}, nil
}

// GetBlock returns the current block information.
//
// Semantics:
//   - Extracts block metadata from the current SDK context.
//   - Returns block height, time, chain ID, hashes, and proposer.
//   - Provides essential blockchain state information for scripts.
//   - Useful for time-sensitive operations and block-aware logic.
//
// Validation:
//   - No validation required - reads from current context.
//
// Returns:
//   - *scripttypes.QueryGetBlockResponse with complete block information.
//
// Errors are returned on context extraction failures; no panics.
func (k Keeper) GetBlock(ctx context.Context, req *scripttypes.QueryGetBlockRequest) (*scripttypes.QueryGetBlockResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Get block header from context
	header := sdkCtx.BlockHeader()

	// Extract the block hash from the current block's context
	// Note: We don't have access to the current block's hash from the context,
	// only the previous block's hash
	blockHash := header.AppHash

	return &scripttypes.QueryGetBlockResponse{
		BlockHeight:     header.Height,
		BlockTime:       header.Time,
		ChainId:         header.ChainID,
		BlockHash:       blockHash,
		AppHash:         header.AppHash,
		ProposerAddress: sdk.ConsAddress(header.ProposerAddress).String(),
	}, nil
}

// FunctionSchema returns JSON schemas for all public functions in a script.
//
// Semantics:
//   - Resolves script address via direct address or nameservice name.
//   - Loads script code (or empty script if not found).
//   - Starts ephemeral RPC server for script execution environment.
//   - Extracts function schemas by introspecting script with DysVM.
//   - Returns JSON object mapping function names to their schemas.
//   - Useful for tooling, documentation, and client integration.
//
// Validation:
//   - Executor address must be provided and valid.
//   - Either script_address or script_name must be provided.
//   - If both are provided, they must resolve to the same address.
//
// Returns:
//   - *scripttypes.QueryFunctionSchemaResponse with JSON schema object.
//   - Schema includes function signatures, parameter types, and return types.
//
// Errors are returned on invalid parameters, script resolution failures, or schema extraction errors; no panics.
func (k Keeper) FunctionSchema(ctx context.Context, req *scripttypes.QueryFunctionSchemaRequest) (*scripttypes.QueryFunctionSchemaResponse, error) {
	if req.ExecutorAddress == "" {
		return nil, status.Error(codes.InvalidArgument, "executor address is required")
	}
	if req.ScriptAddress == "" && req.ScriptName == "" {
		return nil, status.Error(codes.InvalidArgument, "either script_address or script_name is required")
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Resolve script address optionally via nameservice
	var resolvedAddress string
	var err error
	if req.ScriptAddress != "" && req.ScriptName != "" {
		nameAddr, nameErr := k.NameserviceKeeper.ResolveNameOrAddress(ctx, req.ScriptName)
		if nameErr != nil {
			return nil, cosmossdkerrors.Wrap(nameErr, "failed to resolve script_name")
		}
		if nameAddr != req.ScriptAddress {
			return nil, status.Error(codes.InvalidArgument, "script_address does not match resolved script_name")
		}
		resolvedAddress = req.ScriptAddress
	} else if req.ScriptName != "" {
		resolvedAddress, err = k.NameserviceKeeper.ResolveNameOrAddress(ctx, req.ScriptName)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to resolve script_name")
		}
	} else {
		resolvedAddress = req.ScriptAddress
	}

	// Load script (or empty)
	var script scripttypes.Script
	exists, err := k.ScriptMap.Has(ctx, resolvedAddress)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to check script existence")
	}
	if !exists {
		script = scripttypes.Script{Address: resolvedAddress, Version: 0, Code: ""}
	} else {
		script, err = k.ScriptMap.Get(ctx, resolvedAddress)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to get script")
		}
	}

	// Start ephemeral RPC server
	port, srv, err := k.NewRPCServer(sdkCtx, resolvedAddress, k.App)
	if err != nil {
		return nil, err
	}
	defer func() {
		if derr := srv.Shutdown(context.Background()); derr != nil {
			k.Logger(sdkCtx).Error("shutdown error", "error", derr)
		}
	}()

	// Marshal script and header info
	scriptJSON, err := k.cdc.MarshalInterfaceJSON(&script)
	if err != nil {
		return nil, err
	}

	bh := sdkCtx.BlockHeader()
	headerInfo := header.Info{
		Height:  bh.Height,
		Time:    bh.Time,
		ChainID: bh.ChainID,
		AppHash: bh.AppHash,
		Hash:    bh.LastBlockId.Hash,
	}
	headerJSON, err := json.Marshal(headerInfo)
	if err != nil {
		return nil, err
	}

	// Call VM to extract schema
	schemaJSON, runErr := dysvm.ExtractFunctionSchema(ctx, string(scriptJSON), string(headerJSON), port, req.ExecutorAddress, req.ScriptName)
	if runErr != nil {
		return nil, cosmossdkerrors.Wrapf(runErr, "failed to extract function schema: %s, %s", runErr.Error(), schemaJSON)
	}

	return &scripttypes.QueryFunctionSchemaResponse{SchemaJson: schemaJSON}, nil
}
