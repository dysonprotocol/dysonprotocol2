package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// UpdateParams updates the parameters of the x/crontask module via governance proposal.
//
// Semantics:
//   - Updates all module parameters in a single governance operation.
//   - Authority must match the module's configured authority address.
//   - Parameters control task scheduling limits, gas constraints, and subscription rules.
//
// Validation:
//   - Authority must match the module's configured authority address.
//   - All parameter values must pass individual validation (Validate method).
//
// State Updates:
//   - Persists updated parameters to module state.
//
// Emits:
//   - No events are emitted for parameter updates.
//
// Returns:
//   - *crontasktypes.MsgUpdateParamsResponse (empty response).
//
// Errors are returned on invalid authority, parameter validation failures,
// or storage errors; no panics.
func (k Keeper) UpdateParams(ctx context.Context, msg *crontasktypes.MsgUpdateParams) (*crontasktypes.MsgUpdateParamsResponse, error) {
	// Check authority - this should be the governance module account or a dedicated module admin
	expectedAuthority := k.GetAuthority()
	if msg.Authority != expectedAuthority {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"invalid authority; expected %s, got %s",
			expectedAuthority,
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

	return &crontasktypes.MsgUpdateParamsResponse{}, nil
}
