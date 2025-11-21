package keeper

import (
	"context"
	"fmt"

	cosmossdkerrors "cosmossdk.io/errors"
	"dysonprotocol.com/x/script"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// ExecScript executes a script function with arguments and handles attached messages.
//
// Semantics:
//   - Resolves script address via direct address or nameservice name resolution.
//   - Validates that script exists or creates empty script if not found.
//   - Executes attached messages first, collecting their results.
//   - Runs the specified function with provided args/kwargs in isolated context.
//   - Commits state changes only if execution succeeds.
//   - Emits execution event with full context for monitoring.
//
// Validation:
//   - Either script_address or script_name must be provided.
//   - If both are provided, they must resolve to the same address.
//   - Executor address must be valid.
//   - Function name, args, kwargs must be valid JSON strings.
//   - Attached messages must be valid and executable.
//
// State Updates:
//   - Executes attached messages and collects their results.
//   - Commits script execution results if successful.
//   - Creates empty script if address doesn't exist.
//
// Emits:
//   - EventExecScript with execution details (executor, script, function, result).
//
// Returns:
//   - *scripttypes.MsgExecResponse with function result and attached message results.
//
// Errors are returned on invalid parameters, resolution failures, execution errors, or message failures; no panics.
func (k Keeper) ExecScript(ctx context.Context, msg *scripttypes.MsgExec) (*scripttypes.MsgExecResponse, error) {
	if msg == nil {
		return nil, status.Error(codes.InvalidArgument, "message cannot be nil")
	}

	// Validate executor address is a valid bech32 address
	_, err := k.addressCodec.StringToBytes(msg.ExecutorAddress)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid executor address: %s", msg.ExecutorAddress)
	}

	resp := &scripttypes.MsgExecResponse{}
	var scriptObj scripttypes.Script

	// Handle script address and name resolution
	var addr string

	// Validate that at least one of script_address or script_name is provided
	if msg.ScriptAddress == "" && msg.ScriptName == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "either script_address or script_name must be provided")
	}

	// Case 1: Both address and name provided - validate they resolve to the same address
	if msg.ScriptAddress != "" && msg.ScriptName != "" {
		// Validate script_address is a valid bech32 address
		_, err = k.addressCodec.StringToBytes(msg.ScriptAddress)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "invalid script address: %s", msg.ScriptAddress)
		}
		scriptAddr := msg.ScriptAddress

		// Resolve the name to an address
		nameAddr, nameErr := k.NameserviceKeeper.ResolveNameOrAddress(ctx, msg.ScriptName)
		if nameErr != nil {
			return nil, cosmossdkerrors.Wrap(nameErr, fmt.Sprintf("failed to resolve script_name: '%s'", msg.ScriptName))
		}

		// Validate they match
		if scriptAddr != nameAddr {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest,
				fmt.Sprintf("script_address '%s' does not match resolved script_name '%s' (resolves to '%s') - they must be the same address",
					scriptAddr, msg.ScriptName, nameAddr))
		}

		addr = scriptAddr
	} else if msg.ScriptName != "" {
		// Case 2: Only name provided - resolve to address
		addr, err = k.NameserviceKeeper.ResolveNameOrAddress(ctx, msg.ScriptName)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, fmt.Sprintf("failed to resolve script_name: '%s'", msg.ScriptName))
		}
	} else {
		// Case 3: Only address provided - validate bech32 format
		_, err = k.addressCodec.StringToBytes(msg.ScriptAddress)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "invalid script address: %s", msg.ScriptAddress)
		}
		addr = msg.ScriptAddress
	}

	exists, err := k.ScriptMap.Has(ctx, addr)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to check if script exists")
	}

	if !exists {
		// create a new script
		scriptObj = scripttypes.Script{
			Address: addr,
			Version: 0,
			Code:    "",
		}
		err = k.ScriptMap.Set(ctx, addr, scriptObj)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to set script")
		}
	} else {
		scriptObj, err = k.ScriptMap.Get(ctx, addr)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to get script")
		}
	}

	scriptContext := ExecScriptContext{msg, &scriptObj, nil}

	// Replace BranchService with direct CacheContext usage
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Base gas cost for script execution
	sdkCtx.GasMeter().ConsumeGas(1_000_000, "script exec base cost")

	// Create a cached context that creates an isolated context for the execution
	cacheCtx, write := sdkCtx.CacheContext()

	// Execute the function
	execErr := func() (err error) {
		// Add panic recovery
		defer func() {
			if r := recover(); r != nil {
				// Log the panic
				k.Logger(sdkCtx).Error("panic during script execution", "panic", r)
				err = fmt.Errorf("panic during ExecScript")
			}
		}()

		execResp, err := k.execScript(cacheCtx, &scriptContext)
		if err != nil {
			k.Logger(sdkCtx).Error("failed to execute script", "error", err, "execResp", execResp)
			return err
		}

		resp.Result = execResp.Result
		err = script.SetMsgExecResult(resp, scriptContext.AttachedMessageResults)
		if err != nil {
			k.Logger(sdkCtx).Error("failed to set msg exec result", "error", err)
			return err
		}

		// Get event manager from context
		evtCtx := sdk.UnwrapSDKContext(cacheCtx)
		evterr := evtCtx.EventManager().EmitTypedEvent(
			&scripttypes.EventExecScript{
				Request:         msg,
				Response:        resp,
				ExecutorAddress: msg.ExecutorAddress,
				ScriptAddress:   addr,
				ScriptName:      msg.ScriptName,
				FunctionName:    msg.FunctionName,
			})
		if evterr != nil {
			k.Logger(sdkCtx).Error("failed to emit event", "error", evterr)
			return evterr
		}

		return nil
	}()

	// If execution was successful, write state changes back to the parent context
	if execErr == nil {
		write()
	}

	return resp, execErr
}
