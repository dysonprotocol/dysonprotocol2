package types

import (
	"fmt"
	"time"

	sdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// TaskStatus constants define the possible states of a task
const (
	TaskStatus_SCHEDULED = "SCHEDULED"
	TaskStatus_PENDING   = "PENDING"
	TaskStatus_DONE      = "DONE"
	TaskStatus_FAILED    = "FAILED"
	TaskStatus_EXPIRED   = "EXPIRED"
)

// NewGenesisState creates a new GenesisState object
func NewGenesisState() *GenesisState {
	params := DefaultParams()
	return &GenesisState{
		Tasks:              []*Task{},
		NextTaskId:         1,
		NextSubscriptionId: 1,
		Params:             &params,
	}
}

// DefaultParams returns default parameters for the crontask module.
// Uses sdk.DefaultBondDenom which is set at genesis init time.
func DefaultParams() Params {
	return Params{
		BlockGasLimit:    3000000, // 3M gas limit per block for tasks
		ExpiryLimit:      86400,   // 24 hours in seconds
		MaxScheduledTime: 86400,   // 24 hours in seconds
		CleanUpTime:      86400,   // 24 hours in seconds
		// MaxSubscriptionDuration is a time.Duration (nanoseconds). Use 24 hours.
		MaxSubscriptionDuration: 24 * time.Hour,
		MinStakePerSubscription: sdk.Coin{Denom: sdk.DefaultBondDenom, Amount: sdkmath.NewInt(1000)},
	}
}

// Validate checks that the parameters have valid values.
func (p Params) Validate() error {
	if p.BlockGasLimit == 0 {
		return fmt.Errorf("block gas limit must be positive: %d", p.BlockGasLimit)
	}

	if p.ExpiryLimit <= 0 {
		return fmt.Errorf("expiry limit must be positive: %d", p.ExpiryLimit)
	}

	if p.MaxScheduledTime <= 0 {
		return fmt.Errorf("max scheduled time must be positive: %d", p.MaxScheduledTime)
	}

	if p.CleanUpTime < 0 {
		return fmt.Errorf("clean up time cannot be negative: %d", p.CleanUpTime)
	}

	if p.MaxSubscriptionDuration <= 0 {
		return fmt.Errorf("max subscription duration must be positive: %d", p.MaxSubscriptionDuration)
	}

	return nil
}
