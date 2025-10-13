package keeper

import (
	"context"
	"fmt"

	storagev1 "dysonprotocol.com/x/storage/types"
	"github.com/cosmos/cosmos-sdk/types"
)

// InitGenesis initializes the storage module's state from a genesis state.
func (k Keeper) InitGenesis(ctx context.Context, genState *storagev1.GenesisState) {
	// Set the module parameters
	if err := k.SetParams(ctx, genState.Params); err != nil {
		panic(fmt.Errorf("failed to set params: %w", err))
	}

	// Iterate through all the storage entries in the genesis state and set them
	seen := make(map[string]struct{})
	for _, entry := range genState.Entries {
		// Validate the owner address is properly formatted
		if _, err := types.AccAddressFromBech32(entry.Owner); err != nil {
			panic(fmt.Errorf("invalid owner address %s: %w", entry.Owner, err))
		}
		if entry.Index == "" {
			panic(fmt.Errorf("empty index for owner %s", entry.Owner))
		}

		// Generate the combined key and ensure uniqueness
		combinedKey := entry.Owner + "/" + entry.Index
		if _, dup := seen[combinedKey]; dup {
			panic(fmt.Errorf("duplicate storage entry for %s", combinedKey))
		}
		seen[combinedKey] = struct{}{}

		// Set the storage entry
		if err := k.StorageMap.Set(ctx, combinedKey, storagev1.Storage{
			Owner: entry.Owner,
			Index: entry.Index,
			Data:  entry.Data,
		}); err != nil {
			panic(fmt.Errorf("failed to set storage entry %s: %w", combinedKey, err))
		}
	}

	// Rebuild derived state (metrics) after entries are loaded
	if err := k.RebuildDerivedState(ctx); err != nil {
		panic(fmt.Errorf("failed to rebuild derived state: %w", err))
	}
}

// ExportGenesis exports the storage module's state to a genesis state.
func (k Keeper) ExportGenesis(ctx context.Context) *storagev1.GenesisState {
	// Get current parameters
	params := k.GetParams(ctx)

	// Initialize an empty slice for entries
	entries := []storagev1.Storage{}

	// Iterate through all storage entries and add them to the slice
	entryRange, err := k.StorageMap.Iterate(ctx, nil)
	if err != nil {
		panic(err)
	}
	defer entryRange.Close()

	for ; entryRange.Valid(); entryRange.Next() {
		value, err := entryRange.Value()
		if err != nil {
			panic(fmt.Errorf("failed to read storage value during export: %w", err))
		}
		entries = append(entries, value)
	}

	// Entries are already in a deterministic order; no additional sorting required

	// Create and return a new genesis state with the params and entries
	return &storagev1.GenesisState{
		Params:  params,
		Entries: entries,
	}
}
