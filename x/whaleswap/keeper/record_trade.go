package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// recordTradeWithOperations creates a Trade record from operations and indexes it.
// Emits EventTradeOperation for each operation, then EventTradeRecorded for the batch.
// Operations should have sent/received already populated.
func (k Keeper) recordTradeWithOperations(
	ctx context.Context,
	trader string,
	ops []whaleswapv1.TradeOperation,
	note string,
) (uint64, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	tradeId, _ := k.tradeSeq.Next(ctx)
	t := sdkCtx.BlockTime()

	// Aggregate totals
	totalSent := sdk.NewCoins()
	totalReceived := sdk.NewCoins()
	for _, op := range ops {
		if op.Sent.IsValid() && op.Sent.Amount.IsPositive() {
			totalSent = totalSent.Add(op.Sent)
		}
		if op.Received.IsValid() && op.Received.Amount.IsPositive() {
			totalReceived = totalReceived.Add(op.Received)
		}
	}

	trade := whaleswapv1.Trade{
		TradeId:       tradeId,
		Trader:        trader,
		Height:        uint64(sdkCtx.BlockHeight()),
		Timestamp:     &t,
		Operations:    ops,
		TotalSent:     totalSent,
		TotalReceived: totalReceived,
		Note:          note,
	}

	if err := k.TradesMap.Set(ctx, tradeId, trade); err != nil {
		return 0, cosmossdkerrors.Wrap(err, "failed to save trade")
	}

	// Index by trader
	if err := k.TradesByTraderIndex.Set(ctx, collections.Join(trader, tradeId), tradeId); err != nil {
		return 0, cosmossdkerrors.Wrap(err, "failed to index trade by trader")
	}

	// Index by operation type and emit enhanced domain events
	for i, op := range ops {
		switch v := op.Op.(type) {
		case *whaleswapv1.TradeOperation_Swap:
			if v.Swap != nil && v.Swap.PoolId > 0 {
				poolId := v.Swap.PoolId
				if err := k.TradesByPoolIndex.Set(ctx, collections.Join(poolId, tradeId), tradeId); err != nil {
					return 0, cosmossdkerrors.Wrap(err, "failed to index trade by pool")
				}
				// Emit enhanced EventPoolSwap with trade linkage
				if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPoolSwap{
					PoolId:         poolId,
					TradeId:        tradeId,
					OperationIndex: uint32(i),
				}); err != nil {
					return 0, cosmossdkerrors.Wrap(err, "failed to emit EventPoolSwap")
				}
			}
		case *whaleswapv1.TradeOperation_Take:
			if v.Take != nil && v.Take.OfferId > 0 {
				offerId := v.Take.OfferId
				if err := k.TradesByOfferIndex.Set(ctx, collections.Join(offerId, tradeId), tradeId); err != nil {
					return 0, cosmossdkerrors.Wrap(err, "failed to index trade by offer")
				}
				// Emit enhanced EventOfferTaken with trade linkage and units
				if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventOfferTaken{
					OfferId:    offerId,
					TradeId:    tradeId,
					UnitsTaken: v.Take.TakeUnits,
				}); err != nil {
					return 0, cosmossdkerrors.Wrap(err, "failed to emit EventOfferTaken")
				}
				// EventPfandReleased emitted by caller (MsgMakeTrade, TakeOffer) who knows if offer closed
			}
		case *whaleswapv1.TradeOperation_Auction:
			if v.Auction != nil && v.Auction.AuctionId > 0 {
				auctionId := v.Auction.AuctionId
				if err := k.TradesByAuctionIndex.Set(ctx, collections.Join(auctionId, tradeId), tradeId); err != nil {
					return 0, cosmossdkerrors.Wrap(err, "failed to index trade by auction")
				}
				// EventAuctionRedeemed is emitted by RedeemAuction handler with the final trade_id
			}
		}
	}

	// Emit summary event after all operations indexed
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventTradeRecorded{
		TradeId:       tradeId,
		Trader:        trader,
		NumOperations: uint32(len(ops)),
		Note:          note,
	}); err != nil {
		return 0, cosmossdkerrors.Wrap(err, "failed to emit EventTradeRecorded")
	}

	return tradeId, nil
}
