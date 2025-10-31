package keeper

import (
	"fmt"

	"cosmossdk.io/collections"
	cosmossdk_math "cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	"dysonprotocol.com/x/whaleswap/types"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// InitGenesis initializes state from genesis
func (k Keeper) InitGenesis(ctx sdk.Context, gs *types.GenesisState) {
	gs.Params = types.MigrateParams(gs.Params)
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
		// ONE-TIME MIGRATION: fee_pct → fee_rate
		if len(p.FeeRate) == 0 && p.FeePct != "" {
			feeDec, err := cosmossdk_math.LegacyNewDecFromStr(p.FeePct)
			if err != nil {
				panic(fmt.Sprintf("genesis: pool %d: invalid fee_pct %s: %v", p.PoolId, p.FeePct, err))
			}
			// Create two DecCoins, one per reserve denom in canonical order
			if len(p.Coins) != 2 {
				panic(fmt.Sprintf("genesis: pool %d: must have exactly 2 reserve coins for fee_rate migration", p.PoolId))
			}
			p.FeeRate = sdk.DecCoins{
				sdk.NewDecCoinFromDec(p.Coins[0].Denom, feeDec),
				sdk.NewDecCoinFromDec(p.Coins[1].Denom, feeDec),
			}
		}
		// Validate FeeRate is set (either migrated or already in new format)
		if len(p.FeeRate) == 0 {
			panic(fmt.Sprintf("genesis: pool %d: fee_rate must be set (migration from fee_pct failed or missing)", p.PoolId))
		}
		if len(p.FeeRate) != 2 {
			panic(fmt.Sprintf("genesis: pool %d: fee_rate must have exactly 2 entries", p.PoolId))
		}
		types.MigratePool(p)
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
			if o.SettlementMode == whaleswapv1.SettlementMode_SETTLEMENT_LIQUID {
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
		// ONE-TIME MIGRATION: deprecated fields → new fields
		// Migrate trader (field 3 → field 20)
		if t.Trader == "" && t.Taker != "" {
			t.Trader = t.Taker
		}
		// Migrate height (field 4 → field 21)
		if t.Height == 0 && t.HeightDeprecated > 0 {
			t.Height = t.HeightDeprecated
		}
		// Migrate timestamp (field 5 → field 22)
		if t.Timestamp == nil && t.TimestampDeprecated != nil {
			t.Timestamp = t.TimestampDeprecated
		}
		// Migrate sent (field 6 → field 24)
		if len(t.TotalSent) == 0 && t.Sent.IsValid() && t.Sent.Amount.IsPositive() {
			t.TotalSent = sdk.NewCoins(t.Sent)
		}
		// Migrate received (field 7 → field 25)
		if len(t.TotalReceived) == 0 && t.Received.IsValid() && t.Received.Amount.IsPositive() {
			t.TotalReceived = sdk.NewCoins(t.Received)
		}
		// Migrate note (field 10 → field 26)
		if t.Note == "" && t.NoteDeprecated != "" {
			t.Note = t.NoteDeprecated
		}
		// Reconstruct operations from deprecated fields (offer_id, pool_id, auction_id)
		if len(t.Operations) == 0 {
			operations := []whaleswapv1.TradeOperation{}
			// Create operations based on deprecated context fields
			// If offer_id is set, create a Take operation
			if t.OfferId > 0 {
				takeOp := whaleswapv1.TradeOperation{
					Op: &whaleswapv1.TradeOperation_Take{
						Take: &whaleswapv1.TakeItem{OfferId: t.OfferId},
					},
				}
				// Populate sent/received if available
				if t.Sent.IsValid() {
					takeOp.Sent = t.Sent
				}
				if t.Received.IsValid() {
					takeOp.Received = t.Received
				}
				operations = append(operations, takeOp)
			}
			// If pool_id is set, create a Swap operation
			if t.PoolId > 0 {
				swapOp := whaleswapv1.TradeOperation{
					Op: &whaleswapv1.TradeOperation_Swap{
						Swap: &whaleswapv1.SwapLeg{PoolId: t.PoolId},
					},
				}
				// Populate sent/received if available
				if t.Sent.IsValid() {
					swapOp.Sent = t.Sent
				}
				if t.Received.IsValid() {
					swapOp.Received = t.Received
				}
				operations = append(operations, swapOp)
			}
			// If auction_id is set, create an Auction operation
			if t.AuctionId > 0 {
				auctionOp := whaleswapv1.TradeOperation{
					Op: &whaleswapv1.TradeOperation_Auction{
						Auction: &whaleswapv1.AuctionRedeem{AuctionId: t.AuctionId},
					},
				}
				// Populate sent/received if available
				if t.Sent.IsValid() {
					auctionOp.Sent = t.Sent
				}
				if t.Received.IsValid() {
					auctionOp.Received = t.Received
				}
				operations = append(operations, auctionOp)
			}
			t.Operations = operations
		}
		// Validate migrated trade
		if t.Trader == "" {
			panic(fmt.Sprintf("genesis: trade %d: trader cannot be empty after migration", t.TradeId))
		}
		// Note: operations can be empty for edge cases, but that's acceptable
		if err := k.TradesMap.Set(ctx, t.TradeId, *t); err != nil {
			panic(err)
		}

		// Index by trader
		if t.Trader != "" {
			if err := k.TradesByTraderIndex.Set(ctx, collections.Join(t.Trader, t.TradeId), t.TradeId); err != nil {
				panic(err)
			}
		}

		// Index by operations
		for _, op := range t.Operations {
			switch v := op.Op.(type) {
			case *whaleswapv1.TradeOperation_Swap:
				if v.Swap != nil && v.Swap.PoolId > 0 {
					if err := k.TradesByPoolIndex.Set(ctx, collections.Join(v.Swap.PoolId, t.TradeId), t.TradeId); err != nil {
						panic(err)
					}
				}
			case *whaleswapv1.TradeOperation_Take:
				if v.Take != nil && v.Take.OfferId > 0 {
					if err := k.TradesByOfferIndex.Set(ctx, collections.Join(v.Take.OfferId, t.TradeId), t.TradeId); err != nil {
						panic(err)
					}
				}
			case *whaleswapv1.TradeOperation_Auction:
				if v.Auction != nil && v.Auction.AuctionId > 0 {
					if err := k.TradesByAuctionIndex.Set(ctx, collections.Join(v.Auction.AuctionId, t.TradeId), t.TradeId); err != nil {
						panic(err)
					}
				}
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

	// Leverage positions
	leverageCollateral := map[string]cosmossdk_math.Int{}
	var maxPositionID uint64
	for _, p := range gs.Positions {
		if p.PositionId > maxPositionID {
			maxPositionID = p.PositionId
		}
		if p.Status == whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED {
			if p.LiquidationStatus == whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_INITIALIZED {
				p.Status = whaleswapv1.PositionStatus_POSITION_STATUS_LIQUIDATING
			} else {
				p.Status = whaleswapv1.PositionStatus_POSITION_STATUS_OPEN
			}
		}
		if err := k.LeveragePositions.Set(ctx, p.PositionId, *p); err != nil {
			panic(err)
		}
		if err := k.indexPosition(ctx, *p); err != nil {
			panic(err)
		}
		// Tally collateral requirements ONLY for active positions
		if (p.Status == whaleswapv1.PositionStatus_POSITION_STATUS_OPEN || p.Status == whaleswapv1.PositionStatus_POSITION_STATUS_LIQUIDATING) && p.Collateral.Amount.IsPositive() {
			den := p.Collateral.Denom
			if cur, ok := leverageCollateral[den]; ok {
				leverageCollateral[den] = cur.Add(p.Collateral.Amount)
			} else {
				leverageCollateral[den] = p.Collateral.Amount
			}
		}
	}
	if maxPositionID > 0 {
		if err := k.leveragePositionSeq.Set(ctx, maxPositionID+1); err != nil {
			panic(err)
		}
	} else {
		if err := k.leveragePositionSeq.Set(ctx, 1); err != nil {
			panic(err)
		}
	}
	// Validate module balances cover all required components per denom (AMM reserves + offer escrow + pfand + auctions + leverage collateral)
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
	for d := range leverageCollateral {
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
		if v, ok := leverageCollateral[denom]; ok {
			need = need.Add(v)
		}
		balAmt := k.bank.GetBalance(ctx, moduleAddr, denom).Amount
		if balAmt.LT(need) {
			panic(fmt.Sprintf(
				"genesis module balance deficit for %s: have=%s need=%s (amm=%s escrow=%s pfand=%s auction=%s collateral=%s)",
				denom,
				balAmt.String(),
				need.String(),
				ammRequired[denom].String(),
				escrowRequired[denom].String(),
				pfandRequired[denom].String(),
				auctionRequired[denom].String(),
				leverageCollateral[denom].String(),
			))
		}
	}

	// Final AMM sanity (shares/liquidity/coverage) after import
	if err := k.AssertAMMInvariants(ctx); err != nil {
		panic(err)
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
	// Collect leverage positions
	var positions []*types.LeveragePosition
	_ = k.LeveragePositions.Walk(ctx, nil, func(key uint64, value types.LeveragePosition) (bool, error) {
		v := value
		positions = append(positions, &v)
		return false, nil
	})

	return &types.GenesisState{Params: p, Pools: pools, Offers: offers, Trades: trades, Auctions: auctions, Positions: positions}
}
