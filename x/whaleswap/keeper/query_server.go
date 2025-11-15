package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

var _ whaleswapv1.QueryServer = Keeper{}

// Offer queries a single offer by ID.
//
// Semantics:
//   - Retrieves offer data from the offers map using the provided offer_id.
//   - Returns the complete OfferData including maker, amounts, status, and timestamps.
//
// Validation:
//   - Request must be non-nil.
//   - OfferId must be positive.
//
// Returns:
//   - *whaleswapv1.QueryOfferResponse containing the offer data.
//
// Errors are returned on invalid request parameters or when offer not found; no panics.
func (k Keeper) Offer(ctx context.Context, req *whaleswapv1.QueryOfferRequest) (*whaleswapv1.QueryOfferResponse, error) {
	if req == nil || req.OfferId == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "offer_id required")
	}
	offer, err := k.OffersMap.Get(ctx, req.OfferId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "offer not found: %d", req.OfferId)
	}
	return &whaleswapv1.QueryOfferResponse{Offer: &offer}, nil
}

// Metrics computes comprehensive module metrics including escrow balances and trade statistics.
//
// Semantics:
//   - Aggregates escrow balances: AMM pool reserves, offer-locked coins, PFAND requirements.
//   - Counts auctions across all records by summing sell amounts.
//   - Calculates total fees earned across all pools.
//   - Counts total trades by iterating the trades map.
//   - Returns consolidated TradeMetrics for monitoring and invariants checking.
//
// Validation:
//   - No validation required (empty request accepted).
//
// Returns:
//   - *whaleswapv1.QueryMetricsResponse with complete TradeMetrics breakdown.
//
// Errors are returned on tally computation failures; no panics.
func (k Keeper) Metrics(ctx context.Context, _ *whaleswapv1.QueryMetricsRequest) (*whaleswapv1.QueryMetricsResponse, error) {
	amm, err := k.tallyAMMReserves(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "tally amm")
	}
	escrowOffers, err := k.tallyEscrowRequired(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "tally escrow offers")
	}
	pfand, err := k.tallyPfandRequired(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "tally pfand")
	}
	// Auctions: sum sell across all auctions
	auctionCoins := sdk.NewCoins()
	_ = k.AuctionsMap.Walk(ctx, nil, func(_ uint64, a whaleswapv1.AuctionRecord) (bool, error) {
		auctionCoins = auctionCoins.Add(a.Sell)
		return false, nil
	})
	// Fees earned: sum across pools
	fees := sdk.NewCoins()
	_ = k.PoolsMap.Walk(ctx, nil, func(_ uint64, p whaleswapv1.Pool) (bool, error) {
		if len(p.FeesEarned) > 0 {
			fees = fees.Add(p.FeesEarned...)
		}
		return false, nil
	})
	// num_trades by iterating trades map (sequence may include gaps)
	var numTrades uint64
	_ = k.TradesMap.Walk(ctx, nil, func(_ uint64, _ whaleswapv1.Trade) (bool, error) {
		numTrades++
		return false, nil
	})
	m := &whaleswapv1.TradeMetrics{
		NumTrades:            numTrades,
		EscrowedPoolCoins:    amm,
		EscrowedOfferCoins:   escrowOffers,
		EscrowedPfand:        pfand,
		EscrowedAuctionCoins: auctionCoins,
		FeesEarned:           fees,
	}
	return &whaleswapv1.QueryMetricsResponse{Metrics: m}, nil
}

// Leverage Query Handlers

// Position: see query_leverage_health.go

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
