package keeper

import (
	v2 "dysonprotocol.com/x/whaleswap/migrations/v2"

	sdk "github.com/cosmos/cosmos-sdk/types"
)

// Migrator is a struct for handling in-place store migrations.
type Migrator struct {
	keeper Keeper
}

// NewMigrator returns a new Migrator.
func NewMigrator(keeper Keeper) Migrator {
	return Migrator{keeper: keeper}
}

// Migrate1to2 migrates the whaleswap module from consensus version 1 to 2.
// This migration adds the ArbitrageMode parameter with a default value of AUTO.
func (m Migrator) Migrate1to2(ctx sdk.Context) error {
	// Wrap sdk.Context keeper methods for v2.MigrateStore
	return v2.MigrateStore(ctx, m.keeper.GetParams, m.keeper.SetParams)
}
