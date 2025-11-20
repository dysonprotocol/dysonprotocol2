package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// OpenAuction escrows the provided sell coin from the seller into the module,
// creates or updates the auction NFT class keyed by bid_denom with policy
// configured from module parameters, mints an NFT representing the escrow,
// transfers it to the seller, and records the auction with reverse indexes.
//
// Validation:
//   - seller must be a valid address
//   - sell.amount must be > 0; sell.denom and bid_denom must be valid and differ
//   - whaleswap root name must exist and resolve to the module account
//
// Returns:
//   - *whaleswapv1.MsgOpenAuctionResponse containing the new auction_id
//
// Emits:
//   - EventAuctionCreated on success
//
// Errors are returned on validation or module failures; no panics.
func (k Keeper) OpenAuction(ctx context.Context, msg *whaleswapv1.MsgOpenAuction) (*whaleswapv1.MsgOpenAuctionResponse, error) {
	sellerBz, err := k.accKeeper.AddressCodec().StringToBytes(msg.Seller)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid seller")
	}
	seller := sdk.AccAddress(sellerBz)

	// Ensure whaleswap root name is present and resolves to module before class ops
	if err := k.ensureWhaleswapRootName(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed ensuring whaleswap.dys root before open auction")
	}

	// Validate sell coin (explicit in msg): solid denom, amount > 0, denom != bid_denom
	if !msg.Sell.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "sell amount must be > 0")
	}
	if err := sdk.ValidateDenom(msg.Sell.Denom); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid sell denom: %s", msg.Sell.Denom)
	}
	// No wrapper denoms exist
	if err := sdk.ValidateDenom(msg.BidDenom); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid bid denom: %s", msg.BidDenom)
	}
	// No wrapper denoms exist
	if msg.Sell.Denom == msg.BidDenom {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "sell and bid denoms must differ: %s", msg.Sell.Denom)
	}

	// Escrow: move from seller → module
	if err := k.bank.SendCoinsFromAccountToModule(ctx, seller, whaleswap.ModuleName, sdk.NewCoins(msg.Sell)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send coins from account to module")
	}

	// Prepare class id based on bid denom (one class per bid denom)
	classID := whaleswapv1.AuctionClassID(msg.BidDenom)
	// Upsert class basic info
	if _, err := k.nameSvc.SaveClass(ctx, &nameservicev1.MsgSaveClass{
		NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(),
		ClassId:         classID,
		Name:            whaleswapv1.AuctionClassName,
		Symbol:          whaleswapv1.AuctionClassSymbol,
		Description:     "Auction class for escrowed solid coins",
	}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to save class")
	}
	// Apply policy knobs using params (propagate errors)
	p := k.GetParams(ctx)
	if _, err := k.nameSvc.SetNFTClassAlwaysListed(ctx, &nameservicev1.MsgSetNFTClassAlwaysListed{NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(), ClassId: classID, AlwaysListed: true}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set always_listed for class %s", classID)
	}
	if _, err := k.nameSvc.SetNFTClassValuationFeePct(ctx, &nameservicev1.MsgSetNFTClassValuationFeePct{NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(), ClassId: classID, ValuationFeePct: p.ValuationFeePct}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set valuation_fee_pct for class %s", classID)
	}
	if _, err := k.nameSvc.SetNFTClassValuationPeriod(ctx, &nameservicev1.MsgSetNFTClassValuationPeriod{NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(), ClassId: classID, ValuationPeriod: p.ValuationPeriod}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set valuation_period for class %s", classID)
	}
	if _, err := k.nameSvc.SetNFTClassBidTimeout(ctx, &nameservicev1.MsgSetNFTClassBidTimeout{NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(), ClassId: classID, BidTimeout: p.BidTimeout}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set bid_timeout for class %s", classID)
	}
	if _, err := k.nameSvc.SetNFTClassMinimumBidPercentIncrease(ctx, &nameservicev1.MsgSetNFTClassMinimumBidPercentIncrease{NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(), ClassId: classID, MinimumBidPercentIncrease: p.MinimumBidPercentIncrease}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set minimum_bid_percent_increase for class %s", classID)
	}
	// Allowed denoms: only bid_denom
	if _, err := k.nameSvc.SetNFTClassAllowedDenoms(ctx, &nameservicev1.MsgSetNFTClassAllowedDenoms{
		NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(),
		ClassId:         classID,
		AllowedDenoms:   []string{msg.BidDenom},
	}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set allowed_denoms for class %s", classID)
	}

	// Mint NFT id = auctionSeq, send to seller
	id, err := k.auctionSeq.Next(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get next auction id")
	}
	nftID := fmt.Sprintf("%010d", id)
	if _, err := k.nameSvc.MintNFT(ctx, &nameservicev1.MsgMintNFT{NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(), ClassId: classID, NftId: nftID}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to mint nft")
	}
	if _, err := k.nameSvc.MoveNft(ctx, &nameservicev1.MsgMoveNft{NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(), ClassId: classID, NftId: nftID, ToAddress: msg.Seller}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to move nft")
	}

	// Record auction
	rec := whaleswapv1.AuctionRecord{AuctionId: id, ClassId: classID, NftId: nftID, Sell: msg.Sell, BidDenom: msg.BidDenom, Seller: msg.Seller}
	if err := k.AuctionsMap.Set(ctx, id, rec); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set auction")
	}
	// Write reverse indexes
	if err := k.AuctionsBySellBid.Set(ctx, collections.Join3(rec.Sell.Denom, rec.BidDenom, rec.AuctionId), rec.AuctionId); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set auction by sell bid")
	}
	if err := k.AuctionsByBidSell.Set(ctx, collections.Join3(rec.BidDenom, rec.Sell.Denom, rec.AuctionId), rec.AuctionId); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set auction by bid sell")
	}

	if err := sdk.UnwrapSDKContext(ctx).EventManager().EmitTypedEvent(&whaleswapv1.EventAuctionCreated{AuctionId: id}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventAuctionCreated")
	}

	// Update address metrics
	if err := k.incrementAuctionCreated(ctx, msg.Seller, msg.Sell); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update auction metrics")
	}

	return &whaleswapv1.MsgOpenAuctionResponse{AuctionId: id}, nil
}

