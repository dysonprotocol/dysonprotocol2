package keeper_test

import (
	"testing"

	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	"github.com/stretchr/testify/require"

	dysonprotocol "dysonprotocol.com"
	"dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	minttypes "github.com/cosmos/cosmos-sdk/x/mint/types"
)

func TestRebuildModuleInvariantsBurnsExcess(t *testing.T) {
	app := dysonprotocol.Setup(t, false)
	ctx := app.BaseApp.NewContextLegacy(false, cmtproto.Header{})

	pool := whaleswapv1.Pool{
		PoolId:      1,
		Coins:       sdk.NewCoins(sdk.NewInt64Coin("foo.dys", 1_000), sdk.NewInt64Coin("udys", 2_000)),
		SharesDenom: whaleswapv1.PoolSharesDenomForSuffix(".dys", 1), // Use static suffix for test
		FeesEarned:  sdk.NewCoins(sdk.NewInt64Coin("udys", 5)),
	}
	require.NoError(t, app.WhaleswapKeeper.PoolsMap.Set(ctx, pool.PoolId, pool))

	moduleCoins := sdk.NewCoins(
		sdk.NewInt64Coin("foo.dys", 1_000),
		sdk.NewInt64Coin("udys", 3_000), // reserves plus 1k untracked float
	)
	require.NoError(t, app.BankKeeper.MintCoins(ctx, minttypes.ModuleName, moduleCoins))
	require.NoError(t, app.BankKeeper.SendCoinsFromModuleToModule(ctx, minttypes.ModuleName, whaleswap.ModuleName, moduleCoins))

	report, err := app.WhaleswapKeeper.RebuildModuleInvariants(ctx)
	require.NoError(t, err)

	require.Equal(t, "5udys", report.FeesCleared.String())
	require.Equal(t, "1000udys", report.Burned.String())
	require.Equal(t, "1000foo.dys,2000udys", report.Expected.String())
	require.Equal(t, "1000foo.dys,2000udys", report.Actual.String())

	storedPool, err := app.WhaleswapKeeper.PoolsMap.Get(ctx, 1)
	require.NoError(t, err)
	require.Equal(t, 0, len(storedPool.FeesEarned))

	moduleAddr := app.AccountKeeper.GetModuleAddress(whaleswap.ModuleName)
	finalBalances := app.BankKeeper.GetAllBalances(ctx, moduleAddr)
	require.Equal(t, "1000foo.dys,2000udys", finalBalances.String())
}
