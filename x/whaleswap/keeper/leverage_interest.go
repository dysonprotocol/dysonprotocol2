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
	if len(pos.InterestRate) != 2 {
		return math.LegacyDec{}, 0, fmt.Errorf("position interest_rate must have exactly 2 entries")
	}

	rate := pos.InterestRate.AmountOf(pos.Borrowed.Denom)
	sdkCtx := sdk.UnwrapSDKContext(ctx)

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
	var err error
	if elapsed > 0 && pos.Borrowed.Amount.IsPositive() {
		fresh, err = k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
		if err != nil {
			return math.LegacyDec{}, 0, err
		}
	}

	carry := math.LegacyNewDecFromInt(pos.AccruedInterest.Amount)
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

	now := sdk.UnwrapSDKContext(ctx).BlockTime()
	pos.LastInterestSettlementTime = &now

	return interestDec, pos.AccruedInterest, nil
}

// ApplyInterestPayment consumes up to payment amount from AccruedInterest,
// updates TotalInterestPaid, and returns the interest coin actually consumed
// alongside any remaining payment that can be applied to principal.
func (k Keeper) ApplyInterestPayment(pos *whaleswapv1.LeveragePosition, payment math.Int) (sdk.Coin, math.Int, error) {
	if payment.IsNegative() {
		return sdk.Coin{}, math.Int{}, fmt.Errorf("interest payment cannot be negative")
	}
	denom := pos.Borrowed.Denom
	due := pos.AccruedInterest.Amount

	payable := payment
	if payable.GT(due) {
		payable = due
	}

	if pos.TotalInterestPaid.Denom == "" {
		pos.TotalInterestPaid = sdk.NewCoin(denom, payable)
	} else {
		pos.TotalInterestPaid.Amount = pos.TotalInterestPaid.Amount.Add(payable)
	}

	pos.AccruedInterest.Amount = due.Sub(payable)

	interestPaid := sdk.NewCoin(denom, payable)
	remainder := payment.Sub(payable)
	return interestPaid, remainder, nil
}
