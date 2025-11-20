package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// PositionsByPool lists all leverage positions in a specific pool with optional status filter.
//
// Semantics:
//   - Uses indexed queries on PositionsByPoolIndex with (pool_id,status,position_id) keys.
//   - Returns all positions when status unspecified.
//   - Filters positions by the specified pool_id.
//   - Supports pagination with consistent ordering by position ID.
//
// Validation:
//   - Request must be non-nil.
//   - PoolId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryPositionsByPoolResponse with matching positions and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) PositionsByPool(ctx context.Context, req *whaleswapv1.QueryPositionsByPoolRequest) (*whaleswapv1.QueryPositionsByPoolResponse, error) {
	if req == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "request cannot be nil")
	}
	if req.PoolId == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id required")
	}

	cachedPositions := make(map[uint64]*whaleswapv1.LeveragePosition)
	results, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		k.PositionsByPoolIndex,
		req.Pagination,
		func(_ collections.Triple[uint64, uint32, uint64], positionID uint64) (bool, error) {
			pos, err := k.LeveragePositions.Get(ctx, positionID)
			if err != nil {
				return false, err
			}
			if req.Status != whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED && pos.Status != req.Status {
				return false, nil
			}
			cachedPositions[positionID] = &pos
			return true, nil
		},
		func(_ collections.Triple[uint64, uint32, uint64], positionID uint64) (*whaleswapv1.LeveragePosition, error) {
			if pos := cachedPositions[positionID]; pos != nil {
				return pos, nil
			}
			pos, err := k.LeveragePositions.Get(ctx, positionID)
			if err != nil {
				return nil, err
			}
			return &pos, nil
		},
		func(opt *query.CollectionsPaginateOptions[collections.Triple[uint64, uint32, uint64]]) {
			if req.Status != whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED {
				statusKey := positionStatusKey(req.Status)
				prefix := collections.TripleSuperPrefix[uint64, uint32, uint64](req.PoolId, statusKey)
				opt.Prefix = &prefix
			} else {
				prefix := collections.TriplePrefix[uint64, uint32, uint64](req.PoolId)
				opt.Prefix = &prefix
			}
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "positions by pool pagination failed")
	}

	return &whaleswapv1.QueryPositionsByPoolResponse{
		Positions:  results,
		Pagination: pageRes,
	}, nil
}
