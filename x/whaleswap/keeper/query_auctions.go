package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

// Auction queries a single auction by ID.
//
// Semantics:
//   - Retrieves complete auction data including escrow details, bids, and NFT markers.
//   - Returns the full AuctionRecord structure with all metadata and current state.
//
// Validation:
//   - Request must be non-nil.
//   - AuctionId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryAuctionResponse containing the auction data.
//
// Errors are returned on invalid request parameters or when auction not found; no panics.
func (k Keeper) Auction(ctx context.Context, req *whaleswapv1.QueryAuctionRequest) (*whaleswapv1.QueryAuctionResponse, error) {
	if req == nil || req.AuctionId == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "auction_id required")
	}
	rec, err := k.AuctionsMap.Get(ctx, req.AuctionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "auction not found: %d", req.AuctionId)
	}
	return &whaleswapv1.QueryAuctionResponse{Auction: &rec}, nil
}

// Auctions provides unified auction listing with optional denom filters and pagination.
//
// Semantics:
//   - Supports multiple query patterns based on provided filters:
//     * Both sell_denom and bid_denom: uses AuctionsBySellBid index for efficient pair filtering
//     * Only sell_denom: uses AuctionsBySellBid with prefix scan for sell-side filtering
//     * Only bid_denom: uses AuctionsByBidSell index for bid-side filtering
//     * No filters: direct pagination over primary AuctionsMap
//   - Applies appropriate prefix filtering to optimize index usage.
//   - Supports pagination with consistent ordering by auction ID.
//
// Validation:
//   - Request can be nil (defaults handled internally).
//   - Denom filters are optional but must be valid denomination strings if provided.
//
// Returns:
//   - *whaleswapv1.QueryAuctionsResponse with matching auctions and pagination metadata.
//
// Errors are returned on invalid parameters or pagination failures; no panics.
func (k Keeper) Auctions(ctx context.Context, req *whaleswapv1.QueryAuctionsRequest) (*whaleswapv1.QueryAuctionsResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryAuctionsRequest{}
	}
	sell := req.SellDenom
	bid := req.BidDenom

	// Choose index based on provided filters
	switch {
	case sell != "" && bid != "":
		// Use (sell,bid,auction_id) index and paginate
		results, pageRes, err := query.CollectionPaginate(
			ctx,
			k.AuctionsBySellBid,
			req.Pagination,
			func(key collections.Triple[string, string, uint64], value uint64) (*whaleswapv1.AuctionRecord, error) {
				// filter by superprefix via key; CollectionPaginate already ranges over the map so we filter strictly
				if k1, k2, _ := key.K1(), key.K2(), key.K3(); k1 == sell && k2 == bid {
					rec, err := k.AuctionsMap.Get(ctx, value)
					if err != nil {
						return nil, err
					}
					return &rec, nil
				}
				return nil, nil
			},
			// Prefix by (sell,bid) to ensure stable pagination and valid next_key
			func(opt *query.CollectionsPaginateOptions[collections.Triple[string, string, uint64]]) {
				p := collections.TripleSuperPrefix[string, string, uint64](sell, bid)
				opt.Prefix = &p
			},
		)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "Auctions query (sell=[%s],bid=[%s]) failed", sell, bid)
		}
		return &whaleswapv1.QueryAuctionsResponse{Auctions: results, Pagination: pageRes}, nil

	case sell != "":
		// Use (sell,*,auction_id) scan
		results, pageRes, err := query.CollectionPaginate(
			ctx,
			k.AuctionsBySellBid,
			req.Pagination,
			func(key collections.Triple[string, string, uint64], value uint64) (*whaleswapv1.AuctionRecord, error) {
				if k1, _, _ := key.K1(), key.K2(), key.K3(); k1 == sell {
					rec, err := k.AuctionsMap.Get(ctx, value)
					if err != nil {
						return nil, err
					}
					if bid != "" && rec.BidDenom != bid {
						return nil, nil
					}
					return &rec, nil
				}
				return nil, nil
			},
			// Prefix by sell to iterate only that subset
			func(opt *query.CollectionsPaginateOptions[collections.Triple[string, string, uint64]]) {
				p := collections.TriplePrefix[string, string, uint64](sell)
				opt.Prefix = &p
			},
		)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "Auctions query (sell=[%s]) failed", sell)
		}
		return &whaleswapv1.QueryAuctionsResponse{Auctions: results, Pagination: pageRes}, nil

	case bid != "":
		// Use (bid,*,auction_id) index
		results, pageRes, err := query.CollectionPaginate(
			ctx,
			k.AuctionsByBidSell,
			req.Pagination,
			func(key collections.Triple[string, string, uint64], value uint64) (*whaleswapv1.AuctionRecord, error) {
				if k1, _, _ := key.K1(), key.K2(), key.K3(); k1 == bid {
					rec, err := k.AuctionsMap.Get(ctx, value)
					if err != nil {
						return nil, err
					}
					if sell != "" && rec.Sell.Denom != sell {
						return nil, nil
					}
					return &rec, nil
				}
				return nil, nil
			},
			// Prefix by bid to iterate only that subset
			func(opt *query.CollectionsPaginateOptions[collections.Triple[string, string, uint64]]) {
				p := collections.TriplePrefix[string, string, uint64](bid)
				opt.Prefix = &p
			},
		)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "Auctions query (bid=[%s]) failed", bid)
		}
		return &whaleswapv1.QueryAuctionsResponse{Auctions: results, Pagination: pageRes}, nil
	}

	// No filters: paginate primary map
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.AuctionsMap,
		req.Pagination,
		func(key uint64, value whaleswapv1.AuctionRecord) (*whaleswapv1.AuctionRecord, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "Auctions query failed")
	}
	return &whaleswapv1.QueryAuctionsResponse{Auctions: results, Pagination: pageRes}, nil
}
