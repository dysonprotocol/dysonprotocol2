package keeper

import (
	"context"
	"errors"

	"cosmossdk.io/collections"
	scripttypes "dysonprotocol.com/x/script/types"
)

// GetParams returns the current module parameters
func (k Keeper) GetParams(ctx context.Context) (params scripttypes.Params) {
	params, err := k.params.Get(ctx)
	if err == nil {
		return params
	}
	if errors.Is(err, collections.ErrNotFound) {
		return scripttypes.DefaultParams()
	}
	panic(err)
}

// SetParams sets the module parameters
func (k Keeper) SetParams(ctx context.Context, params scripttypes.Params) error {
	if err := params.Validate(); err != nil {
		return err
	}
	return k.params.Set(ctx, params)
}
