package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	nameservice "dysonprotocol.com/x/nameservice"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// AcceptBid accepts the current active bid, transferring NFT ownership and releasing escrowed funds.
//
// Semantics:
//   - Accepts the highest current bid on an NFT owned by the sender.
//   - Transfers escrowed bid amount from module to current NFT owner.
//   - Transfers NFT ownership from current owner to bidder.
//   - Updates NFT valuation to the accepted bid amount.
//   - Clears all bid-related data from NFT state.
//
// Validation:
//   - Sender must be the current NFT owner.
//   - NFT must have an active bid (non-zero amount and bidder).
//
// State Updates:
//   - Transfers bid amount from module escrow to previous NFT owner.
//   - Transfers NFT ownership to bidder.
//   - Updates NFT valuation to accepted bid amount.
//   - Clears current bid data (bidder, amount, timestamp, height).
//   - Marks active bid record as accepted and removes from active index.
//
// Emits:
//   - EventBidAccepted(class_id, nft_id, new_owner) on successful bid acceptance.
//
// Returns:
//   - *nameservicev1.MsgAcceptBidResponse (empty response indicating success).
//
// Errors are returned on NFT not found, unauthorized sender, no active bid, or transfer failures; no panics.
func (k Keeper) AcceptBid(ctx context.Context, msg *nameservicev1.MsgAcceptBid) (*nameservicev1.MsgAcceptBidResponse, error) {
	k.Logger.Info("AcceptBid: Processing", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId, "owner", msg.Owner)

	// Extract the NFT data
	nftData, err := k.GetNFTData(ctx, msg.NftClassId, msg.NftId)
	if err != nil {
		k.Logger.Error("AcceptBid: NFT not found", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId, "error", err)
		return nil, cosmossdkerrors.Wrapf(err, "failed to get NFT data")
	}

	// Get the current owner of the NFT
	nftOwnerAddr := k.nftKeeper.GetOwner(ctx, msg.NftClassId, msg.NftId)
	nftOwner := nftOwnerAddr.String()

	// Convert message sender address
	senderAddr, err := sdk.AccAddressFromBech32(msg.Owner)
	if err != nil {
		k.Logger.Error("AcceptBid: Invalid owner address", "owner", msg.Owner, "error", err)
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid owner address: %s", msg.Owner)
	}

	// Verify authorization: The sender must be the current owner of the NFT
	if !nftOwnerAddr.Equals(senderAddr) {
		k.Logger.Error("AcceptBid: Unauthorized - sender is not the NFT owner",
			"sender", msg.Owner,
			"nft_owner", nftOwner)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "only the current owner of the NFT can accept bids for this NFT")
	}

	// Check if there's an active bid
	if nftData.CurrentBidder == "" || nftData.CurrentBid.IsZero() {
		k.Logger.Error("AcceptBid: No active bid", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrNotFound, "no active bid to accept")
	}

	// Convert bidder address
	bidderAddr, err := sdk.AccAddressFromBech32(nftData.CurrentBidder)
	if err != nil {
		k.Logger.Error("AcceptBid: Invalid bidder address", "bidder", nftData.CurrentBidder, "error", err)
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid bidder address: %s", nftData.CurrentBidder)
	}

	// Send the bid amount from module to NFT's current owner
	bidCoins := sdk.NewCoins(nftData.CurrentBid)
	err = k.bankKeeper.SendCoinsFromModuleToAccount(ctx, nameservice.ModuleName, nftOwnerAddr, bidCoins)
	if err != nil {
		k.Logger.Error("AcceptBid: Failed to transfer bid amount to NFT owner", "amount", nftData.CurrentBid, "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to transfer bid amount to NFT owner")
	}
	k.Logger.Info("AcceptBid: Transferred bid to NFT owner", "amount", nftData.CurrentBid, "owner", nftOwner)

	// Store current values before changing
	prevOwner := nftOwner
	bidAmount := nftData.CurrentBid

	// Update NFT data - bidder becomes new owner, valuation set to bid amount
	nftData.Valuation = nftData.CurrentBid

	// Clear out the current bid info
	nftData.CurrentBidder = ""
	nftData.CurrentBid = sdk.Coin{}
	nftData.BidTimestamp = nil
	// Clear bid height after acceptance
	nftData.BidHeight = 0

	// Update the NFT data
	if err := k.SetNFTData(ctx, msg.NftClassId, msg.NftId, nftData); err != nil {
		k.Logger.Error("AcceptBid: Failed to update NFT data", "error", err)
		return nil, cosmossdkerrors.Wrapf(err, "failed to update NFT data")
	}

	// --- Bid ledger update: mark active bid as ACCEPTED and clear active index ---
	if bidID, err := k.activeBidForNFT.Get(ctx, collections.Join(msg.NftClassId, msg.NftId)); err == nil {
		rec, gErr := k.bids.Get(ctx, bidID)
		if gErr == nil {
			rec.Status = nameservicev1.BidStatus_BID_ACCEPTED
			_ = k.bids.Set(ctx, bidID, rec)
		}
		_ = k.activeBidForNFT.Remove(ctx, collections.Join(msg.NftClassId, msg.NftId))
	}

	// Transfer the NFT to the new owner
	err = k.nftKeeper.Transfer(ctx, msg.NftClassId, msg.NftId, bidderAddr)
	if err != nil {
		k.Logger.Error("AcceptBid: Failed to transfer NFT", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to transfer NFT to bidder")
	}

	k.Logger.Info("AcceptBid: Successfully transferred NFT",
		"nft_class_id", msg.NftClassId,
		"nft_id", msg.NftId,
		"from", prevOwner,
		"to", bidderAddr.String(),
		"amount", bidAmount.String())

	// Get SDK context from context.Context
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventBidAccepted{
			ClassId:  msg.NftClassId,      // Class ID of the NFT being transferred
			NftId:    msg.NftId,           // NFT ID
			NewOwner: bidderAddr.String(), // The bidder who becomes the new owner
		},
	); err != nil {
		k.Logger.Error("AcceptBid: Failed to emit event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return &nameservicev1.MsgAcceptBidResponse{}, nil
}
