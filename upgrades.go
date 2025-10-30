package dysonprotocol

import (
	"context"

	"strings"

	upgradetypes "cosmossdk.io/x/upgrade/types"

	"github.com/cosmos/cosmos-sdk/types/module"
)

// WhaleswapV2UpgradeName defines the on-chain upgrade name for
// migrating whaleswap module from v1 proto fields to v2 (fee_pct → fee_rate,
// Trade deprecated fields → new fields). This includes state migration.
const WhaleswapV2UpgradeName = "whaleswap-v2"

func (app *DysApp) RegisterUpgradeHandlers() {
	app.Logger().Info("RegisterUpgradeHandlers: installing upgrade handlers")

	// Register handler for whaleswap-v2 (state migration upgrade)
	app.UpgradeKeeper.SetUpgradeHandler(
		WhaleswapV2UpgradeName,
		func(ctx context.Context, plan upgradetypes.Plan, fromVM module.VersionMap) (module.VersionMap, error) {
			app.Logger().Info("Executing whaleswap v1→v2 migration", "name", plan.Name, "height", plan.Height)

			// Run whaleswap state migration
			if err := app.WhaleswapKeeper.MigrateWhaleswapV1ToV2(ctx); err != nil {
				app.Logger().Error("Whaleswap migration failed", "name", plan.Name, "height", plan.Height, "err", err)
				return fromVM, err
			}
			app.Logger().Info("Whaleswap migration completed", "name", plan.Name, "height", plan.Height)

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
		case WhaleswapV2UpgradeName:
			// State migration upgrade; no store migrations needed (migration happens in handler)
			app.Logger().Info("Whaleswap v2 upgrade; state migration in handler", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
		default:
			app.Logger().Info("No store loader configured for current upgrade info", "disk_name", upgradeInfo.Name, "expected_names", []string{WhaleswapV2UpgradeName}, "height", upgradeInfo.Height)
		}
	} else if upgradeInfo.Name == WhaleswapV2UpgradeName {
		app.Logger().Info("Skip height is set; not configuring store loader", "name", upgradeInfo.Name, "height", upgradeInfo.Height)
	} else {
		app.Logger().Info("No store loader configured for current upgrade info", "disk_name", upgradeInfo.Name, "expected_names", []string{WhaleswapV2UpgradeName}, "height", upgradeInfo.Height)
	}
}
