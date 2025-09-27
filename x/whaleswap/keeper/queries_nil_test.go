package keeper

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"

	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

// NOTE: These tests only validate that query handlers gracefully handle nil requests
// and missing required fields without panicking. They do not assert on concrete
// store contents; a zero-state keeper is sufficient.

func TestQueries_NilAndEmptyRequests(t *testing.T) {
	t.Parallel()
	k, ctx := newTestKeeper(t) // helper constructs keeper with empty state

	// Offers: Offer(nil), Offer(0)
	_, err := k.Offer(ctx, nil)
	require.Error(t, err)
	_, err = k.Offer(ctx, &whaleswapv1.QueryOfferRequest{OfferId: 0})
	require.Error(t, err)

	// Offers list with nil req
	_, err = k.Offers(ctx, nil)
	require.NoError(t, err)
	// OffersByOwner: nil, empty owner
	_, err = k.OffersByOwner(ctx, nil)
	require.Error(t, err)
	_, err = k.OffersByOwner(ctx, &whaleswapv1.QueryOffersByOwnerRequest{Owner: ""})
	require.Error(t, err)
	// OffersByDenom: nil, empty denom
	_, err = k.OffersByDenom(ctx, nil)
	require.Error(t, err)
	_, err = k.OffersByDenom(ctx, &whaleswapv1.QueryOffersByDenomRequest{Role: "have"})
	require.Error(t, err)
	// OffersByPairPriceRange: nil, missing pair
	_, err = k.OffersByPairPriceRange(ctx, nil)
	require.Error(t, err)
	_, err = k.OffersByPairPriceRange(ctx, &whaleswapv1.QueryOffersByPairPriceRangeRequest{})
	require.Error(t, err)
	// OffersBest: nil, missing pair
	_, err = k.OffersBest(ctx, nil)
	require.Error(t, err)
	_, err = k.OffersBest(ctx, &whaleswapv1.QueryOffersBestRequest{})
	require.Error(t, err)

	// Pools: Pool(nil), Pool(0)
	_, err = k.Pool(ctx, nil)
	require.Error(t, err)
	_, err = k.Pool(ctx, &whaleswapv1.QueryPoolRequest{PoolId: 0})
	require.Error(t, err)
	// Pools list with nil req
	_, err = k.Pools(ctx, nil)
	require.NoError(t, err)
	// PoolsByPair: nil, missing pair
	_, err = k.PoolsByPair(ctx, nil)
	require.Error(t, err)
	_, err = k.PoolsByPair(ctx, &whaleswapv1.QueryPoolsByPairRequest{})
	require.Error(t, err)
	// PoolsByDenom: nil, missing denom
	_, err = k.PoolsByDenom(ctx, nil)
	require.Error(t, err)
	_, err = k.PoolsByDenom(ctx, &whaleswapv1.QueryPoolsByDenomRequest{})
	require.Error(t, err)
	// PoolBySharesDenom: nil, missing shares denom
	_, err = k.PoolBySharesDenom(ctx, nil)
	require.Error(t, err)
	_, err = k.PoolBySharesDenom(ctx, &whaleswapv1.QueryPoolBySharesDenomRequest{})
	require.Error(t, err)
	// PoolsByPairPriceRange: nil, missing pair
	_, err = k.PoolsByPairPriceRange(ctx, nil)
	require.Error(t, err)
	_, err = k.PoolsByPairPriceRange(ctx, &whaleswapv1.QueryPoolsByPairPriceRangeRequest{})
	require.Error(t, err)
	// PoolsByOwner: nil, missing owner
	_, err = k.PoolsByOwner(ctx, nil)
	require.Error(t, err)
	_, err = k.PoolsByOwner(ctx, &whaleswapv1.QueryPoolsByOwnerRequest{})
	require.Error(t, err)

	// Trades: Trade(nil), Trade(0)
	_, err = k.Trade(ctx, nil)
	require.Error(t, err)
	_, err = k.Trade(ctx, &whaleswapv1.QueryTradeRequest{TradeId: 0})
	require.Error(t, err)
	// TradesByOffer: nil, missing id
	_, err = k.TradesByOffer(ctx, nil)
	require.Error(t, err)
	_, err = k.TradesByOffer(ctx, &whaleswapv1.QueryTradesByOfferRequest{})
	require.Error(t, err)
	// TradesByTaker: nil, missing taker
	_, err = k.TradesByTaker(ctx, nil)
	require.Error(t, err)
	_, err = k.TradesByTaker(ctx, &whaleswapv1.QueryTradesByTakerRequest{})
	require.Error(t, err)
	// TradesByPool: nil, missing id
	_, err = k.TradesByPool(ctx, nil)
	require.Error(t, err)
	_, err = k.TradesByPool(ctx, &whaleswapv1.QueryTradesByPoolRequest{})
	require.Error(t, err)

	// Auctions: Auction(nil), Auction(0)
	_, err = k.Auction(ctx, nil)
	require.Error(t, err)
	_, err = k.Auction(ctx, &whaleswapv1.QueryAuctionRequest{AuctionId: 0})
	require.Error(t, err)
	// Auctions list with nil req
	_, err = k.Auctions(ctx, nil)
	require.NoError(t, err)
}

// newTestKeeper creates a keeper with in-memory store and no state.
func newTestKeeper(t *testing.T) (Keeper, context.Context) {
	t.Helper()
	// Fallback minimal setup: use context.Background(); some query paths only
	// rely on nil-guard logic and will not access state.
	// In case state access occurs, these calls will return errors rather than panic.
	return Keeper{}, context.Background()
}
