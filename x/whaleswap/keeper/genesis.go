package keeper

import (
	"fmt"

	"cosmossdk.io/collections"
	cosmossdk_math "cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	"dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// InitGenesis initializes state from genesis
func (k Keeper) InitGenesis(ctx sdk.Context, gs *types.GenesisState) {
	// params
	if err := k.SetParams(ctx, gs.Params); err != nil {
		panic(err)
	}

	// Pools
	// Tally AMM reserve requirements and sanity-check shares supply
	ammRequired := map[string]cosmossdk_math.Int{}
	var maxPoolID uint64
	for _, p := range gs.Pools {
		if p.PoolId > maxPoolID {
			maxPoolID = p.PoolId
		}
		if err := k.PoolsMap.Set(ctx, p.PoolId, *p); err != nil {
			panic(err)
		}
		// accumulate AMM reserves per denom
		for _, c := range p.Coins {
			if cur, ok := ammRequired[c.Denom]; ok {
				ammRequired[c.Denom] = cur.Add(c.Amount)
			} else {
				ammRequired[c.Denom] = c.Amount
			}
		}
		// shares supply must be positive for any existing pool
		supply := k.bank.GetSupply(ctx, p.SharesDenom).Amount
		if !supply.IsPositive() {
			panic(fmt.Sprintf("genesis: shares supply must be > 0 for pool %d denom %s", p.PoolId, p.SharesDenom))
		}
	}
	if maxPoolID > 0 {
		if err := k.poolSeq.Set(ctx, maxPoolID+1); err != nil {
			panic(err)
		}
	} else {
		if err := k.poolSeq.Set(ctx, 1); err != nil {
			panic(err)
		}
	}

	// Offers
	escrowRequired := map[string]cosmossdk_math.Int{}
	pfandRequired := map[string]cosmossdk_math.Int{}
	var maxOfferID uint64
	for _, o := range gs.Offers {
		if o.OfferId > maxOfferID {
			maxOfferID = o.OfferId
		}
		if err := k.OffersMap.Set(ctx, o.OfferId, *o); err != nil {
			panic(err)
		}
		// rebuild indexes
		// have, id
		if err := k.OffersByHave.Set(ctx, collections.Join(o.RemainingHave.Denom, o.OfferId), o.OfferId); err != nil {
			panic(err)
		}
		// want, id
		if err := k.OffersByWant.Set(ctx, collections.Join(o.RemainingWant.Denom, o.OfferId), o.OfferId); err != nil {
			panic(err)
		}
		// owner+status
		if err := k.OffersByOwnerStatus.Set(ctx, collections.Join3(o.Maker, o.Status, o.OfferId), o.OfferId); err != nil {
			panic(err)
		}
		// price index only for open offers (require positive amounts)
		if o.Status == types.OfferStatusOpen {
			if !o.RemainingHave.Amount.IsPositive() || !o.RemainingWant.Amount.IsPositive() {
				panic(fmt.Sprintf("genesis: open offer %d must have positive have and want amounts", o.OfferId))
			}
			haveDenom := o.RemainingHave.Denom
			wantDenom := o.RemainingWant.Denom
			low, high := haveDenom, wantDenom
			if low > high {
				low, high = high, low
			}
			pairKey := low + "|" + high
			priceHavePerWant := cosmossdk_math.LegacyNewDecFromInt(o.RemainingHave.Amount).Quo(cosmossdk_math.LegacyNewDecFromInt(o.RemainingWant.Amount))
			priceWantPerHave := cosmossdk_math.LegacyNewDecFromInt(o.RemainingWant.Amount).Quo(cosmossdk_math.LegacyNewDecFromInt(o.RemainingHave.Amount))
			priceDec := priceWantPerHave
			if low == wantDenom && high == haveDenom {
				priceDec = priceHavePerWant
			}
			if err := k.OffersByPairPrice.Set(ctx, collections.Join3(pairKey, priceDec.String(), o.OfferId), o.OfferId); err != nil {
				panic(err)
			}
			// Tally escrow/pfand requirements for open offers
			if k.isLiquidDenom(o.RemainingHave.Denom) {
				if o.PfandLocked.Amount.IsPositive() {
					den := o.PfandLocked.Denom
					if cur, ok := pfandRequired[den]; ok {
						pfandRequired[den] = cur.Add(o.PfandLocked.Amount)
					} else {
						pfandRequired[den] = o.PfandLocked.Amount
					}
				}
			} else {
				if o.RemainingHave.Amount.IsPositive() {
					den := o.RemainingHave.Denom
					if cur, ok := escrowRequired[den]; ok {
						escrowRequired[den] = cur.Add(o.RemainingHave.Amount)
					} else {
						escrowRequired[den] = o.RemainingHave.Amount
					}
				}
			}
		}
	}
	if maxOfferID > 0 {
		if err := k.offerSeq.Set(ctx, maxOfferID+1); err != nil {
			panic(err)
		}
	} else {
		if err := k.offerSeq.Set(ctx, 1); err != nil {
			panic(err)
		}
	}

	// Trades
	var maxTradeID uint64
	for _, t := range gs.Trades {
		if t.TradeId > maxTradeID {
			maxTradeID = t.TradeId
		}
		if err := k.TradesMap.Set(ctx, t.TradeId, *t); err != nil {
			panic(err)
		}
		// rebuild reverse indexes
		if t.PoolId > 0 {
			if err := k.TradesByPoolIndex.Set(ctx, collections.Join(t.PoolId, t.TradeId), t.TradeId); err != nil {
				panic(err)
			}
		}
		if t.Taker != "" {
			if err := k.TradesByTakerIndex.Set(ctx, collections.Join(t.Taker, t.TradeId), t.TradeId); err != nil {
				panic(err)
			}
		}
	}
	if maxTradeID > 0 {
		if err := k.tradeSeq.Set(ctx, maxTradeID+1); err != nil {
			panic(err)
		}
	} else {
		if err := k.tradeSeq.Set(ctx, 1); err != nil {
			panic(err)
		}
	}

	// Auctions (tally required sell escrow)
	var maxAuctionID uint64
	auctionRequired := map[string]cosmossdk_math.Int{}
	for _, a := range gs.Auctions {
		if a.AuctionId > maxAuctionID {
			maxAuctionID = a.AuctionId
		}
		if err := k.AuctionsMap.Set(ctx, a.AuctionId, *a); err != nil {
			panic(err)
		}
		// Reverse indexes
		if err := k.AuctionsBySellBid.Set(ctx, collections.Join3(a.Sell.Denom, a.BidDenom, a.AuctionId), a.AuctionId); err != nil {
			panic(err)
		}
		if err := k.AuctionsByBidSell.Set(ctx, collections.Join3(a.BidDenom, a.Sell.Denom, a.AuctionId), a.AuctionId); err != nil {
			panic(err)
		}
		// Tally auction escrow requirement
		den := a.Sell.Denom
		if cur, ok := auctionRequired[den]; ok {
			auctionRequired[den] = cur.Add(a.Sell.Amount)
		} else {
			auctionRequired[den] = a.Sell.Amount
		}
	}
	if maxAuctionID > 0 {
		if err := k.auctionSeq.Set(ctx, maxAuctionID+1); err != nil {
			panic(err)
		}
	} else {
		if err := k.auctionSeq.Set(ctx, 1); err != nil {
			panic(err)
		}
	}
	// Validate module balances cover all required components per denom (AMM reserves + offer escrow + pfand + auctions)
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	denomSet := map[string]struct{}{}
	for d := range ammRequired {
		denomSet[d] = struct{}{}
	}
	for d := range escrowRequired {
		denomSet[d] = struct{}{}
	}
	for d := range pfandRequired {
		denomSet[d] = struct{}{}
	}
	for d := range auctionRequired {
		denomSet[d] = struct{}{}
	}
	for denom := range denomSet {
		need := cosmossdk_math.NewInt(0)
		if v, ok := ammRequired[denom]; ok {
			need = need.Add(v)
		}
		if v, ok := escrowRequired[denom]; ok {
			need = need.Add(v)
		}
		if v, ok := pfandRequired[denom]; ok {
			need = need.Add(v)
		}
		if v, ok := auctionRequired[denom]; ok {
			need = need.Add(v)
		}
		balAmt := k.bank.GetBalance(ctx, moduleAddr, denom).Amount
		if balAmt.LT(need) {
			panic(fmt.Sprintf(
				"genesis module balance deficit for %s: have=%s need=%s (amm=%s escrow=%s pfand=%s auction=%s)",
				denom,
				balAmt.String(),
				need.String(),
				ammRequired[denom].String(),
				escrowRequired[denom].String(),
				pfandRequired[denom].String(),
				auctionRequired[denom].String(),
			))
		}
	}
}

// ExportGenesis exports current module state
func (k Keeper) ExportGenesis(ctx sdk.Context) *types.GenesisState {
	p := k.GetParams(ctx)
	// Collect pools
	var pools []*types.Pool
	_ = k.PoolsMap.Walk(ctx, nil, func(key uint64, value types.Pool) (bool, error) {
		v := value
		pools = append(pools, &v)
		return false, nil
	})
	// Collect offers
	var offers []*types.OfferData
	_ = k.OffersMap.Walk(ctx, nil, func(key uint64, value types.OfferData) (bool, error) {
		v := value
		offers = append(offers, &v)
		return false, nil
	})
	// Collect trades
	var trades []*types.Trade
	_ = k.TradesMap.Walk(ctx, nil, func(key uint64, value types.Trade) (bool, error) {
		v := value
		trades = append(trades, &v)
		return false, nil
	})
	// Collect auctions
	var auctions []*types.AuctionRecord
	_ = k.AuctionsMap.Walk(ctx, nil, func(key uint64, value types.AuctionRecord) (bool, error) {
		v := value
		auctions = append(auctions, &v)
		return false, nil
	})

	return &types.GenesisState{Params: p, Pools: pools, Offers: offers, Trades: trades, Auctions: auctions}
}
