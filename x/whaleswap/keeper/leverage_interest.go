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
	// New schema: pool.InterestRate must be exactly 2 in canonical order matching pool.Coins denoms.
	if len(pool.InterestRate) != 2 {
		return math.LegacyDec{}, fmt.Errorf("pool interest_rate must have exactly 2 entries")
	}
	switch denom {
	case pool.Coins[0].Denom:
		return pool.InterestRate.AmountOf(pool.Coins[0].Denom), nil
	case pool.Coins[1].Denom:
		return pool.InterestRate.AmountOf(pool.Coins[1].Denom), nil
	default:
		return math.LegacyDec{}, fmt.Errorf("denom %s not in pool", denom)
	}
}
