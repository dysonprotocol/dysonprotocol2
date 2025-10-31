package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

// UpdateParams updates module parameters. Authority-only.
//
// Semantics:
//   - Authority check: verifies msg.Authority matches the module's configured authority.
//   - Parameter validation: validates all parameter constraints (pfand amounts, time durations,
//     percentage bounds, block delays).
//   - State update: persists validated parameters to the module's parameter store.
//
// Validation:
//   - Authority must match the module's configured authority address.
//   - Parameters must pass Params.Validate() which checks:
//     - PfandPerOffer denom set when amount > 0
//     - ValuationPeriod > 0
//     - BidTimeout > 0
//     - ValuationFeePct in [0,1) if set
//     - MinimumBidPercentIncrease in [0,1) if set
//     - BlockDelayBeforeClose > 0
//     - BlockDelayBeforeLiquidation > 0
//
// Returns:
//   - *whaleswapv1.MsgUpdateParamsResponse (empty) on success.
//
// Errors are returned on authority mismatch, parameter validation failures,
// or parameter persistence failures; no panics.
func (k Keeper) UpdateParams(ctx context.Context, msg *whaleswapv1.MsgUpdateParams) (*whaleswapv1.MsgUpdateParamsResponse, error) {
	if k.authority != msg.Authority {
		return nil, whaleswapv1.ErrInvalidAuthority
	}
	if err := k.SetParams(ctx, msg.Params); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set params")
	}
	return &whaleswapv1.MsgUpdateParamsResponse{}, nil
}
