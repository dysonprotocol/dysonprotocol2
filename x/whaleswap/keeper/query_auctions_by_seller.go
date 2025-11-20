package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// AuctionsBySeller queries auctions created by a specific seller address.
//
// Semantics:
//   - Returns auctions where the specified address appears as the seller.
//   - Uses filtered pagination over primary AuctionsMap (no dedicated index assumed).
//   - Results ordered by auction ID ascending.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Seller address must be non-empty.
//
// Returns:
//   - *whaleswapv1.QueryAuctionsBySellerResponse with matching auctions and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) AuctionsBySeller(ctx context.Context, req *whaleswapv1.QueryAuctionsBySellerRequest) (*whaleswapv1.QueryAuctionsBySellerResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryAuctionsBySellerRequest{}
	}
	if req.Seller == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "seller required")
	}
	results, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		k.AuctionsMap,
		req.Pagination,
		func(key uint64, value whaleswapv1.AuctionRecord) (bool, error) {
			return value.Seller == req.Seller, nil
		},
		func(key uint64, value whaleswapv1.AuctionRecord) (*whaleswapv1.AuctionRecord, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AuctionsBySeller paginate failed")
	}
	return &whaleswapv1.QueryAuctionsBySellerResponse{Auctions: results, Pagination: pageRes}, nil
}

