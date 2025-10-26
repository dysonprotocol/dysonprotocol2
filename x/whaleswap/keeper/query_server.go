package keeper

import (
	"context"

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

	var positions []*whaleswapv1.LeveragePosition

	// Walk through all positions and filter by user
	_ = k.LeveragePositions.Walk(ctx, nil, func(_ uint64, pos whaleswapv1.LeveragePosition) (bool, error) {
		if pos.User != req.User {
			return false, nil
		}

		// Apply filters if specified
		if req.PoolId != 0 && pos.PoolId != req.PoolId {
			return false, nil
		}
		if req.BorrowedDenom != "" && pos.Borrowed.Denom != req.BorrowedDenom {
			return false, nil
		}
		if req.CollateralDenom != "" && pos.Collateral.Denom != req.CollateralDenom {
			return false, nil
		}

		positions = append(positions, &pos)
		return false, nil
	})

	// Apply pagination
	var pageResp *query.PageResponse
	if req.Pagination != nil {
		pageResp = &query.PageResponse{}
	}

	return &whaleswapv1.QueryPositionsByUserResponse{
		Positions:  positions,
		Pagination: pageResp,
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

	var positions []*whaleswapv1.LeveragePosition

	// Walk through all positions and filter by pool
	_ = k.LeveragePositions.Walk(ctx, nil, func(_ uint64, pos whaleswapv1.LeveragePosition) (bool, error) {
		if pos.PoolId != req.PoolId {
			return false, nil
		}
		positions = append(positions, &pos)
		return false, nil
	})

	// Apply pagination
	var pageResp *query.PageResponse
	if req.Pagination != nil {
		pageResp = &query.PageResponse{}
	}

	return &whaleswapv1.QueryPositionsByPoolResponse{
		Positions:  positions,
		Pagination: pageResp,
	}, nil
}
