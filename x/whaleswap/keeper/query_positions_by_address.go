package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// PositionsByAddress lists all leverage positions for an address with optional filters.
//
// Semantics:
//   - Uses indexed queries on PositionsByAddressIndex with (address,status,position_id) keys.
//   - Returns all positions when status unspecified.
//   - Applies additional filters for pool_id, borrowed_denom, collateral_denom as specified.
//   - Supports pagination with consistent ordering by position ID.
//
// Validation:
//   - Request must be non-nil.
//   - Address must be non-empty.
//
// Returns:
//   - *whaleswapv1.QueryPositionsByAddressResponse with matching positions and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) PositionsByAddress(ctx context.Context, req *whaleswapv1.QueryPositionsByAddressRequest) (*whaleswapv1.QueryPositionsByAddressResponse, error) {
	if req == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "request cannot be nil")
	}
	if req.Address == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "address required")
	}

	// Validate that pool_id cannot be combined with borrowed_denom or collateral_denom
	if req.PoolId != 0 && (req.BorrowedDenom != "" || req.CollateralDenom != "") {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id cannot be combined with borrowed_denom or collateral_denom")
	}

	cachedPositions := make(map[uint64]*whaleswapv1.LeveragePosition)
	results, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		k.PositionsByAddressIndex,
		req.Pagination,
		func(_ collections.Triple[string, uint32, uint64], positionID uint64) (bool, error) {
			pos, err := k.LeveragePositions.Get(ctx, positionID)
			if err != nil {
				return false, err
			}
			if req.Status != whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED && pos.Status != req.Status {
				return false, nil
			}
			if req.PoolId != 0 {
				if pos.PoolId != req.PoolId {
					return false, nil
				}
			} else {
				if req.BorrowedDenom != "" && pos.Borrowed.Denom != req.BorrowedDenom {
					return false, nil
				}
				if req.CollateralDenom != "" && pos.Collateral.Denom != req.CollateralDenom {
					return false, nil
				}
			}
			cachedPositions[positionID] = &pos
			return true, nil
		},
		func(_ collections.Triple[string, uint32, uint64], positionID uint64) (*whaleswapv1.LeveragePosition, error) {
			if pos := cachedPositions[positionID]; pos != nil {
				return pos, nil
			}
			pos, err := k.LeveragePositions.Get(ctx, positionID)
			if err != nil {
				return nil, err
			}
			return &pos, nil
		},
		func(opt *query.CollectionsPaginateOptions[collections.Triple[string, uint32, uint64]]) {
			if req.Status != whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED {
				statusKey := positionStatusKey(req.Status)
				prefix := collections.TripleSuperPrefix[string, uint32, uint64](req.Address, statusKey)
				opt.Prefix = &prefix
			} else {
				prefix := collections.TriplePrefix[string, uint32, uint64](req.Address)
				opt.Prefix = &prefix
			}
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "positions by address pagination failed")
	}

	return &whaleswapv1.QueryPositionsByAddressResponse{
		Positions:  results,
		Pagination: pageRes,
	}, nil
}
