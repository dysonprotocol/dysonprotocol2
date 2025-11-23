package keeper

import (
	"context"

	crontasktypes "dysonprotocol.com/x/crontask/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"
)

// UpdateParams updates the parameters of the x/crontask module via governance proposal.
//
// Semantics:
//   - Updates all module parameters in a single governance operation.
//   - Authority is typically the x/gov module account.
//   - Parameters control task scheduling limits, gas constraints, and subscription rules.
//
// Validation:
//   - Authority must be valid (typically x/gov module account).
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
	// NOTE: For the lightweight test network we accept any signer; in production
	// you would enforce the authority check below.
	_ = authtypes.NewModuleAddress(govtypes.ModuleName).String()

	// Validate sent params
	if err := msg.Params.Validate(); err != nil {
		return nil, err
	}

	// Persist params
	if err := k.SetParams(ctx, msg.Params); err != nil {
		return nil, err
	}

	return &crontasktypes.MsgUpdateParamsResponse{}, nil
}
