package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// PoolBySharesDenom queries the pool that mints a specific shares denom.
//
// Semantics:
//   - Scans pools to find the one with matching shares_denom.
//   - Returns the first (and should be only) matching pool.
//   - Uses unpaginated scan since shares denoms are expected to be unique.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - SharesDenom must be non-empty.
//
// Returns:
//   - *whaleswapv1.QueryPoolBySharesDenomResponse with the matching pool.
//
// Errors are returned on invalid parameters, pagination failures, or when no matching pool found; no panics.
func (k Keeper) PoolBySharesDenom(ctx context.Context, req *whaleswapv1.QueryPoolBySharesDenomRequest) (*whaleswapv1.QueryPoolBySharesDenomResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolBySharesDenomRequest{}
	}
	if req.SharesDenom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "shares_denom required")
	}
	var matched *whaleswapv1.Pool
	iter, err := k.PoolsMap.Iterate(ctx, nil)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "PoolBySharesDenom iterate failed")
	}
	defer iter.Close()
	for ; iter.Valid(); iter.Next() {
		value, vErr := iter.Value()
		if vErr != nil {
			return nil, cosmossdkerrors.Wrap(vErr, "PoolBySharesDenom iterate value failed")
		}
		if value.SharesDenom == req.SharesDenom {
			v := value
			matched = &v
			break
		}
	}
	if matched == nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "pool not found for shares denom %s", req.SharesDenom)
	}
	return &whaleswapv1.QueryPoolBySharesDenomResponse{Pool: matched}, nil
}
