package keeper

import (
	"context"
)

// GetNextTaskID gets and increments the global task ID counter
func (k Keeper) GetNextTaskID(ctx context.Context) (uint64, error) {
	return k.NextTaskID.Next(ctx)
}
