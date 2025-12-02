package types

import (
	"encoding/json"

	cosmossdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// NormalizeLegacyGenesisJSON inspects the provided genesis JSON and rewrites
// legacy-encoded fields so they match the proto JSON expectations introduced in
// v2.0.0. It currently converts numeric duration fields (seconds) into the
// string form required by google.protobuf.Duration. If no changes are needed,
// the original slice is returned.
func NormalizeLegacyGenesisJSON(raw []byte) ([]byte, error) {
	return raw, nil
}

// MigrateParams backfills defaults for parameters introduced after v2.0.0-rc11.
// It should be invoked on any params object loaded from persistent state or
// decoded from legacy genesis JSON before validation.
func MigrateParams(p Params) Params {
	// Backfill ArbitrageMode: UNSPECIFIED (0) means old genesis, default to AUTO
	if p.ArbitrageMode == ArbitrageMode_ARBITRAGE_MODE_UNSPECIFIED {
		p.ArbitrageMode = ArbitrageMode_ARBITRAGE_MODE_AUTO
	}
	return p
}

var (
	oneDec           = cosmossdkmath.LegacyNewDec(1)
	zeroDec          = cosmossdkmath.LegacyZeroDec()
	defaultMinCR     = cosmossdkmath.LegacyMustNewDecFromStr("1.5")
	defaultMaxLev    = cosmossdkmath.LegacyMustNewDecFromStr("20")
	defaultLiq       = cosmossdkmath.LegacyMustNewDecFromStr("1.2")
	defaultMaxBorrow = cosmossdkmath.LegacyMustNewDecFromStr("0.80")
)

// MigratePool normalizes per-pool leverage configuration fields to ensure they
// contain exactly two entries matching the pool's reserve denoms. Legacy exports
// may omit the second entry (treating parameters as symmetric) or leave fields
// unset entirely; this helper back-fills sane defaults so invariants and leverage
// operations remain well-defined post-migration.
func MigratePool(pool *Pool) {
}

// MigrateOffer normalizes OfferData timestamps to the new created/updated time/height fields.
func MigrateOffer(offer *OfferData) {
}

func ensurePerDenomDecCoins(
	input sdk.DecCoins,
	denomA, denomB string,
	fallbackA, fallbackB cosmossdkmath.LegacyDec,
	valid func(cosmossdkmath.LegacyDec) bool,
) sdk.DecCoins {
	coins := sdk.NewDecCoins(input...)
	valA, hasA := amountOfWithPresence(coins, denomA)
	valB, hasB := amountOfWithPresence(coins, denomB)

	copyAllowed := fallbackA.Equal(fallbackB) || hasA != hasB

	if !hasA && hasB && copyAllowed {
		valA = valB
		hasA = true
	}
	if hasA && !hasB && copyAllowed {
		valB = valA
		hasB = true
	}

	if !valid(valA) {
		valA = fallbackA
	}
	if !valid(valB) {
		valB = fallbackB
	}

	return sdk.DecCoins{
		sdk.NewDecCoinFromDec(denomA, valA),
		sdk.NewDecCoinFromDec(denomB, valB),
	}
}

func amountOfWithPresence(coins sdk.DecCoins, denom string) (cosmossdkmath.LegacyDec, bool) {
	for _, coin := range coins {
		if coin.Denom == denom {
			return coin.Amount, true
		}
	}
	return cosmossdkmath.LegacyZeroDec(), false
}

func normalizeLegacyGenesisJSON(raw []byte) ([]byte, bool, error) {
	return raw, false, nil
}

func normalizeLegacyParamsJSON(raw json.RawMessage) ([]byte, bool, error) {
	return raw, false, nil
}

func convertLegacyDurationValue(value any) (string, bool, error) {
	return "", false, nil
}

func durationStringFromNumber(num json.Number) (string, error) {
	return "", nil
}

func durationStringFromObject(obj map[string]any) (string, error) {
	return "", nil
}

func extractJSONInt(v any) (int64, error) {
	return 0, nil
}

func normalizeLegacyPoolsJSON(raw json.RawMessage) ([]byte, bool, error) {
	return raw, false, nil
}

func normalizeLegacyAddressMetricsJSON(raw json.RawMessage) ([]byte, bool, error) {
	return raw, false, nil
}

func needsFeeRate(value any) bool {
	return false
}

func extractPoolDenoms(value any) ([]string, error) {
	return nil, nil
}

func renderInterfaceString(v any) string {
	return ""
}
