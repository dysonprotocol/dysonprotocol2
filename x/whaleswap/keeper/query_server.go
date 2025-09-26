package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

var _ whaleswapv1.QueryServer = Keeper{}

func (k Keeper) Offer(ctx context.Context, req *whaleswapv1.QueryOfferRequest) (*whaleswapv1.QueryOfferResponse, error) {
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
	// Liquid-backing remainder: module solids minus (amm + escrowOffers + auctions + pfand)
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	actual := k.bank.SpendableCoins(ctx, moduleAddr)
	parts := sdk.NewCoins().Add(amm...).Add(escrowOffers...).Add(auctionCoins...).Add(pfand...)
	actualSolids := sdk.NewCoins()
	for _, c := range actual {
		if !k.isLiquidDenom(c.Denom) && c.Amount.IsPositive() {
			actualSolids = actualSolids.Add(c)
		}
	}
	liquidBacking := sdk.NewCoins()
	for _, c := range actualSolids {
		rem := c.Amount.Sub(parts.AmountOf(c.Denom))
		if rem.IsPositive() {
			liquidBacking = liquidBacking.Add(sdk.NewCoin(c.Denom, rem))
		}
	}
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
		EscrowedLiquidCoins:  liquidBacking,
		FeesEarned:           fees,
	}
	return &whaleswapv1.QueryMetricsResponse{Metrics: m}, nil
}
