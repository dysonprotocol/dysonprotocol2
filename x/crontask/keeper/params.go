package keeper

import (
	"context"
	"errors"
	"fmt"

	"cosmossdk.io/collections"
	crontasktypes "dysonprotocol.com/x/crontask/types"
)

// SetParams sets the crontask module parameters
func (k Keeper) SetParams(ctx context.Context, params crontasktypes.Params) error {

	// Validate parameters before attempting to set them
	if err := params.Validate(); err != nil {
		k.Logger.Error("SetParams validation error", "error", err)
		return fmt.Errorf("invalid parameters: %w", err)
	}

	err := k.Params.Set(ctx, params)
	if err != nil {
		k.Logger.Error("SetParams error when setting params", "error", err)
		return err
	}

	return nil
}

// GetParams gets the crontask module parameters
func (k Keeper) GetParams(ctx context.Context) crontasktypes.Params {
	params, err := k.Params.Get(ctx)
	if err == nil {
		return params
	}
	if errors.Is(err, collections.ErrNotFound) {
		k.Logger.Error("GetParams: params not found; returning defaults")
		return crontasktypes.DefaultParams()
	}
	// Surface unexpected errors loudly; do not mask corruption
	panic(err)
}

// GetModuleParams returns the current module parameters
func (k Keeper) GetModuleParams(ctx context.Context) crontasktypes.Params {
	return crontasktypes.Params{
		BlockGasLimit:    k.config.BlockGasLimit,
		ExpiryLimit:      k.config.ExpiryLimit,
		MaxScheduledTime: k.config.MaxScheduledTime,
	}
}

// GetAuthority returns the module's authority
func (k Keeper) GetAuthority() string {
	return k.authority
}
