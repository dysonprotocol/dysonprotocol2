package dysonprotocol

import (
    "context"

    "strings"

    upgradetypes "cosmossdk.io/x/upgrade/types"

    "github.com/cosmos/cosmos-sdk/types/module"
)

// (removed legacy upgrade names)

// RmHistoricalQueriesUpgradeName defines the on-chain upgrade name for
// removing historical query support in the script module. This is an
// export/import style upgrade with no store upgrades.
const RmHistoricalQueriesUpgradeName = "rm-historical-queries"

func (app *DysApp) RegisterUpgradeHandlers() {
	app.Logger().Info("RegisterUpgradeHandlers: installing upgrade handlers")
    // (removed legacy handlers)

	// Register handler for rm-historical-queries (export/import upgrade)
	app.UpgradeKeeper.SetUpgradeHandler(
		RmHistoricalQueriesUpgradeName,
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
        case RmHistoricalQueriesUpgradeName:
			// Export/Import style upgrade; no store upgrades
			app.Logger().Info("Export/Import upgrade; no store upgrades configured", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
		default:
            app.Logger().Info("No store loader configured for current upgrade info", "disk_name", upgradeInfo.Name, "expected_names", []string{RmHistoricalQueriesUpgradeName}, "height", upgradeInfo.Height)
		}
    } else if upgradeInfo.Name == RmHistoricalQueriesUpgradeName {
		app.Logger().Info("Skip height is set; not configuring store loader", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
	} else {
        app.Logger().Info("No store loader configured for current upgrade info", "disk_name", upgradeInfo.Name, "expected_names", []string{RmHistoricalQueriesUpgradeName}, "height", upgradeInfo.Height)
	}
}
