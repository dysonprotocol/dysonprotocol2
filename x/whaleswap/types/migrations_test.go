package types_test

import (
	"encoding/json"
	"testing"
	"time"

	cosmossdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/stretchr/testify/require"

	"dysonprotocol.com/x/whaleswap/types"
)

func TestNormalizeLegacyGenesisJSON_ConvertsNumericDurations(t *testing.T) {
	t.Parallel()
	raw := []byte(`{"params":{"bid_timeout":5,"valuation_period":3600}}`)

	normalized, err := types.NormalizeLegacyGenesisJSON(raw)
	require.NoError(t, err)

	var decoded map[string]map[string]any
	require.NoError(t, json.Unmarshal(normalized, &decoded))
	params := decoded["params"]
	require.Equal(t, (5 * time.Second).String(), params["bid_timeout"])
	require.Equal(t, time.Hour.String(), params["valuation_period"])
}

func TestMigrateParams_BackfillsDefaults(t *testing.T) {
	t.Parallel()
	defaults := types.DefaultParams()
	legacy := types.Params{
		PfandPerOffer:               defaults.PfandPerOffer,
		ValuationFeePct:             defaults.ValuationFeePct,
		ValuationPeriod:             0,
		BidTimeout:                  0,
		MinimumBidPercentIncrease:   defaults.MinimumBidPercentIncrease,
		MaxNoteLength:               defaults.MaxNoteLength,
		BlockDelayBeforeClose:       0,
		BlockDelayBeforeLiquidation: 0,
	}

	migrated := types.MigrateParams(legacy)
	require.Equal(t, defaults.ValuationPeriod, migrated.ValuationPeriod)
	require.Equal(t, defaults.BidTimeout, migrated.BidTimeout)
	require.Equal(t, defaults.BlockDelayBeforeClose, migrated.BlockDelayBeforeClose)
	require.Equal(t, defaults.BlockDelayBeforeLiquidation, migrated.BlockDelayBeforeLiquidation)

	// Non-zero values are preserved.
	custom := defaults
	custom.ValuationPeriod = 2 * time.Hour
	custom.BidTimeout = 42 * time.Second
	custom.BlockDelayBeforeClose = 99
	custom.BlockDelayBeforeLiquidation = 123

	customMigrated := types.MigrateParams(custom)
	require.Equal(t, 2*time.Hour, customMigrated.ValuationPeriod)
	require.Equal(t, 42*time.Second, customMigrated.BidTimeout)
	require.Equal(t, uint64(99), customMigrated.BlockDelayBeforeClose)
	require.Equal(t, uint64(123), customMigrated.BlockDelayBeforeLiquidation)
}

func TestMigratePool_NormalizesRiskVectors(t *testing.T) {
	t.Parallel()
	pool := types.Pool{
		Coins: sdk.NewCoins(
			sdk.NewInt64Coin("foo", 1_000),
			sdk.NewInt64Coin("bar", 1_000),
		),
		MinCollateralRatio: sdk.DecCoins{
			sdk.NewDecCoinFromDec("foo", cosmossdkmath.LegacyMustNewDecFromStr("1.4")),
		},
		MaxLeverageRatio:     sdk.DecCoins{},
		LiquidationThreshold: sdk.DecCoins{},
		MaxBorrowPercent: sdk.DecCoins{
			sdk.NewDecCoinFromDec("foo", cosmossdkmath.LegacyMustNewDecFromStr("0.70")),
		},
		InterestRate: sdk.DecCoins{
			sdk.NewDecCoinFromDec("foo", cosmossdkmath.LegacyMustNewDecFromStr("0.01")),
		},
	}

	types.MigratePool(&pool)

	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("1.4"), pool.MinCollateralRatio.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("1.4"), pool.MinCollateralRatio.AmountOf("bar"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("20"), pool.MaxLeverageRatio.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("20"), pool.MaxLeverageRatio.AmountOf("bar"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("1.2"), pool.LiquidationThreshold.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("1.2"), pool.LiquidationThreshold.AmountOf("bar"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("0.70"), pool.MaxBorrowPercent.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("0.70"), pool.MaxBorrowPercent.AmountOf("bar"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("0.01"), pool.InterestRate.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("0.01"), pool.InterestRate.AmountOf("bar"))
}

func TestMigratePool_ReplacesInvalidValues(t *testing.T) {
	t.Parallel()
	pool := types.Pool{
		Coins: sdk.NewCoins(
			sdk.NewInt64Coin("foo", 500),
			sdk.NewInt64Coin("bar", 500),
		),
		MinCollateralRatio: sdk.DecCoins{
			sdk.NewDecCoinFromDec("foo", cosmossdkmath.LegacyMustNewDecFromStr("0.9")),
			sdk.NewDecCoinFromDec("bar", cosmossdkmath.LegacyMustNewDecFromStr("0.8")),
		},
		MaxLeverageRatio: sdk.DecCoins{},
		LiquidationThreshold: sdk.DecCoins{
			sdk.NewDecCoinFromDec("foo", cosmossdkmath.LegacyMustNewDecFromStr("0.95")),
		},
		MaxBorrowPercent: sdk.DecCoins{
			sdk.NewDecCoinFromDec("foo", cosmossdkmath.LegacyMustNewDecFromStr("1.1")),
			sdk.NewDecCoinFromDec("bar", cosmossdkmath.LegacyMustNewDecFromStr("-0.2")),
		},
		InterestRate: sdk.DecCoins{
			sdk.NewDecCoinFromDec("foo", cosmossdkmath.LegacyMustNewDecFromStr("-0.5")),
		},
	}

	types.MigratePool(&pool)

	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("1.5"), pool.MinCollateralRatio.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("1.5"), pool.MinCollateralRatio.AmountOf("bar"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("20"), pool.MaxLeverageRatio.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("20"), pool.MaxLeverageRatio.AmountOf("bar"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("1.2"), pool.LiquidationThreshold.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("1.2"), pool.LiquidationThreshold.AmountOf("bar"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("0.80"), pool.MaxBorrowPercent.AmountOf("foo"))
	require.Equal(t, cosmossdkmath.LegacyMustNewDecFromStr("0.80"), pool.MaxBorrowPercent.AmountOf("bar"))
	require.True(t, pool.InterestRate.AmountOf("foo").IsZero())
	require.True(t, pool.InterestRate.AmountOf("bar").IsZero())
}
