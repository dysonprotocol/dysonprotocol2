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

	// Map deprecated timestamps/heights to new normalized fields if missing
	if pool.CreatedTime == nil && pool.Created != nil {
		pool.CreatedTime = pool.Created
	}
	if pool.UpdatedTime == nil && pool.Updated != nil {
		pool.UpdatedTime = pool.Updated
	}
	if pool.CreatedHeight == 0 && pool.BlockHeight > 0 {
		pool.CreatedHeight = pool.BlockHeight
	}
	if pool.UpdatedHeight == 0 {
		// Best-effort default: use created_height if updated_time exists but height missing
		if pool.UpdatedTime != nil {
			pool.UpdatedHeight = pool.CreatedHeight
		}
	}

	pool.MinInitialCollateralRatio = ensurePerDenomDecCoins(
		pool.MinInitialCollateralRatio,
		denomA, denomB,
		defaultMinCR, defaultMinCR,
		func(d cosmossdkmath.LegacyDec) bool { return d.GT(oneDec) },
	)
	// Deprecated: max_leverage_ratio is no longer used. Only normalize if already set (for backward compatibility),
	// but don't populate defaults since it's deprecated and should remain empty for new pools.
	if len(pool.MaxLeverageRatio) > 0 {
		pool.MaxLeverageRatio = ensurePerDenomDecCoins(
			pool.MaxLeverageRatio,
			denomA, denomB,
			defaultMaxLev, defaultMaxLev,
			func(d cosmossdkmath.LegacyDec) bool { return d.GT(oneDec) },
		)
	} else {
		// Keep empty for new pools (deprecated field)
		pool.MaxLeverageRatio = sdk.DecCoins{}
	}
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

// MigrateOffer normalizes OfferData timestamps to the new created/updated time/height fields.
func MigrateOffer(offer *OfferData) {
	if offer == nil {
		return
	}
	// Backfill updated_time from deprecated updated_timestamp
	if offer.UpdatedTime == nil && offer.UpdatedTimestamp != nil {
		offer.UpdatedTime = offer.UpdatedTimestamp
	}
	// If created fields are unset, derive best-effort defaults from updated
	if offer.CreatedTime == nil && offer.UpdatedTime != nil {
		offer.CreatedTime = offer.UpdatedTime
	}
	if offer.CreatedHeight == 0 && offer.UpdatedHeight > 0 {
		offer.CreatedHeight = offer.UpdatedHeight
	}
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
	var root map[string]json.RawMessage
	if err := json.Unmarshal(raw, &root); err != nil {
		return nil, false, err
	}

	changed := false

	if paramsRaw, ok := root["params"]; ok && len(bytes.TrimSpace(paramsRaw)) > 0 {
		updatedParams, paramsChanged, err := normalizeLegacyParamsJSON(paramsRaw)
		if err != nil {
			return nil, false, fmt.Errorf("normalize params: %w", err)
		}
		if paramsChanged {
			root["params"] = updatedParams
			changed = true
		}
	}

	if poolsRaw, ok := root["pools"]; ok && len(bytes.TrimSpace(poolsRaw)) > 0 {
		updatedPools, poolsChanged, err := normalizeLegacyPoolsJSON(poolsRaw)
		if err != nil {
			return nil, false, fmt.Errorf("normalize pools: %w", err)
		}
		if poolsChanged {
			root["pools"] = updatedPools
			changed = true
		}
	}

	if metricsRaw, ok := root["address_metrics"]; ok && len(bytes.TrimSpace(metricsRaw)) > 0 {
		updatedMetrics, metricsChanged, err := normalizeLegacyAddressMetricsJSON(metricsRaw)
		if err != nil {
			return nil, false, fmt.Errorf("normalize address metrics: %w", err)
		}
		if metricsChanged {
			root["address_metrics"] = updatedMetrics
			changed = true
		}
	}

	if !changed {
		return nil, false, nil
	}

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

func normalizeLegacyPoolsJSON(raw json.RawMessage) ([]byte, bool, error) {
	var pools []map[string]any
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := dec.Decode(&pools); err != nil {
		return nil, false, err
	}

	changed := false
	for _, pool := range pools {
		if pool == nil {
			continue
		}

		poolID := renderInterfaceString(pool["pool_id"])

		if val, ok := pool["min_collateral_ratio"]; ok {
			if _, exists := pool["min_initial_collateral_ratio"]; !exists {
				pool["min_initial_collateral_ratio"] = val
			}
			delete(pool, "min_collateral_ratio")
			changed = true
		}

		if feePct, ok := pool["fee_pct"]; ok {
			delete(pool, "fee_pct")
			changed = true

			if needsFeeRate(pool["fee_rate"]) {
				amountStr := strings.TrimSpace(renderInterfaceString(feePct))
				if amountStr != "" {
					feeDec, err := cosmossdkmath.LegacyNewDecFromStr(amountStr)
					if err != nil {
						return nil, false, fmt.Errorf("pool %s invalid fee_pct: %w", poolID, err)
					}
					denoms, err := extractPoolDenoms(pool["coins"])
					if err != nil {
						return nil, false, fmt.Errorf("pool %s: %w", poolID, err)
					}
					feeRate := make([]map[string]string, len(denoms))
					for i, denom := range denoms {
						feeRate[i] = map[string]string{
							"denom":  denom,
							"amount": feeDec.String(),
						}
					}
					pool["fee_rate"] = feeRate
				}
			}
		}
	}

	if !changed {
		return nil, false, nil
	}
	buf, err := json.Marshal(pools)
	if err != nil {
		return nil, false, err
	}
	return buf, true, nil
}

func normalizeLegacyAddressMetricsJSON(raw json.RawMessage) ([]byte, bool, error) {
	var metrics []map[string]any
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := dec.Decode(&metrics); err != nil {
		return nil, false, err
	}

	changed := false
	for _, entry := range metrics {
		if entry == nil {
			continue
		}
		pnl, ok := entry["leverage_pnl"]
		if !ok {
			continue
		}
		delete(entry, "leverage_pnl")
		if _, exists := entry["profit"]; !exists {
			entry["profit"] = pnl
		}
		if _, exists := entry["losses"]; !exists {
			entry["losses"] = []any{}
		}
		changed = true
	}

	if !changed {
		return nil, false, nil
	}
	buf, err := json.Marshal(metrics)
	if err != nil {
		return nil, false, err
	}
	return buf, true, nil
}

func needsFeeRate(value any) bool {
	if value == nil {
		return true
	}
	arr, ok := value.([]any)
	if !ok {
		return false
	}
	return len(arr) == 0
}

func extractPoolDenoms(value any) ([]string, error) {
	arr, ok := value.([]any)
	if !ok {
		return nil, fmt.Errorf("coins must be an array")
	}
	if len(arr) < 2 {
		return nil, fmt.Errorf("coins must contain at least two entries")
	}
	denoms := make([]string, len(arr))
	for i, item := range arr {
		entry, ok := item.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("coin entry %d must be an object", i)
		}
		denom, ok := entry["denom"].(string)
		if !ok || strings.TrimSpace(denom) == "" {
			return nil, fmt.Errorf("coin entry %d missing denom", i)
		}
		denoms[i] = denom
	}
	return denoms, nil
}

func renderInterfaceString(v any) string {
	switch val := v.(type) {
	case string:
		return val
	case json.Number:
		return val.String()
	case fmt.Stringer:
		return val.String()
	default:
		if val == nil {
			return ""
		}
		return fmt.Sprintf("%v", val)
	}
}
