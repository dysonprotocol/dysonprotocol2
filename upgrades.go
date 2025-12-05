package dysonprotocol

import (
	"context"

	"strings"

	upgradetypes "cosmossdk.io/x/upgrade/types"

	"github.com/cosmos/cosmos-sdk/types/module"
)

// ProtorevUpgradeName defines the on-chain upgrade name for the
// whaleswap arbitrage (protorev) feature.
const ProtorevUpgradeName = "protorev"

func (app *DysApp) RegisterUpgradeHandlers() {
	// Register handler for protorev upgrade
	app.UpgradeKeeper.SetUpgradeHandler(
		ProtorevUpgradeName,
		func(ctx context.Context, plan upgradetypes.Plan, fromVM module.VersionMap) (module.VersionMap, error) {
			app.Logger().Info("Executing protorev upgrade", "name", plan.Name, "height", plan.Height)

			// Run module migrations
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

	upgradeInfo, err := app.UpgradeKeeper.ReadUpgradeInfoFromDisk()
	if err != nil {
		panic(err)
	}

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
		if upgradeInfo.Name == ProtorevUpgradeName {
			// Feature upgrade; no store migrations needed
		}
	} else if upgradeInfo.Name == ProtorevUpgradeName {
		// Skip height is set; not configuring store loader
	}
}
