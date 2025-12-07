package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// UpdateParams updates the module parameters.
//
// Semantics:
//   - Updates module parameters via governance proposal.
//   - If reserved_names field is blank in the message, the existing value is preserved.
//   - All other parameters must be provided and will be updated.
//
// Validation:
//   - Authority must match the module's configured authority address.
//   - All parameter values must pass individual validation.
//
// State Updates:
//   - Updates module parameters in state.
//
// Emits:
//   - EventParamsUpdated event with the updated parameters.
//
// Returns:
//   - *nameservicev1.MsgUpdateParamsResponse (empty response on success).
//
// Errors are returned on invalid authority, parameter validation failures, or storage errors; no panics.
func (k Keeper) UpdateParams(ctx context.Context, msg *nameservicev1.MsgUpdateParams) (*nameservicev1.MsgUpdateParamsResponse, error) {
	// Check authority - this should be the governance module account or a dedicated module admin
	if msg.Authority != k.GetAuthority() {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"invalid authority; expected %s, got %s",
			k.GetAuthority(),
			msg.Authority,
		)
	}

	// If reserved_names is blank, preserve the existing value
	if msg.Params.ReservedNames == "" {
		currentParams := k.GetParams(ctx)
		msg.Params.ReservedNames = currentParams.ReservedNames
	}

	// Validate the parameters
	if err := msg.Params.Validate(); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invalid parameters")
	}

	// Set the parameters
	if err := k.SetParams(ctx, msg.Params); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update parameters")
	}

	// Emit event
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	err := sdkCtx.EventManager().EmitTypedEvent(&nameservicev1.EventParamsUpdated{
		Params: msg.Params,
	})
	if err != nil {
		k.Logger.Error("failed to emit event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return &nameservicev1.MsgUpdateParamsResponse{}, nil
}
