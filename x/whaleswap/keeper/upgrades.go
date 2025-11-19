package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// MigrateWhaleswapLeverageInterest migrates existing leverage positions to the new schema:
// 1. Converts interest_rate from repeated DecCoin to single DecCoin (borrowed denom)
// 2. Converts accrued_interest_remainder from string to DecCoin
// 3. Sets initial_held and initial_collateral snapshots for existing positions
func (k Keeper) MigrateWhaleswapLeverageInterest(ctx context.Context) error {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	k.Logger(sdkCtx).Info("Starting whaleswap leverage-interest migration")

	// Get all existing leverage positions
	positions, err := k.GetAllLeveragePositions(ctx)
	if err != nil {
		return fmt.Errorf("failed to get leverage positions: %w", err)
	}

	k.Logger(sdkCtx).Info("Found leverage positions to migrate", "count", len(positions))

	migratedCount := 0
	for i := range positions {
		pos := &positions[i] // Get pointer to the position

		// Skip if position is already migrated (has new fields populated)
		if !pos.InitialHeld.IsZero() || !pos.InitialCollateral.IsZero() {
			continue
		}

		// Migrate the position
		if err := k.migrateLeveragePosition(ctx, pos); err != nil {
			k.Logger(sdkCtx).Error("Failed to migrate position", "position_id", pos.PositionId, "error", err)
			continue
		}

		// Save the migrated position
		if err := k.savePosition(ctx, *pos, whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED); err != nil {
			k.Logger(sdkCtx).Error("Failed to save migrated position", "position_id", pos.PositionId, "error", err)
			continue
		}

		migratedCount++
		if i%100 == 0 { // Log progress every 100 positions
			k.Logger(sdkCtx).Info("Migration progress", "processed", i+1, "migrated", migratedCount)
		}
	}

	k.Logger(sdkCtx).Info("Completed whaleswap leverage-interest migration", "migrated_positions", migratedCount)
	return nil
}

// migrateLeveragePosition handles the migration of a single leverage position
func (k Keeper) migrateLeveragePosition(ctx context.Context, pos *whaleswapv1.LeveragePosition) error {
	// 1. Migrate interest_rate from repeated DecCoin to single DecCoin
	if err := k.migrateInterestRate(ctx, pos); err != nil {
		return fmt.Errorf("failed to migrate interest_rate: %w", err)
	}

	// 2. Migrate accrued_interest_remainder from string to DecCoin
	if err := k.migrateAccruedInterestRemainder(pos); err != nil {
		return fmt.Errorf("failed to migrate accrued_interest_remainder: %w", err)
	}

	// 3. Set initial_held and initial_collateral snapshots
	k.setInitialSnapshots(pos)

	return nil
}

// migrateInterestRate handles the conversion from old repeated DecCoin format to new single DecCoin format
func (k Keeper) migrateInterestRate(ctx context.Context, pos *whaleswapv1.LeveragePosition) error {
	// Check if we already have the interest rate for the borrowed denom
	for _, ir := range pos.InterestRate {
		if ir.Denom == pos.Borrowed.Denom {
			return nil // Already has the correct rate
		}
	}

	// For existing positions, we need to determine the appropriate interest rate
	// Get the current pool configuration to find the interest rate for the borrowed denom
	// If pool data is not available, use zero rate as fallback

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err == nil && len(pool.InterestRate) > 0 {
		// Find the interest rate for the borrowed denom from the pool
		for _, rate := range pool.InterestRate {
			if rate.Denom == pos.Borrowed.Denom {
				pos.InterestRate = sdk.NewDecCoins(rate)
				return nil
			}
		}
	}

	// Fallback: use zero interest rate if pool data is not available
	pos.InterestRate = sdk.NewDecCoins(sdk.NewDecCoinFromDec(pos.Borrowed.Denom, math.LegacyZeroDec()))
	return nil
}

// migrateAccruedInterestRemainder handles the conversion from old string format to new DecCoin format
func (k Keeper) migrateAccruedInterestRemainder(pos *whaleswapv1.LeveragePosition) error {
	// If already migrated (DecCoin with proper denom), skip
	if pos.AccruedInterestRemainder.Denom == pos.Borrowed.Denom {
		return nil
	}

	// For existing positions, we need to set a default remainder
	// Since the old string field is no longer accessible, we assume zero remainder
	// This is a reasonable assumption since remainder represents fractional interest < 1 coin
	pos.AccruedInterestRemainder = sdk.NewDecCoinFromDec(pos.Borrowed.Denom, math.LegacyZeroDec())
	return nil
}

// setInitialSnapshots sets the initial_held and initial_collateral fields for existing positions
func (k Keeper) setInitialSnapshots(pos *whaleswapv1.LeveragePosition) {
	// Set initial_held to current held value (since this is the opening snapshot)
	if pos.InitialHeld.IsZero() {
		pos.InitialHeld = pos.Held
	}

	// Set initial_collateral to current collateral value (since this is the opening snapshot)
	if pos.InitialCollateral.IsZero() {
		pos.InitialCollateral = pos.Collateral
	}
}

// GetAllLeveragePositions returns all leverage positions for migration purposes
func (k Keeper) GetAllLeveragePositions(ctx context.Context) ([]whaleswapv1.LeveragePosition, error) {
	var positions []whaleswapv1.LeveragePosition

	// Iterate through all positions in the store
	err := k.LeveragePositions.Walk(ctx, nil, func(key uint64, pos whaleswapv1.LeveragePosition) (bool, error) {
		positions = append(positions, pos)
		return false, nil // continue walking
	})

	return positions, err
}
