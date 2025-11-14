package keeper

import (
	"context"

	sdk "github.com/cosmos/cosmos-sdk/types"
)

// MigrateWhaleswapLeverageInterest is a placeholder for the upcoming leverage
// interest/accounting migration. The detailed transformation will be added once
// the new schema (initial principal, interest settlement tracking, etc.) is
// introduced.
func (k Keeper) MigrateWhaleswapLeverageInterest(ctx context.Context) error {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	k.Logger(sdkCtx).Info("Whaleswap leverage-interest migration: no-op placeholder")
	return nil
}
