package types

import (
	"encoding/json"
	"fmt"

	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// DefaultGenesis returns the default genesis state for the module.
func DefaultGenesis() json.RawMessage {
	// Create a default genesis state and marshal it to JSON
	state := NewGenesisState()
	cdc := codec.NewProtoCodec(cdctypes.NewInterfaceRegistry())
	return cdc.MustMarshalJSON(state)
}

// ValidateGenesis performs complete genesis state validation
func ValidateGenesis(gs *GenesisState) error {
	if gs == nil {
		return fmt.Errorf("genesis state cannot be nil")
	}

	// Allow NextTaskId to be 0 to indicate "unset"; keeper will default it.

	// Validate params
	if gs.Params == nil {
		return fmt.Errorf("params cannot be nil")
	}
	if err := gs.Params.Validate(); err != nil {
		return fmt.Errorf("invalid module parameters: %w", err)
	}

	// Allow NextSubscriptionId to be 0 to indicate "unset"; keeper will default it.

	// Validate tasks
	taskIDs := make(map[uint64]bool)
	for _, task := range gs.Tasks {
		if task.TaskId == 0 {
			return fmt.Errorf("task ID cannot be 0")
		}
		if _, exists := taskIDs[task.TaskId]; exists {
			return fmt.Errorf("duplicate task ID: %d", task.TaskId)
		}
		taskIDs[task.TaskId] = true

		if task.Creator == "" {
			return fmt.Errorf("task creator cannot be empty")
		}
		if _, err := sdk.AccAddressFromBech32(task.Creator); err != nil {
			return fmt.Errorf("invalid task creator address %s: %v", task.Creator, err)
		}
		if task.ScheduledTimestamp <= 0 {
			return fmt.Errorf("scheduled timestamp must be positive")
		}
		if task.ExpiryTimestamp <= task.ScheduledTimestamp {
			return fmt.Errorf("expiry timestamp must be after scheduled timestamp")
		}
		if task.TaskGasLimit == 0 {
			return fmt.Errorf("gas limit must be positive")
		}
		if !task.TaskGasPrice.IsPositive() {
			return fmt.Errorf("gas price must be positive")
		}
		if len(task.Msgs) == 0 {
			return fmt.Errorf("task must have at least one message")
		}
	}

	// Validate subscriptions
	subIDs := make(map[uint64]bool)
	for _, sub := range gs.Subscriptions {
		if sub.SubscriptionId == 0 {
			return fmt.Errorf("subscription ID cannot be 0")
		}
		if _, exists := subIDs[sub.SubscriptionId]; exists {
			return fmt.Errorf("duplicate subscription ID: %d", sub.SubscriptionId)
		}
		subIDs[sub.SubscriptionId] = true

		if sub.Creator == "" {
			return fmt.Errorf("subscription creator cannot be empty")
		}
		if _, err := sdk.AccAddressFromBech32(sub.Creator); err != nil {
			return fmt.Errorf("invalid subscription creator address %s: %v", sub.Creator, err)
		}
		if sub.ScriptAddress == "" {
			return fmt.Errorf("subscription script address cannot be empty")
		}
		if _, err := sdk.AccAddressFromBech32(sub.ScriptAddress); err != nil {
			return fmt.Errorf("invalid subscription script address %s: %v", sub.ScriptAddress, err)
		}
		if sub.TaskGasLimit == 0 {
			return fmt.Errorf("subscription task gas limit must be positive")
		}
		if !sub.TaskGasFee.IsValid() {
			return fmt.Errorf("invalid subscription task gas fee")
		}
		if sub.ExpiryTimestamp <= 0 {
			return fmt.Errorf("subscription expiry timestamp must be positive")
		}
	}

	return nil
}
