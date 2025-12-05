package v3

import (
	"context"

	"dysonprotocol.com/x/whaleswap/types"
)

// MigrateStore performs in-place store migrations from consensus version 2 to 3.
// The migration adds the AffiliateFeePct parameter with a default value of "0" (disabled).
func MigrateStore(
	ctx context.Context,
	getParams func(context.Context) types.Params,
	setParams func(context.Context, types.Params) error,
) error {
	// Get current params from store
	params := getParams(ctx)

	// Backfill AffiliateFeePct: empty string means old state, default to "0" (disabled)
	if params.AffiliateFeePct == "" {
		params.AffiliateFeePct = "0"
	}

	// Save updated params
	return setParams(ctx, params)
}
