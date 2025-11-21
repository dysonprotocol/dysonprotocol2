package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	scriptv1 "dysonprotocol.com/api/script/types"
	"dysonprotocol.com/dysvm"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
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
//   - Message must not be nil.
//   - Address must be a valid bech32 address.
//   - Code must be valid Python syntax with some restrictions.
//   - Context must contain a valid SDK context (UnwrapSDKContext can panic if not).
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
// Errors are returned on nil message, invalid address, formatting failures, storage errors, or event emission failures.
func (k Keeper) UpdateScript(ctx context.Context, msg *scripttypes.MsgUpdateScript) (*scripttypes.MsgUpdateScriptResponse, error) {
	if msg == nil {
		return nil, status.Error(codes.InvalidArgument, "message cannot be nil")
	}

	// Validate address is a valid bech32 address
	_, err := k.addressCodec.StringToBytes(msg.Address)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid script address: %s", msg.Address)
	}

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

	// Check for version overflow
	if script.Version == ^uint64(0) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "script version overflow: cannot increment version beyond maximum")
	}
	script.Version = script.Version + 1

	// Set update metadata
	blockHeight := sdkCtx.BlockHeight()
	if blockHeight < 0 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid block height: %d", blockHeight)
	}
	script.UpdateHeight = uint64(blockHeight)
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
