package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// PoolsByOwner queries pools where the owner holds non-zero shares balance.
//
// Semantics:
//   - Returns pools where the specified owner has a positive balance of pool shares.
//   - Uses bank module balance checks for each pool's shares denom.
//   - Falls back to filtered scan when no dedicated index exists.
//   - Results ordered by pool ID ascending.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Owner must be non-empty and a valid address.
//
// Returns:
//   - *whaleswapv1.QueryPoolsByOwnerResponse with matching pools and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) PoolsByOwner(ctx context.Context, req *whaleswapv1.QueryPoolsByOwnerRequest) (*whaleswapv1.QueryPoolsByOwnerResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolsByOwnerRequest{}
	}
	if req.Owner == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "owner required")
	}
	addrBz, err := k.accKeeper.AddressCodec().StringToBytes(req.Owner)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid owner: %s", req.Owner)
	}
	results, pageRes, perr := query.CollectionFilteredPaginate(ctx, k.PoolsMap, req.Pagination,
		func(key uint64, value whaleswapv1.Pool) (bool, error) {
			bal := k.bank.GetBalance(ctx, addrBz, value.SharesDenom).Amount
			return bal.IsPositive(), nil
		},
		func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
			v := value
			return &v, nil
		},
	)
	if perr != nil {
		return nil, cosmossdkerrors.Wrap(perr, "PoolsByOwner paginate failed")
	}
	return &whaleswapv1.QueryPoolsByOwnerResponse{Pools: results, Pagination: pageRes}, nil
}
