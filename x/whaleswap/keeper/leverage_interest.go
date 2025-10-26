package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

const secondsPerYear = 365.25 * 24 * 60 * 60

// CalculateInterest computes accrued interest on borrowed amount.
// interest = borrowed_amount × rate × (elapsed_seconds / seconds_per_year)
func (k Keeper) CalculateInterest(borrowed math.Int, annualRate math.LegacyDec, elapsedSeconds int64) (math.LegacyDec, error) {
	if borrowed.IsNegative() || elapsedSeconds < 0 {
		return math.LegacyDec{}, fmt.Errorf("borrowed and elapsed_seconds must be non-negative")
	}
	borrowedDec := math.LegacyNewDecFromInt(borrowed)
	timeRatio := math.LegacyNewDec(elapsedSeconds).Quo(math.LegacyNewDec(int64(secondsPerYear)))
	interest := borrowedDec.Mul(annualRate).Mul(timeRatio)
	return interest, nil
}

// ComputeEffectiveRepayment returns principal + accrued interest as integer.
func (k Keeper) ComputeEffectiveRepayment(principal math.Int, interest math.LegacyDec) math.Int {
	interestInt := interest.TruncateInt()
	return principal.Add(interestInt)
}

// GetInterestRateForDenom retrieves the annual interest rate for a specific denom from pool config.
func (k Keeper) GetInterestRateForDenom(ctx context.Context, pool *whaleswapv1.Pool, denom string) (math.LegacyDec, error) {
	if len(pool.Coins) != 2 {
		return math.LegacyDec{}, fmt.Errorf("invalid pool state: expected 2 coins")
	}
	rate := math.LegacyNewDec(0)
	var err error
	switch denom {
	case pool.Coins[0].Denom:
		if pool.InterestRateCoin1 != "" {
			rate, err = math.LegacyNewDecFromStr(pool.InterestRateCoin1)
			if err != nil {
				return math.LegacyDec{}, fmt.Errorf("invalid interest_rate_coin1: %w", err)
			}
		}
	case pool.Coins[1].Denom:
		if pool.InterestRateCoin2 != "" {
			rate, err = math.LegacyNewDecFromStr(pool.InterestRateCoin2)
			if err != nil {
				return math.LegacyDec{}, fmt.Errorf("invalid interest_rate_coin2: %w", err)
			}
		}
	default:
		return math.LegacyDec{}, fmt.Errorf("denom %s not in pool", denom)
	}
	return rate, nil
}
