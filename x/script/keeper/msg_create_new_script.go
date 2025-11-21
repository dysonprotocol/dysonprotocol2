package keeper

import (
	"context"
	"crypto/sha256"

	cosmossdkerrors "cosmossdk.io/errors"
	scriptv1 "dysonprotocol.com/api/script/types"
	"dysonprotocol.com/dysvm"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/x/authz"
)

// CreateNewScript creates a new script with a deterministic address and grants update permissions.
//
// Semantics:
//   - Generates deterministic script address using SHA256 hash of creator + formatted code.
//   - Creates bech32 address from first 20 bytes of hash.
//   - Formats code using DysFormat before address generation and storage.
//   - Grants generic authorization for MsgUpdateScript to creator via authz.
//   - Initializes script with version 1 and formatted code.
//
// Validation:
//   - Creator address must be valid.
//   - Code must be valid Python syntax that can be formatted by DysFormat.
//   - Generated address must not already exist. Essentially this means that each script must be unique for each creator.
//
// State Updates:
//   - Stores new script in ScriptMap with version 1.
//   - Creates authz grant allowing creator to update the script. To be fully autonomus the script can revoke the grant.
//
// Emits:
//   - EventCreateNewScript(script_address, creator_address, version) on success.
//
// Returns:
//   - *scripttypes.MsgCreateNewScriptResponse with generated script address and version.
//
// Errors are returned on invalid creator address, formatting failures, address conflicts, or grant creation failures; no panics.
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
