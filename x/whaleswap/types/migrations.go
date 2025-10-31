package types

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	cosmossdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// NormalizeLegacyGenesisJSON inspects the provided genesis JSON and rewrites
// legacy-encoded fields so they match the proto JSON expectations introduced in
// v2.0.0. It currently converts numeric duration fields (seconds) into the
// string form required by google.protobuf.Duration. If no changes are needed,
// the original slice is returned.
func NormalizeLegacyGenesisJSON(raw []byte) ([]byte, error) {
	normalized, changed, err := normalizeLegacyGenesisJSON(raw)
	if err != nil {
		return nil, err
	}
	if !changed {
		return raw, nil
	}
	return normalized, nil
}

// MigrateParams backfills defaults for parameters introduced after v2.0.0-rc11.
// It should be invoked on any params object loaded from persistent state or
// decoded from legacy genesis JSON before validation.
func MigrateParams(p Params) Params {
	defaults := DefaultParams()
	if p.ValuationPeriod <= 0 {
		p.ValuationPeriod = defaults.ValuationPeriod
	}
	if p.BidTimeout <= 0 {
		p.BidTimeout = defaults.BidTimeout
	}
	if p.BlockDelayBeforeClose == 0 {
		p.BlockDelayBeforeClose = defaults.BlockDelayBeforeClose
	}
	if p.BlockDelayBeforeLiquidation == 0 {
		p.BlockDelayBeforeLiquidation = defaults.BlockDelayBeforeLiquidation
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
	if pool == nil || len(pool.Coins) != 2 {
		return
	}
	denomA := pool.Coins[0].Denom
	denomB := pool.Coins[1].Denom
	// Clear deprecated min/max price bands if present.
	if len(pool.MinPrice) > 0 {
		pool.MinPrice = sdk.NewCoins()
	}
	if len(pool.MaxPrice) > 0 {
		pool.MaxPrice = sdk.NewCoins()
	}

	pool.MinCollateralRatio = ensurePerDenomDecCoins(
		pool.MinCollateralRatio,
		denomA, denomB,
		defaultMinCR, defaultMinCR,
		func(d cosmossdkmath.LegacyDec) bool { return d.GT(oneDec) },
	)
	pool.MaxLeverageRatio = ensurePerDenomDecCoins(
		pool.MaxLeverageRatio,
		denomA, denomB,
		defaultMaxLev, defaultMaxLev,
		func(d cosmossdkmath.LegacyDec) bool { return d.GT(oneDec) },
	)
	pool.LiquidationThreshold = ensurePerDenomDecCoins(
		pool.LiquidationThreshold,
		denomA, denomB,
		defaultLiq, defaultLiq,
		func(d cosmossdkmath.LegacyDec) bool { return d.GT(oneDec) },
	)
	pool.MaxBorrowPercent = ensurePerDenomDecCoins(
		pool.MaxBorrowPercent,
		denomA, denomB,
		defaultMaxBorrow, defaultMaxBorrow,
		func(d cosmossdkmath.LegacyDec) bool { return !d.IsNegative() && d.LT(oneDec) },
	)
	pool.InterestRate = ensurePerDenomDecCoins(
		pool.InterestRate,
		denomA, denomB,
		zeroDec, zeroDec,
		func(d cosmossdkmath.LegacyDec) bool { return !d.IsNegative() },
	)
}

func ensurePerDenomDecCoins(
	input sdk.DecCoins,
	denomA, denomB string,
	fallbackA, fallbackB cosmossdkmath.LegacyDec,
	valid func(cosmossdkmath.LegacyDec) bool,
) sdk.DecCoins {
	coins := sdk.NewDecCoins(input...)
	valA := coins.AmountOf(denomA)
	valB := coins.AmountOf(denomB)

	if !valid(valA) {
		valA = fallbackA
	}
	if !valid(valB) {
		if valid(valA) && (len(coins) == 1 || fallbackA.Equal(fallbackB)) {
			valB = valA
		} else {
			valB = fallbackB
		}
	}

	return sdk.DecCoins{
		sdk.NewDecCoinFromDec(denomA, valA),
		sdk.NewDecCoinFromDec(denomB, valB),
	}
}

func normalizeLegacyGenesisJSON(raw []byte) ([]byte, bool, error) {
	var root map[string]json.RawMessage
	if err := json.Unmarshal(raw, &root); err != nil {
		return nil, false, err
	}

	paramsRaw, ok := root["params"]
	if !ok || len(bytes.TrimSpace(paramsRaw)) == 0 {
		return nil, false, nil
	}

	updatedParams, changed, err := normalizeLegacyParamsJSON(paramsRaw)
	if err != nil {
		return nil, false, fmt.Errorf("normalize params: %w", err)
	}
	if !changed {
		return nil, false, nil
	}

	root["params"] = updatedParams
	buf, err := json.Marshal(root)
	if err != nil {
		return nil, false, err
	}
	return buf, true, nil
}

func normalizeLegacyParamsJSON(raw json.RawMessage) ([]byte, bool, error) {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	params := map[string]any{}
	if err := dec.Decode(&params); err != nil {
		return nil, false, err
	}

	changed := false
	for _, key := range []string{"bid_timeout", "valuation_period"} {
		val, ok := params[key]
		if !ok {
			continue
		}
		rewritten, didRewrite, err := convertLegacyDurationValue(val)
		if err != nil {
			return nil, false, fmt.Errorf("%s: %w", key, err)
		}
		if didRewrite {
			params[key] = rewritten
			changed = true
		}
	}

	if !changed {
		return nil, false, nil
	}

	buf, err := json.Marshal(params)
	if err != nil {
		return nil, false, err
	}
	return buf, true, nil
}

func convertLegacyDurationValue(value any) (string, bool, error) {
	switch v := value.(type) {
	case string:
		if strings.TrimSpace(v) == "" {
			return "", false, nil
		}
		return "", false, nil
	case json.Number:
		dur, err := durationStringFromNumber(v)
		if err != nil {
			return "", false, err
		}
		return dur, true, nil
	case float64:
		dur := time.Duration(v * float64(time.Second))
		return dur.String(), true, nil
	case map[string]any:
		dur, err := durationStringFromObject(v)
		if err != nil {
			return "", false, err
		}
		if dur == "" {
			return "", false, nil
		}
		return dur, true, nil
	default:
		return "", false, nil
	}
}

func durationStringFromNumber(num json.Number) (string, error) {
	if i, err := num.Int64(); err == nil {
		return (time.Duration(i) * time.Second).String(), nil
	}
	f, err := num.Float64()
	if err != nil {
		return "", err
	}
	return time.Duration(f * float64(time.Second)).String(), nil
}

func durationStringFromObject(obj map[string]any) (string, error) {
	seconds, err := extractJSONInt(obj["seconds"])
	if err != nil {
		return "", err
	}
	nanos, err := extractJSONInt(obj["nanos"])
	if err != nil {
		return "", err
	}
	if seconds == 0 && nanos == 0 {
		return "", nil
	}
	d := time.Duration(seconds)*time.Second + time.Duration(nanos)*time.Nanosecond
	return d.String(), nil
}

func extractJSONInt(v any) (int64, error) {
	switch val := v.(type) {
	case nil:
		return 0, nil
	case json.Number:
		return val.Int64()
	case string:
		if strings.TrimSpace(val) == "" {
			return 0, nil
		}
		i, err := strconv.ParseInt(val, 10, 64)
		if err != nil {
			return 0, err
		}
		return i, nil
	case float64:
		return int64(val), nil
	default:
		return 0, fmt.Errorf("unsupported number type %T", v)
	}
}
