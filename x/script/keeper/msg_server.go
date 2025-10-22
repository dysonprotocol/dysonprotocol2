package keeper

import (
	"context"
	"crypto/sha256"
	"fmt"

	cosmossdkerrors "cosmossdk.io/errors"
	storetypes "cosmossdk.io/store/types"
	scriptv1 "dysonprotocol.com/api/script/types"
	"dysonprotocol.com/dysvm"
	"dysonprotocol.com/x/script"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/x/authz"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"
)

var _ scripttypes.MsgServer = Keeper{}

func (k Keeper) UpdateScript(ctx context.Context, msg *scripttypes.MsgUpdateScript) (*scripttypes.MsgUpdateScriptResponse, error) {

	var script scripttypes.Script
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	sdkCtx.GasMeter().ConsumeGas(1_000_000, "script update script base cost")

	exists, err := k.ScriptMap.Has(ctx, msg.Address)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to check if script exists")
	}

	if !exists {
		script = scripttypes.Script{
			Address:      msg.Address,
			Version:      0,
			Code:         msg.Code,
			UpdateHeight: uint64(sdkCtx.BlockHeight()),
		}
	} else {
		script, err = k.ScriptMap.Get(ctx, msg.Address)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to get existing script")
		}
	}

	// Format the code with black before setting it
	formattedCode, err := dysvm.DysFormat(ctx, msg.Code)
	if err != nil {
		k.Logger(sdkCtx).Error("failed to format code with dys_format", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to format code")
	}

	script.Code = formattedCode
	script.Version = script.Version + 1
	// Set update metadata
	script.UpdateHeight = uint64(sdkCtx.BlockHeight())
	k.Logger(sdkCtx).Info("updating script", "script", script.Address, "version", script.Version)
	err = k.ScriptMap.Set(ctx, msg.Address, script)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to set script")
	}

	// Get event manager from context
	err = sdkCtx.EventManager().EmitTypedEvent(
		&scriptv1.EventUpdateScript{
			Version:       script.Version,
			ScriptAddress: msg.Address,
		})

	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit update script event")
	}

	resp := scripttypes.MsgUpdateScriptResponse{
		Version: script.Version,
	}

	return &resp, nil
}

func (k Keeper) ExecScript(ctx context.Context, msg *scripttypes.MsgExec) (*scripttypes.MsgExecResponse, error) {
	resp := &scripttypes.MsgExecResponse{}
	var scriptObj scripttypes.Script

	// Handle script address and name resolution
	var addr string
	var err error

	// Validate that at least one of script_address or script_name is provided
	if msg.ScriptAddress == "" && msg.ScriptName == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "either script_address or script_name must be provided")
	}

	// Case 1: Both address and name provided - validate they resolve to the same address
	if msg.ScriptAddress != "" && msg.ScriptName != "" {
		// script_address should be a bech32 address (no resolution needed)
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
		// Case 3: Only address provided - use as bech32 address directly (no resolution)
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
	execErr := func() error {
		// Add panic recovery
		defer func() {
			if r := recover(); r != nil {
				err = fmt.Errorf("panic during script execution: %v", r)
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

func (k Keeper) CreateNewScript(ctx context.Context, msg *scripttypes.MsgCreateNewScript) (*scripttypes.MsgCreateNewScriptResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	sdkCtx.GasMeter().ConsumeGas(1_000_000, "script create new script base cost")

	// Create a deterministic address from the creator's address and the script content
	creatorBytes, err := k.addressCodec.StringToBytes(msg.CreatorAddress)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid creator address: %s", msg.CreatorAddress)
	}

	// Format the code with black before setting it and deriving address
	formattedCode, err := dysvm.DysFormat(ctx, msg.Code)
	if err != nil {
		k.Logger(sdkCtx).Error("failed to format code with dys_format", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to format code")
	}

	// Create a hash of the creator + code to generate a deterministic script address
	contentToHash := append(creatorBytes, []byte(formattedCode)...)
	hasher := sha256.New()
	hasher.Write(contentToHash)
	scriptAddrBytes := hasher.Sum(nil)

	// Create bech32 address from the hash
	scriptAddr, err := sdk.Bech32ifyAddressBytes(sdk.GetConfig().GetBech32AccountAddrPrefix(), scriptAddrBytes[:20])
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to create script address")
	}

	// Check if script with this address already exists
	exists, err := k.ScriptMap.Has(ctx, scriptAddr)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to check if script exists")
	}

	if exists {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "cannot create new script: a script with address %s already exists. Each script has a unique address derived from its creator and content", scriptAddr)
	}

	// Create a new script
	script := scripttypes.Script{
		Address: scriptAddr,
		Version: 1, // Start at version 1
		Code:    formattedCode,
	}

	// Save the script
	err = k.ScriptMap.Set(ctx, scriptAddr, script)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to set script")
	}

	// Create a generic authorization for MsgUpdateScript
	// This allows the creator to update the script in the future
	msgTypeURL := sdk.MsgTypeURL(&scripttypes.MsgUpdateScript{})
	authorization := authz.NewGenericAuthorization(msgTypeURL)

	// Convert the addresses to the correct format
	creatorAddress := sdk.AccAddress(creatorBytes)
	scriptAddress, err := k.addressCodec.StringToBytes(scriptAddr)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to convert script address to bytes: %s", scriptAddr)
	}

	// In authz, the script (scriptAddress) is the GRANTER and the creator (creatorAddress) is the GRANTEE
	// This allows the creator to act on behalf of the script
	err = k.AuthzKeeper.SaveGrant(ctx, creatorAddress, sdk.AccAddress(scriptAddress), authorization, nil)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to save authz grant")
	}

	// Emit event
	err = sdkCtx.EventManager().EmitTypedEvent(
		&scriptv1.EventCreateNewScript{
			ScriptAddress:  scriptAddr,
			CreatorAddress: msg.CreatorAddress,
			Version:        script.Version,
		})
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit create new script event")
	}

	return &scripttypes.MsgCreateNewScriptResponse{
		ScriptAddress: scriptAddr,
		Version:       script.Version,
	}, nil
}

