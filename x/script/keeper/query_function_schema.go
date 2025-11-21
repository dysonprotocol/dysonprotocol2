package keeper

import (
	"context"
	"encoding/json"

	"dysonprotocol.com/dysvm"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"cosmossdk.io/core/header"
	cosmossdkerrors "cosmossdk.io/errors"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

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
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "request cannot be nil")
	}
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
		return nil, cosmossdkerrors.Wrap(err, "failed to start RPC server")
	}
	defer func() {
		if derr := srv.Shutdown(context.Background()); derr != nil {
			k.Logger(sdkCtx).Error("shutdown error", "error", derr)
		}
	}()

	// Marshal script and header info
	scriptJSON, err := k.cdc.MarshalInterfaceJSON(&script)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to marshal script to JSON")
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
		return nil, cosmossdkerrors.Wrap(err, "failed to marshal header info to JSON")
	}

	// Call VM to extract schema
	schemaJSON, runErr := dysvm.ExtractFunctionSchema(ctx, string(scriptJSON), string(headerJSON), port, req.ExecutorAddress, req.ScriptName)
	if runErr != nil {
		return nil, cosmossdkerrors.Wrapf(runErr, "failed to extract function schema: %s", schemaJSON)
	}

	return &scripttypes.QueryFunctionSchemaResponse{SchemaJson: schemaJSON}, nil
}
