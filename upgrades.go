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

	if upgradeInfo.Name == UpgradeName && !app.UpgradeKeeper.IsSkipHeight(upgradeInfo.Height) {
		app.Logger().Info("Configuring store loader for upgrade", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
		storeUpgrades := storetypes.StoreUpgrades{
			Added: []string{
				epochstypes.ModuleName,
				protocolpooltypes.ModuleName,
			},
		}

		// configure store loader that checks if version == upgradeHeight and applies store upgrades
		app.SetStoreLoader(upgradetypes.UpgradeStoreLoader(upgradeInfo.Height, &storeUpgrades))
	} else if upgradeInfo.Name == UpgradeName && app.UpgradeKeeper.IsSkipHeight(upgradeInfo.Height) {
		app.Logger().Info("Skip height is set; not configuring store loader", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
	} else {
		app.Logger().Info("No store loader configured for current upgrade info", "disk_name", upgradeInfo.Name, "expected_name", UpgradeName, "height", upgradeInfo.Height)
	}
}