// UpdateParams updates the module parameters
func (k Keeper) UpdateParams(ctx context.Context, msg *scripttypes.MsgUpdateParams) (*scripttypes.MsgUpdateParamsResponse, error) {
	// Validate authority
	if k.authority != msg.Authority {
		return nil, cosmossdkerrors.Wrapf(govtypes.ErrInvalidSigner, "invalid authority; expected %s, got %s", k.authority, msg.Authority)
	}

	// Validate the parameters
	if err := msg.Params.Validate(); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invalid parameters")
	}

	// Set the parameters
	if err := k.SetParams(ctx, msg.Params); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to set parameters")
	}

	return &scripttypes.MsgUpdateParamsResponse{}, nil
}

// Sudo executes arbitrary messages with authority override (no signer validation)
func (k Keeper) Sudo(ctx context.Context, msg *scripttypes.MsgSudo) (*scripttypes.MsgSudoResponse, error) {
	// Validate authority
	if k.authority != msg.Authority {
		return nil, cosmossdkerrors.Wrapf(govtypes.ErrInvalidSigner, "invalid authority; expected %s, got %s", k.authority, msg.Authority)
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Unpack messages
	msgs, err := script.GetMsgExecMessages(&scripttypes.MsgExec{AttachedMessages: msg.Messages})
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to unpack sudo messages")
	}

	// Execute each message without signer validation
	results := make([]sdk.Msg, len(msgs))
	for i, execMsg := range msgs {
		result, err := k.DispatchSudoMessage(sdkCtx, execMsg)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to execute sudo message at index %d", i)
		}
		results[i] = result
	}

	// Pack results
	resp := &scripttypes.MsgSudoResponse{}
	err = script.SetMsgExecResult(&scripttypes.MsgExecResponse{}, results)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to pack sudo results")
	}

	// Convert to response format
	anyResults, err := script.GetAnyMessages(results)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to convert results to Any")
	}
	resp.Results = anyResults

	return resp, nil
}

// HandleRunRecovery is an exported version of handleRunRecovery for testing
func HandleRunRecovery(r interface{}) error {
	return handleRunRecovery(r)
}

func handleRunRecovery(r interface{}) error {
	fmt.Printf("Handle recovery: %v\n", r)
	switch rec := r.(type) {
	case nil:
		// No panic, just return nil or handle gracefully
		return nil
	case storetypes.ErrorOutOfGas:
		return cosmossdkerrors.Wrapf(sdkerrors.ErrOutOfGas,
			"script ran out of gas (descriptor: %s)", rec.Descriptor,
		)
	case error:
		// Additional checks for other error types
		// if cosmossdkerrors.Is(rec, sdkerrors.ErrXYZ) { ... }
		return sdkerrors.ErrPanic.Wrapf("script panic (error type): %v", rec.Error())
	default:
		// Panic with something that wasn't an error
		return sdkerrors.ErrPanic.Wrapf("script panic (non-error type): %v", rec)
	}
}
