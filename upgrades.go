package dysonprotocol

import (
	"context"

	"strings"

	storetypes "cosmossdk.io/store/types"
	upgradetypes "cosmossdk.io/x/upgrade/types"

	"github.com/cosmos/cosmos-sdk/types/module"
	epochstypes "github.com/cosmos/cosmos-sdk/x/epochs/types"
	protocolpooltypes "github.com/cosmos/cosmos-sdk/x/protocolpool/types"
)

// UpgradeName defines the on-chain upgrade name for the sample DysApp upgrade
// from v050 to v053.
//
// NOTE: This upgrade defines a reference implementation of what an upgrade
// could look like when an application is migrating from Cosmos SDK version
// v0.50.x to v0.53.x.
const UpgradeName = "v050-to-v053"

// RemoveCircuitUpgradeName defines the on-chain upgrade name that removes the
// deprecated "circuit" module store from state.
const RemoveCircuitUpgradeName = "remove-circuit"

// V2RC9UpgradeName defines the on-chain upgrade name for v2.0.0-rc9.
const V2RC9UpgradeName = "v2.0.0-rc9"

func (app *DysApp) RegisterUpgradeHandlers() {
	app.Logger().Info("RegisterUpgradeHandlers: installing upgrade handlers")
	app.UpgradeKeeper.SetUpgradeHandler(
		UpgradeName,
		func(ctx context.Context, plan upgradetypes.Plan, fromVM module.VersionMap) (module.VersionMap, error) {
			app.Logger().Info("Executing upgrade handler", "name", plan.Name, "height", plan.Height)
			newVM, err := app.ModuleManager.RunMigrations(ctx, app.Configurator(), fromVM)
			if err != nil {
				app.Logger().Error("Upgrade handler failed", "name", plan.Name, "height", plan.Height, "err", err)
				return newVM, err
			}
			app.Logger().Info("Upgrade handler completed", "name", plan.Name, "height", plan.Height)
			return newVM, nil
		},
	)

	// Register handler for removing the deprecated circuit module store
	app.UpgradeKeeper.SetUpgradeHandler(
		RemoveCircuitUpgradeName,
		func(ctx context.Context, plan upgradetypes.Plan, fromVM module.VersionMap) (module.VersionMap, error) {
			app.Logger().Info("Executing upgrade handler", "name", plan.Name, "height", plan.Height)
			newVM, err := app.ModuleManager.RunMigrations(ctx, app.Configurator(), fromVM)
			if err != nil {
				app.Logger().Error("Upgrade handler failed", "name", plan.Name, "height", plan.Height, "err", err)
				return newVM, err
			}
			app.Logger().Info("Upgrade handler completed", "name", plan.Name, "height", plan.Height)
			return newVM, nil
		},
	)

	// Register handler for v2.0.0-rc9
	app.UpgradeKeeper.SetUpgradeHandler(
		V2RC9UpgradeName,
		func(ctx context.Context, plan upgradetypes.Plan, fromVM module.VersionMap) (module.VersionMap, error) {
			app.Logger().Info("Executing upgrade handler", "name", plan.Name, "height", plan.Height)
			newVM, err := app.ModuleManager.RunMigrations(ctx, app.Configurator(), fromVM)
			if err != nil {
				app.Logger().Error("Upgrade handler failed", "name", plan.Name, "height", plan.Height, "err", err)
				return newVM, err
			}
			app.Logger().Info("Upgrade handler completed", "name", plan.Name, "height", plan.Height)
			return newVM, nil
		},
	)

	// Note: Do NOT register test upgrade handlers here pre-emptively.
	// The SDK will abort if a handler exists before the planned height ("binary updated before trigger").

	app.Logger().Info("Reading upgrade info from disk to determine dynamic handlers/store loader")
	upgradeInfo, err := app.UpgradeKeeper.ReadUpgradeInfoFromDisk()
	if err != nil {
		panic(err)
	}
	app.Logger().Info("Upgrade info from disk", "name", upgradeInfo.Name, "height", upgradeInfo.Height)

	// If we are restarting after an upgrade panic, only now register the matching test handler by name.
	if strings.HasPrefix(upgradeInfo.Name, "test-") {
		app.Logger().Info("Registering dynamic test upgrade handler", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
		app.UpgradeKeeper.SetUpgradeHandler(
			upgradeInfo.Name,
			func(ctx context.Context, plan upgradetypes.Plan, fromVM module.VersionMap) (module.VersionMap, error) {
				app.Logger().Info("Executing test upgrade handler", "name", plan.Name, "height", plan.Height)
				newVM, err := app.ModuleManager.RunMigrations(ctx, app.Configurator(), fromVM)
				if err != nil {
					app.Logger().Error("Test upgrade handler failed", "name", plan.Name, "height", plan.Height, "err", err)
					return newVM, err
				}
				app.Logger().Info("Test upgrade handler completed", "name", plan.Name, "height", plan.Height)
				return newVM, nil
			},
		)
	}

	if !app.UpgradeKeeper.IsSkipHeight(upgradeInfo.Height) {
		switch upgradeInfo.Name {
		case UpgradeName:
			app.Logger().Info("Configuring store loader for upgrade", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
			storeUpgrades := storetypes.StoreUpgrades{
				Added: []string{
					epochstypes.ModuleName,
					protocolpooltypes.ModuleName,
				},
			}
			// configure store loader that checks if version == upgradeHeight and applies store upgrades
			app.SetStoreLoader(upgradetypes.UpgradeStoreLoader(upgradeInfo.Height, &storeUpgrades))
		case RemoveCircuitUpgradeName:
			app.Logger().Info("Configuring store loader to delete deprecated module store", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
			storeUpgrades := storetypes.StoreUpgrades{
				Deleted: []string{
					"circuit", // store key matches x/circuit types.ModuleName
				},
			}
			// configure store loader that checks if version == upgradeHeight and applies store deletions
			app.SetStoreLoader(upgradetypes.UpgradeStoreLoader(upgradeInfo.Height, &storeUpgrades))
		case V2RC9UpgradeName:
			// No store upgrades required for v2.0.0-rc9
			app.Logger().Info("No store upgrades for this upgrade; not configuring store loader", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
		default:
			app.Logger().Info("No store loader configured for current upgrade info", "disk_name", upgradeInfo.Name, "expected_names", []string{UpgradeName, RemoveCircuitUpgradeName, V2RC9UpgradeName}, "height", upgradeInfo.Height)
		}
	} else if upgradeInfo.Name == UpgradeName || upgradeInfo.Name == RemoveCircuitUpgradeName || upgradeInfo.Name == V2RC9UpgradeName {
		app.Logger().Info("Skip height is set; not configuring store loader", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
	} else {
		app.Logger().Info("No store loader configured for current upgrade info", "disk_name", upgradeInfo.Name, "expected_names", []string{UpgradeName, RemoveCircuitUpgradeName, V2RC9UpgradeName}, "height", upgradeInfo.Height)
	}
}
