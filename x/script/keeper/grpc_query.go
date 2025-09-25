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

func (k Keeper) Params(ctx context.Context, req *scripttypes.QueryParamsRequest) (*scripttypes.QueryParamsResponse, error) {
	params := k.GetParams(ctx)
	return &scripttypes.QueryParamsResponse{Params: params}, nil
}

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

// VerifyTx verifies the signatures of a transaction.
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

	for i, sig := range sigs {
		pubKey := sig.PubKey
		if pubKey == nil {
			return nil, status.Error(codes.InvalidArgument, "public key is missing")
		}

		signerAddr := sdk.AccAddress(pubKey.Address())
		if !signerAddr.Equals(sdk.AccAddress(signers[i])) {
			return nil, status.Errorf(codes.InvalidArgument, "signature does not match its respective signer; expected: %s, got: %s", sdk.AccAddress(signers[i]), signerAddr)
		}

		// Get account info from AccountKeeper
		acc := k.AccountKeeper.GetAccount(ctx, signerAddr)
		if acc == nil {
			return nil, status.Errorf(codes.NotFound, "account not found for address %s", signerAddr)
		}

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
		err = authsigning.VerifySignature(ctx, pubKey, signerData, sig.Data, signModeHandler, txData)
		if err != nil {
			return nil, status.Errorf(codes.Unauthenticated, "signature [%d] verification failed (make sure the --chain-id=\"\", --account-number=0, and --sequence=0): %s", i, err.Error())
		}

		signerAddress = signerAddr.String()
	}

	// All signatures have been successfully verified
	return &scripttypes.QueryVerifyTxResponse{
		Signer: signerAddress,
	}, nil
}

// Run executes a script function in read-only mode without modifying state.
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
