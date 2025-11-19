package keeper

import (
	"context"
	"fmt"
	"time"

	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

const secondsPerYear = 365.25 * 24 * 60 * 60

func getAccruedInterestRemainder(pos *whaleswapv1.LeveragePosition) (math.LegacyDec, error) {
	// Validate the DecCoin remainder
	if pos.AccruedInterestRemainder.IsNegative() || pos.AccruedInterestRemainder.Amount.GTE(math.LegacyOneDec()) {
		return math.LegacyZeroDec(), fmt.Errorf("accrued_interest_remainder must be in [0,1)")
	}
	// Ensure denom matches borrowed denom
	if pos.AccruedInterestRemainder.Denom != pos.Borrowed.Denom {
		return math.LegacyZeroDec(), fmt.Errorf("accrued_interest_remainder denom %s does not match borrowed denom %s",
			pos.AccruedInterestRemainder.Denom, pos.Borrowed.Denom)
	}
	return pos.AccruedInterestRemainder.Amount, nil
}

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

// InterestStatus computes the total interest due (accrued + fresh) for a position
// without mutating state. It returns the decimal interest amount and elapsed
// seconds since the last settlement reference.
func (k Keeper) InterestStatus(ctx context.Context, pos *whaleswapv1.LeveragePosition) (math.LegacyDec, int64, error) {
	if pos == nil {
		return math.LegacyDec{}, 0, fmt.Errorf("position cannot be nil")
	}
	// Validate interest rate denom matches borrowed denom
	if pos.InterestRate.Denom != pos.Borrowed.Denom {
		return math.LegacyDec{}, 0, fmt.Errorf("interest_rate denom %s does not match borrowed denom %s",
			pos.InterestRate.Denom, pos.Borrowed.Denom)
	}

	rate := pos.InterestRate.Amount
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	remainder, err := getAccruedInterestRemainder(pos)
	if err != nil {
		return math.LegacyDec{}, 0, err
	}

	var baseTime *time.Time
	if pos.LastInterestSettlementTime != nil {
		baseTime = pos.LastInterestSettlementTime
	} else if pos.UpdatedTime != nil {
		baseTime = pos.UpdatedTime
	} else {
		bt := sdkCtx.BlockTime()
		baseTime = &bt
	}

	elapsed := sdkCtx.BlockTime().Sub(*baseTime).Seconds()
	if elapsed < 0 {
		elapsed = 0
	}

	fresh := math.LegacyZeroDec()
	if elapsed > 0 && pos.Borrowed.IsPositive() {
		if calc, calcErr := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed)); calcErr != nil {
			return math.LegacyDec{}, 0, calcErr
		} else {
			fresh = calc
		}
	}

	carry := math.LegacyNewDecFromInt(pos.AccruedInterest.Amount).Add(remainder)
	return carry.Add(fresh), int64(elapsed), nil
}

// SettleInterest flushes fresh interest into accrued_interest, updates the
// settlement timestamp, and returns both the decimal amount and integer coin
// (borrowed denom) owed.
func (k Keeper) SettleInterest(ctx context.Context, pos *whaleswapv1.LeveragePosition) (math.LegacyDec, sdk.Coin, error) {
	interestDec, _, err := k.InterestStatus(ctx, pos)
	if err != nil {
		return math.LegacyDec{}, sdk.Coin{}, err
	}

	interestInt := interestDec.TruncateInt()
	denom := pos.Borrowed.Denom
	pos.AccruedInterest = sdk.NewCoin(denom, interestInt)
	pos.AccruedInterestRemainder = sdk.NewDecCoinFromDec(denom, interestDec.Sub(math.LegacyNewDecFromInt(interestInt)))

	now := sdk.UnwrapSDKContext(ctx).BlockTime()
	pos.LastInterestSettlementTime = &now

	return interestDec, pos.AccruedInterest, nil
}

func resetInterestRemainderIfNoDebt(pos *whaleswapv1.LeveragePosition) {
	if pos == nil {
		return
	}
	if pos.Borrowed.IsZero() && pos.AccruedInterest.IsZero() {
		pos.AccruedInterestRemainder = sdk.NewDecCoinFromDec(pos.Borrowed.Denom, math.LegacyZeroDec())
	}
}

// ApplyInterestPayment consumes up to payment amount from AccruedInterest,
// updates TotalInterestPaid, and returns the interest coin actually consumed
// alongside any remaining payment coin that can be applied to principal.
func (k Keeper) ApplyInterestPayment(pos *whaleswapv1.LeveragePosition, payment sdk.Coin) (sdk.Coin, sdk.Coin, error) {
	if payment.IsNegative() {
		return sdk.Coin{}, sdk.Coin{}, fmt.Errorf("interest payment cannot be negative")
	}
	if payment.Denom != pos.Borrowed.Denom {
		return sdk.Coin{}, sdk.Coin{}, fmt.Errorf("payment denom %s does not match borrowed denom %s", payment.Denom, pos.Borrowed.Denom)
	}

	// Calculate how much of the payment goes to interest
	payableToInterest := payment
	if payment.IsGT(pos.AccruedInterest) {
		payableToInterest = pos.AccruedInterest
	}

	// Update total interest paid
	if pos.TotalInterestPaid.Denom == "" {
		pos.TotalInterestPaid = payableToInterest
	} else {
		pos.TotalInterestPaid = pos.TotalInterestPaid.Add(payableToInterest)
	}

	// Reduce accrued interest
	pos.AccruedInterest = pos.AccruedInterest.Sub(payableToInterest)

	// Calculate remainder for principal
	remainder := payment.Sub(payableToInterest)
	return payableToInterest, remainder, nil
}
