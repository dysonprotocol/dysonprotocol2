package v2

import (
	"context"

	"dysonprotocol.com/x/whaleswap/types"
)

// MigrateStore performs in-place store migrations from consensus version 1 to 2.
// The migration adds the ArbitrageMode parameter with a default value of AUTO.
func MigrateStore(
	ctx context.Context,
	getParams func(context.Context) types.Params,
	setParams func(context.Context, types.Params) error,
) error {
	// Get current params from store
	params := getParams(ctx)

	// Backfill ArbitrageMode: UNSPECIFIED (0) means old state, default to AUTO
	if params.ArbitrageMode == types.ArbitrageMode_ARBITRAGE_MODE_UNSPECIFIED {
		params.ArbitrageMode = types.ArbitrageMode_ARBITRAGE_MODE_AUTO
	}

	// Save updated params
	return setParams(ctx, params)
}
