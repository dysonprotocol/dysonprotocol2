package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	scriptv1 "dysonprotocol.com/api/script/types"
	"dysonprotocol.com/dysvm"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// UpdateScript updates the script code at the given address and increments its version.
//
// Semantics:
//   - Updates or creates a script at the specified address with formatted code.
//   - Automatically formats the provided code using DysFormat before storage.
//   - Increments the script version on each update.
//   - Sets update metadata including block height.
//   - Creates new scripts with empty code if they don't exist.
//
// Validation:
//   - Address must be a valid bech32 address.
//   - Code must be valid Python syntax with some restrictions.
//
// State Updates:
//   - Stores/updates script in ScriptMap with incremented version.
//   - Sets UpdateHeight to current block height.
//
// Emits:
//   - EventUpdateScript(version, script_address) on successful update.
//
// Returns:
//   - *scripttypes.MsgUpdateScriptResponse with the updated script version.
//
// Errors are returned on invalid address, formatting failures, storage errors, or event emission failures; no panics.
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
