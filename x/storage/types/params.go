package types

import (
	"fmt"

	"cosmossdk.io/math"
)

// DefaultMaxStorageSize is the default maximum storage size in bytes (1KB)
const DefaultMaxStorageSize = uint64(50 * 1024) // 50KB

// MinMaxStorageSize is the minimum allowed value for max storage size
const MinMaxStorageSize = uint64(1024) // 1KB

// MaxMaxStorageSize is the maximum allowed value for max storage size
const MaxMaxStorageSize = uint64(100 * 1024 * 1024) // 100MB

// DefaultStorageStakeMultiple is the default stake requirement multiplier (0 udys per byte)
const DefaultStorageStakeMultiple = "0"

// NewParams creates a new Params instance with given values
func NewParams(maxStorageSize uint64, storageStakeMultiple string) Params {
	return Params{
		MaxStorageSize:       maxStorageSize,
		StorageStakeMultiple: storageStakeMultiple,
	}
}

// DefaultParams returns a default set of parameters
func DefaultParams() Params {
	return NewParams(DefaultMaxStorageSize, DefaultStorageStakeMultiple)
}

// Validate validates the params
func (p Params) Validate() error {
	if err := validateMaxStorageSize(p.MaxStorageSize); err != nil {
		return err
	}
	if err := validateStorageStakeMultiple(p.StorageStakeMultiple); err != nil {
		return err
	}
	return nil
}

func validateMaxStorageSize(maxStorageSize uint64) error {
	if maxStorageSize < MinMaxStorageSize {
		return fmt.Errorf("max storage size must be at least %d bytes, got: %d", MinMaxStorageSize, maxStorageSize)
	}

	if maxStorageSize > MaxMaxStorageSize {
		return fmt.Errorf("max storage size must be at most %d bytes, got: %d", MaxMaxStorageSize, maxStorageSize)
	}

	return nil
}

func validateStorageStakeMultiple(storageStakeMultiple string) error {
	dec, err := math.LegacyNewDecFromStr(storageStakeMultiple)
	if err != nil {
		return fmt.Errorf("invalid storage_stake_multiple: %s, must be a valid decimal number", storageStakeMultiple)
	}
	if dec.IsNegative() {
		return fmt.Errorf("storage_stake_multiple must not be negative, got: %s", storageStakeMultiple)
	}
	return nil
}
