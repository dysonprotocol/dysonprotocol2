package keeper

import (
	"context"

	sdk "github.com/cosmos/cosmos-sdk/types"
)

// BeginBlocker enforces nodes to keep the required historical blocks
// It queries the module parameters to determine the maximum historical blocks
// that should be available and panics if the required blocks are not accessible
func (k Keeper) BeginBlocker(ctx context.Context) error {
	// Historical retention validation removed; nothing to do per block
	_ = sdk.UnwrapSDKContext(ctx)
	return nil
}

// validateHistoricalBlocks checks if the required historical blocks are accessible
// validateHistoricalBlocks removed with historical query support

func (k Keeper) EndBlocker(ctx context.Context) error {
	return nil
}
