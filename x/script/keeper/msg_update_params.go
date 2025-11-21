package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	scripttypes "dysonprotocol.com/x/script/types"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"
)

// UpdateParams updates the module parameters via governance proposal.
//
// Semantics:
//   - Validates that the signer has authority to update parameters (gov module).
//   - Validates that all provided parameters are valid.
//   - Updates all module parameters atomically.
//
// Validation:
//   - Authority must match the configured authority (gov module account).
//   - All parameters in the params message must pass individual validation.
//
// State Updates:
//   - Updates all script module parameters in the parameter store.
//
// Returns:
//   - *scripttypes.MsgUpdateParamsResponse (empty response on success).
//
// Errors are returned on invalid authority, parameter validation failures, or storage errors; no panics.
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
