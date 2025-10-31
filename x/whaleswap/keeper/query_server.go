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

// Metrics computes TradeMetrics and returns them
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
// PositionsByUser lists all positions for a user with optional filters
// This is the concrete implementation for the gRPC PositionsByUser query
func (k Keeper) PositionsByUser(ctx context.Context, req *whaleswapv1.QueryPositionsByUserRequest) (*whaleswapv1.QueryPositionsByUserResponse, error) {
	if req == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "request cannot be nil")
	}
	if req.User == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "user address required")
	}

	status := req.Status
	if status == whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED {
		status = whaleswapv1.PositionStatus_POSITION_STATUS_OPEN
	}
	statusKey := positionStatusKey(status)

	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.PositionsByUserIndex,
		req.Pagination,
		func(_ collections.Triple[string, uint32, uint64], positionID uint64) (*whaleswapv1.LeveragePosition, error) {
			pos, err := k.LeveragePositions.Get(ctx, positionID)
			if err != nil {
				return nil, err
			}
			if req.PoolId != 0 && pos.PoolId != req.PoolId {
				return nil, nil
			}
			if req.BorrowedDenom != "" && pos.Borrowed.Denom != req.BorrowedDenom {
				return nil, nil
			}
			if req.CollateralDenom != "" && pos.Collateral.Denom != req.CollateralDenom {
				return nil, nil
			}
			return &pos, nil
		},
		func(opt *query.CollectionsPaginateOptions[collections.Triple[string, uint32, uint64]]) {
			prefix := collections.TripleSuperPrefix[string, uint32, uint64](req.User, statusKey)
			opt.Prefix = &prefix
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "positions by user pagination failed")
	}

	return &whaleswapv1.QueryPositionsByUserResponse{
		Positions:  results,
		Pagination: pageRes,
	}, nil
}

// PositionsByPool lists all positions in a pool
// This is the concrete implementation for the gRPC PositionsByPool query
func (k Keeper) PositionsByPool(ctx context.Context, req *whaleswapv1.QueryPositionsByPoolRequest) (*whaleswapv1.QueryPositionsByPoolResponse, error) {
	if req == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "request cannot be nil")
	}
	if req.PoolId == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id required")
	}

	status := req.Status
	if status == whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED {
		status = whaleswapv1.PositionStatus_POSITION_STATUS_OPEN
	}
	statusKey := positionStatusKey(status)

	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.PositionsByPoolIndex,
		req.Pagination,
		func(_ collections.Triple[uint64, uint32, uint64], positionID uint64) (*whaleswapv1.LeveragePosition, error) {
			pos, err := k.LeveragePositions.Get(ctx, positionID)
			if err != nil {
				return nil, err
			}
			return &pos, nil
		},
		func(opt *query.CollectionsPaginateOptions[collections.Triple[uint64, uint32, uint64]]) {
			prefix := collections.TripleSuperPrefix[uint64, uint32, uint64](req.PoolId, statusKey)
			opt.Prefix = &prefix
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
