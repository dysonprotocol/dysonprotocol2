package keeper

import (
	"context"
	"strings"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// RedeemAuction lets the current NFT owner redeem the auction escrow when no
// bid is active. It transfers the escrowed sell coins from the module to the
// caller, burns the NFT, deletes reverse indexes and the primary record, and
// optionally records a Trade if the redeemer is the last winning bidder
// (owner != original seller and a positive valuation exists in bid_denom).
//
// Validation:
//   - auction must exist
//   - caller must equal the current NFT owner
//   - no current bidder may exist
//   - module escrow must contain at least the sell amount
//
// Returns:
//   - *whaleswapv1.MsgRedeemAuctionResponse (empty body)
//
// Emits:
//   - EventAuctionRedeemed with auction_id and trade_id (0 if seller redeems
//     without a recorded trade)
//
// Errors are returned on validation or module failures; no panics.
func (k Keeper) RedeemAuction(ctx context.Context, msg *whaleswapv1.MsgRedeemAuction) (*whaleswapv1.MsgRedeemAuctionResponse, error) {
	rec, err := k.AuctionsMap.Get(ctx, msg.AuctionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "auction not found: %d", msg.AuctionId)
	}
	// Require current NFT owner to redeem
	ownerAddr := k.nft.GetOwner(ctx, rec.ClassId, rec.NftId)
	if ownerAddr.Empty() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "NFT not found: class %s, id %s", rec.ClassId, rec.NftId)
	}
	ownerStr, err := k.accKeeper.AddressCodec().BytesToString(ownerAddr.Bytes())
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to encode nft owner for %s/%s", rec.ClassId, rec.NftId)
	}
	if ownerStr != msg.Caller {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrUnauthorized, "only current owner can redeem: owner=%s caller=%s", ownerStr, msg.Caller)
	}
	// Enforce no current bidder
	nftData, err := k.nameSvc.GetNFTData(ctx, rec.ClassId, rec.NftId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "nft not found: %s/%s", rec.ClassId, rec.NftId)
	}
	if strings.TrimSpace(nftData.CurrentBidder) != "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "cannot redeem while a bid is active")
	}
	// Escrow pre-check
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	bal := k.bank.GetBalance(ctx, moduleAddr, rec.Sell.Denom)
	if !bal.IsGTE(rec.Sell) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "module escrow insufficient: have=%s need=%s", bal.String(), rec.Sell.String())
	}
	to, err2 := k.accKeeper.AddressCodec().StringToBytes(msg.Caller)
	if err2 != nil {
		return nil, cosmossdkerrors.Wrapf(err2, "invalid caller")
	}
	if err := k.bank.SendCoinsFromModuleToAccount(ctx, whaleswap.ModuleName, sdk.AccAddress(to), sdk.NewCoins(rec.Sell)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send coins")
	}
	if _, err := k.nameSvc.BurnNFT(ctx, &nameservicev1.MsgBurnNFT{NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(), ClassId: rec.ClassId, NftId: rec.NftId}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to burn nft")
	}
	// Delete reverse indexes first, then primary record
	if err := k.AuctionsBySellBid.Remove(ctx, collections.Join3(rec.Sell.Denom, rec.BidDenom, rec.AuctionId)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to remove auction index (sell|bid): %s|%s id=%d", rec.Sell.Denom, rec.BidDenom, rec.AuctionId)
	}
	if err := k.AuctionsByBidSell.Remove(ctx, collections.Join3(rec.BidDenom, rec.Sell.Denom, rec.AuctionId)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to remove auction index (bid|sell): %s|%s id=%d", rec.BidDenom, rec.Sell.Denom, rec.AuctionId)
	}
	if err := k.AuctionsMap.Remove(ctx, msg.AuctionId); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to remove auction %d", msg.AuctionId)
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	// Record a trade ONLY if the redeemer is the last winning/claimed bidder:
	// - ownership transferred away from original seller
	// - valuation set in bid denom and > 0 (set by nameservice on accept/claim)
	var tradeId uint64
	if ownerStr != rec.Seller && nftData.Valuation.Denom == rec.BidDenom && nftData.Valuation.Amount.IsPositive() {
		// Build operation for auction redemption
		op := whaleswapv1.TradeOperation{
			Op: &whaleswapv1.TradeOperation_Auction{
				Auction: &whaleswapv1.AuctionRedeem{AuctionId: rec.AuctionId},
			},
			Sent:     sdk.NewCoin(rec.BidDenom, nftData.Valuation.Amount),
			Received: rec.Sell,
		}

		// Record single-operation trade
		tid, err := k.recordTradeWithOperations(ctx, msg.Caller, []whaleswapv1.TradeOperation{op}, "")
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to record auction trade")
		}
		tradeId = tid
	}

	// Emit EventAuctionRedeemed with trade_id (0 if seller redeemed without trade)
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventAuctionRedeemed{
		AuctionId: msg.AuctionId,
		TradeId:   tradeId,
	}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventAuctionRedeemed")
	}

	// Assert module balance invariants after redemption
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after RedeemAuction")
	}

	return &whaleswapv1.MsgRedeemAuctionResponse{}, nil
}
