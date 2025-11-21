package keeper

import (
	"context"

	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

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
