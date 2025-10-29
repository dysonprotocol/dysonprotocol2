package keeper

import (
	"fmt"

	"cosmossdk.io/math"
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
