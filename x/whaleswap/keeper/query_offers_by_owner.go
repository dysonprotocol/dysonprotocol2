package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// OffersByOwner queries offers by owner address with optional status filter.
//
// Semantics:
//   - Returns offers owned by the specified address, optionally filtered by status.
//   - Uses indexed queries on OffersByOwnerStatus when both owner and status provided for optimal performance.
//   - Falls back to filtered scans over primary OffersMap for partial filters.
//   - Supports pagination with consistent ordering by offer ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Owner must be non-empty.
//   - Status must be valid ("open", "closed", "cancelled") if provided.
//
// Returns:
//   - *whaleswapv1.QueryOffersByOwnerResponse with matching offers and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) OffersByOwner(ctx context.Context, req *whaleswapv1.QueryOffersByOwnerRequest) (*whaleswapv1.QueryOffersByOwnerResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryOffersByOwnerRequest{}
	}
	owner := req.Owner
	status := req.Status
	if owner == "" {
		return nil, fmt.Errorf("owner required")
	}
	// If status provided, validate it and use owner+status index; else fall back to filtered scan
	if owner != "" && status != "" {
		if status != whaleswapv1.OfferStatusOpen && status != whaleswapv1.OfferStatusClosed && status != whaleswapv1.OfferStatusCancelled {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid status: %s", status)
		}
		results, pageRes, err := query.CollectionFilteredPaginate(
			ctx,
			k.OffersByOwnerStatus,
			req.Pagination,
			func(key collections.Triple[string, string, uint64], _ uint64) (bool, error) {
				k1, k2, _ := key.K1(), key.K2(), key.K3()
				return k1 == owner && k2 == status, nil
			},
			func(_ collections.Triple[string, string, uint64], value uint64) (*whaleswapv1.OfferData, error) {
				v, err := k.OffersMap.Get(ctx, value)
				if err != nil {
					return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", value)
				}
				return &v, nil
			},
		)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "paginate offers by owner/status failed: %s/%s", owner, status)
		}
		return &whaleswapv1.QueryOffersByOwnerResponse{Offers: results, Pagination: pageRes}, nil
	}
	// filtered scan fallback using predicate to avoid nil entries
	results, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		k.OffersMap,
		req.Pagination,
		func(_ uint64, value whaleswapv1.OfferData) (bool, error) {
			if owner != "" && value.Maker != owner {
				return false, nil
			}
			if status != "" && value.Status != status {
				return false, nil
			}
			return true, nil
		},
		func(_ uint64, value whaleswapv1.OfferData) (*whaleswapv1.OfferData, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate offers failed")
	}
	return &whaleswapv1.QueryOffersByOwnerResponse{Offers: results, Pagination: pageRes}, nil
}
