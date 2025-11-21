package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	storagetypes "dysonprotocol.com/x/storage/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// UpdateParams updates the x/storage module parameters via governance proposal.
//
// Semantics:
//   - Validates that the signer has authority to update module parameters (typically governance module).
//   - Validates that all provided parameters are valid according to parameter constraints.
//   - Updates the module's parameter state with the new values.
//
// Validation:
//   - Authority must match the module's configured authority address.
//   - All parameter values must pass individual validation (MaxStorageSize, StorageStakeMultiple).
//
// State Updates:
//   - Updates the module's Params in state with the new parameter values.
//
// Emits:
//   - No events emitted for parameter updates.
//
// Returns:
//   - *storagetypes.MsgUpdateParamsResponse with empty body on success.
//
// Errors are returned on invalid authority, parameter validation failures, or state update failures; no panics.
func (k Keeper) UpdateParams(ctx context.Context, msg *storagetypes.MsgUpdateParams) (*storagetypes.MsgUpdateParamsResponse, error) {
	// Check authority - this should be the governance module account or a dedicated module admin
	if msg.Authority != k.GetAuthority() {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"invalid authority; expected %s, got %s",
			k.GetAuthority(),
			msg.Authority,
		)
	}

	// Validate the parameters
	if err := msg.Params.Validate(); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invalid parameters")
	}

	// Set the parameters
	if err := k.SetParams(ctx, msg.Params); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update parameters")
	}

	return &storagetypes.MsgUpdateParamsResponse{}, nil
}

