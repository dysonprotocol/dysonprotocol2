package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	cosmossdk_math "cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// AuctionsByPairPriceRange queries auctions for a pair whose effective price falls within bounds.
//
// Semantics:
//   - Filters auctions by sell/bid denom pair using AuctionsBySellBid index.
//   - Applies prefix filtering to iterate only auctions for the specified pair.
//   - Price filtering is placeholder (marked as TODO in implementation).
//   - Supports pagination with consistent ordering by auction ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Both sell_denom and bid_denom must be non-empty.
//   - Min/max prices must be valid decimal strings if provided.
//
// Returns:
//   - *whaleswapv1.QueryAuctionsByPairPriceRangeResponse with matching auctions and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) AuctionsByPairPriceRange(ctx context.Context, req *whaleswapv1.QueryAuctionsByPairPriceRangeRequest) (*whaleswapv1.QueryAuctionsByPairPriceRangeResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryAuctionsByPairPriceRangeRequest{}
	}
	if req.SellDenom == "" || req.BidDenom == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "sell_denom and bid_denom required")
	}
	var minDec, maxDec cosmossdk_math.LegacyDec
	var err error
	if req.MinPrice != "" {
		minDec, err = cosmossdk_math.LegacyNewDecFromStr(req.MinPrice)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid min_price: %s", req.MinPrice)
		}
	}
	if req.MaxPrice != "" {
		maxDec, err = cosmossdk_math.LegacyNewDecFromStr(req.MaxPrice)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid max_price: %s", req.MaxPrice)
		}
	}
	// Iterate over index by (sell,bid,auction_id) for a tight candidate set
	results, pageRes, perr := query.CollectionFilteredPaginate(
		ctx,
		k.AuctionsBySellBid,
		req.Pagination,
		func(key collections.Triple[string, string, uint64], id uint64) (bool, error) {
			k1, k2, _ := key.K1(), key.K2(), key.K3()
			return k1 == req.SellDenom && k2 == req.BidDenom, nil
		},
		func(key collections.Triple[string, string, uint64], id uint64) (*whaleswapv1.AuctionRecord, error) {
			rec, err := k.AuctionsMap.Get(ctx, id)
			if err != nil {
				return nil, err
			}
			// Compute effective price = bid-per-sell based on current valuation or bid and redeemable sell amount.
			// Placeholder logic until valuation/bid fields are modeled: skip filtering.
			_ = minDec
			_ = maxDec
			v := rec
			return &v, nil
		},
		// Prefix by (sell,bid) to iterate only that subset and ensure stable next_key
		func(opt *query.CollectionsPaginateOptions[collections.Triple[string, string, uint64]]) {
			p := collections.TripleSuperPrefix[string, string, uint64](req.SellDenom, req.BidDenom)
			opt.Prefix = &p
		},
	)
	if perr != nil {
		return nil, cosmossdkerrors.Wrap(perr, "AuctionsByPairPriceRange paginate failed")
	}
	return &whaleswapv1.QueryAuctionsByPairPriceRangeResponse{Auctions: results, Pagination: pageRes}, nil
}
