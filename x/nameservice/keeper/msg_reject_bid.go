package keeper

import (
	"context"
	"fmt"
	"time"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservice "dysonprotocol.com/x/nameservice"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// RejectBid rejects the current active bid and sets a new valuation, charging a rejection fee.
//
// Semantics:
//   - Rejects the current bid on an NFT owned by the sender.
//   - Sets new NFT valuation, charging a rejection fee proportional to the new valuation.
//   - Rejection fee routing: to NFT class owner for user-controlled classes, to community pool for governance-controlled classes.
//   - Refunds the rejected bidder their escrowed funds.
//   - Clears bid data from NFT state.
//
// Validation:
//   - Sender must be the current NFT owner.
//   - NFT must have an active bid to reject.
//   - New valuation must be valid and higher than current valuation.
//
// State Updates:
//   - Refunds escrowed bid amount from module to rejected bidder.
//   - Updates NFT valuation to new amount if provided.
//   - Charges rejection fee to the NFT class owner (or community pool for governance-controlled classes).
//   - Clears current bid data (bidder, amount, timestamp, height).
//   - Marks active bid record as rejected.
//
// Emits:
//   - EventBidRejected(class_id, nft_id, rejection_fee) on successful bid rejection.
//
// Returns:
//   - *nameservicev1.MsgRejectBidResponse with the rejection fee amount.
//
// Errors are returned on NFT not found, unauthorized sender, no active bid, invalid valuation, or transfer failures; no panics.
func (k Keeper) RejectBid(ctx context.Context, msg *nameservicev1.MsgRejectBid) (*nameservicev1.MsgRejectBidResponse, error) {
	k.Logger.Info("RejectBid: Processing", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId, "owner", msg.Owner, "new_value", msg.NewValuation)

	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Extract the NFT data
	nftData, err := k.GetNFTData(ctx, msg.NftClassId, msg.NftId)
	if err != nil {
		k.Logger.Error("RejectBid: NFT not found", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId, "error", err)
		return nil, cosmossdkerrors.Wrapf(err, "failed to get NFT data")
	}

	// Verify authorization: the sender must be the owner of the specific NFT
	ownerAddr := k.nftKeeper.GetOwner(ctx, msg.NftClassId, msg.NftId)
	if ownerAddr.String() != msg.Owner {
		k.Logger.Error("RejectBid: Authorization failed",
			"sender", msg.Owner,
			"actual_owner", ownerAddr.String(),
			"nft_class_id", msg.NftClassId,
			"nft_id", msg.NftId)
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"only the owner of the NFT (%s) can reject bids for it",
			ownerAddr.String())
	}

	// Convert message sender address
	senderAddr, err := sdk.AccAddressFromBech32(msg.Owner)
	if err != nil {
		k.Logger.Error("RejectBid: Invalid owner address", "owner", msg.Owner, "error", err)
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid owner address: %s", msg.Owner)
	}

	// Check if there's an active bid
	if nftData.CurrentBidder == "" || nftData.CurrentBid.IsZero() {
		k.Logger.Error("RejectBid: No active bid", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrNotFound, "no active bid to reject")
	}

	// Check that the new valuation has the same denomination as the current bid
	if msg.NewValuation.Denom != nftData.CurrentBid.Denom {
		k.Logger.Error("RejectBid: New valuation denom mismatch",
			"new_valuation_denom", msg.NewValuation.Denom,
			"current_bid_denom", nftData.CurrentBid.Denom)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest,
			fmt.Sprintf("new valuation denom (%s) must match current bid denom (%s)",
				msg.NewValuation.Denom, nftData.CurrentBid.Denom))
	}

	// Enforce that the new valuation is at least the minimum percent higher than the current bid
	classDataForBids, _ := k.GetNFTClassData(ctx, msg.NftClassId)
	minBidIncrease, err := math.LegacyNewDecFromStr(classDataForBids.MinimumBidPercentIncrease)
	if err != nil {
		k.Logger.Error("RejectBid: Failed to parse minimum bid percent increase", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to parse minimum bid percent increase")
	}

	// Convert amounts to LegacyDec for arithmetic
	currentBidAmountLegacy, err := math.LegacyNewDecFromStr(nftData.CurrentBid.Amount.String())
	if err != nil {
		k.Logger.Error("RejectBid: Failed to convert current bid amount to decimal", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to convert current bid amount to decimal")
	}

	// Convert min increase to LegacyDec (even though already a LegacyDec, keep consistent with patterns)
	minBidIncreaseLegacy, err := math.LegacyNewDecFromStr(minBidIncrease.String())
	if err != nil {
		k.Logger.Error("RejectBid: Failed to convert minimum bid increase to legacy decimal", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to convert minimum bid increase to legacy decimal")
	}

	onePlusIncrease := math.LegacyOneDec().Add(minBidIncreaseLegacy)
	minRequiredValuation := currentBidAmountLegacy.Mul(onePlusIncrease).Ceil()

	newValuationAmountLegacy, err := math.LegacyNewDecFromStr(msg.NewValuation.Amount.String())
	if err != nil {
		k.Logger.Error("RejectBid: Failed to convert new valuation amount to decimal", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to convert new valuation amount to decimal")
	}

	if newValuationAmountLegacy.LT(minRequiredValuation) {
		percentDisplay := minBidIncreaseLegacy.Mul(math.LegacyNewDec(100)).TruncateInt().String()
		minRequiredInt := minRequiredValuation.TruncateInt().String()

		k.Logger.Error("RejectBid: New valuation does not meet minimum percentage increase",
			"new_valuation", msg.NewValuation.Amount.String(),
			"current_bid", nftData.CurrentBid.Amount.String(),
			"min_required", minRequiredInt,
			"min_increase_percent_display", percentDisplay,
			"denom", msg.NewValuation.Denom)

		return nil, cosmossdkerrors.Wrap(
			sdkerrors.ErrInvalidRequest,
			fmt.Sprintf(
				"The next minimum acceptable valuation is %s%% higher than current bid: %s %s",
				percentDisplay,
				minRequiredInt,
				msg.NewValuation.Denom,
			),
		)
	}

	// Refund the bidder
	bidderAddr, err := sdk.AccAddressFromBech32(nftData.CurrentBidder)
	if err != nil {
		k.Logger.Error("RejectBid: Invalid bidder address", "bidder", nftData.CurrentBidder, "error", err)
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid bidder address: %s", nftData.CurrentBidder)
	}
	bidCoins := sdk.NewCoins(nftData.CurrentBid)
	err = k.bankKeeper.SendCoinsFromModuleToAccount(ctx, nameservice.ModuleName, bidderAddr, bidCoins)
	if err != nil {
		k.Logger.Error("RejectBid: Failed to refund bid amount", "amount", nftData.CurrentBid, "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to refund bid amount")
	}

	// Validate the new valuation
	if err := k.ValidateValuation(ctx, msg.NftClassId, msg.NewValuation); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to validate new valuation: %s", msg.NewValuation.String())
	}

	currentTime := sdkCtx.BlockTime()

	// Set a new expiry time of now + 1 year
	newExpiryTime := currentTime.AddDate(1, 0, 0)

	// --------------------------------
	// Calculate and charge reject bid fee on full new valuation
	// --------------------------------
	//
	// Rejection fee is configured per NFT class via SetNFTClassRejectBidValuationFeePercent.
	// Fee percentage is stored in NFTClassData.RejectBidValuationFeePercent and must be
	// within module parameter bounds (MinRejectBidValuationFeePercent to MaxRejectBidValuationFeePercent).
	// Only the NFT class owner can set this percentage. Defaults to 0% if not set.

	// Get the reject bid fee percentage
	rejectFeePercent, err := math.LegacyNewDecFromStr(classDataForBids.RejectBidValuationFeePercent)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to parse reject bid valuation fee percent")
	}

	// Calculate fee based on the full new valuation
	totalFeeCoins := sdk.Coins{}
	if !rejectFeePercent.IsZero() {

		// Convert to DecCoins for decimal arithmetic
		decValuation := sdk.NewDecCoinsFromCoins(msg.NewValuation)

		// Convert to LegacyDec for compatibility with SDK DecCoins methods
		legacyRejectFeePercent, err := math.LegacyNewDecFromStr(rejectFeePercent.String())
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to convert reject fee percent to legacy decimal")
		}

		// Calculate the fee amount: valuation * rejectFeePercent
		decRejectFee := decValuation.MulDec(legacyRejectFeePercent)

		// Convert back to regular coins
		totalFeeCoins, _ = decRejectFee.TruncateDecimal()

		// Charge the reject fee
		if !totalFeeCoins.IsZero() {
			k.Logger.Info("Charging reject bid fee on full valuation",
				"nft_class_id", msg.NftClassId,
				"nft_id", msg.NftId,
				"valuation", msg.NewValuation.String(),
				"reject_fee_percent", rejectFeePercent.String(),
				"reject_fee", totalFeeCoins.String())

			// Route fee to NFT class owner or community pool based on ownership
			// - User-controlled NFT classes: fee goes to the class owner
			// - Governance-controlled NFT classes (authority-owned): fee goes to community pool
			classOwner, _, err := k.GetDenomOwner(sdkCtx, msg.NftClassId)
			if err != nil {
				k.Logger.Error("RejectBid: Failed to get NFT class owner", "class_id", msg.NftClassId, "error", err)
				return nil, cosmossdkerrors.Wrap(err, "failed to get NFT class owner")
			}

			// Check if the owner is the authority (governance module)
			if classOwner == k.GetAuthority() {
				// Send fee to community pool (for governance-controlled classes)
				k.Logger.Info("RejectBid: Sending fee to community pool", "fee", totalFeeCoins.String())
				err = k.communityPoolKeeper.FundCommunityPool(ctx, totalFeeCoins, senderAddr)
				if err != nil {
					return nil, cosmossdkerrors.Wrap(err, "failed to fund community pool with reject fee")
				}
			} else {
				// Send fee to the owner of the NFT class (for user-controlled classes)
				k.Logger.Info("RejectBid: Sending fee to NFT class owner", "owner", classOwner, "fee", totalFeeCoins.String())
				classOwnerAddr, err := sdk.AccAddressFromBech32(classOwner)
				if err != nil {
					return nil, cosmossdkerrors.Wrap(err, "failed to parse NFT class owner address")
				}
				err = k.bankKeeper.SendCoins(ctx, senderAddr, classOwnerAddr, totalFeeCoins)
				if err != nil {
					return nil, cosmossdkerrors.Wrap(err, "failed to send reject fee to NFT class owner")
				}
			}
		}
	}

	// Update the NFT data: set new valuation, new expiry, clear out the current bid
	nftData.Valuation = msg.NewValuation
	nftData.ValuationExpiry = newExpiryTime
	nftData.CurrentBidder = ""
	nftData.CurrentBid = sdk.Coin{}
	nftData.BidTimestamp = nil
	// Clear bid height after rejection
	nftData.BidHeight = 0

	// Update the NFT data using the centralized function
	if err := k.SetNFTData(ctx, msg.NftClassId, msg.NftId, nftData); err != nil {
		k.Logger.Error("RejectBid: Failed to update NFT data", "error", err)
		return nil, cosmossdkerrors.Wrapf(err, "failed to update NFT data")
	}

	// --- Bid ledger update: mark active bid as REJECTED, record fee, clear active index ---
	bidID, err := k.activeBidForNFT.Get(ctx, collections.Join(msg.NftClassId, msg.NftId))
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get active bid ID for NFT %s/%s", msg.NftClassId, msg.NftId)
	}
	rec, err := k.bids.Get(ctx, bidID)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get bid record %d", bidID)
	}
			rec.Status = nameservicev1.BidStatus_BID_REJECTED
			rec.RejectionFee = totalFeeCoins
			if err := k.bids.Set(ctx, bidID, rec); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update bid record %d", bidID)
		}
		if err := k.activeBidForNFT.Remove(ctx, collections.Join(msg.NftClassId, msg.NftId)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to remove active bid index for NFT %s/%s", msg.NftClassId, msg.NftId)
	}

	// Emit an event
	if evErr := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventBidRejected{
			ClassId:      msg.NftClassId, // Class ID of the NFT
			NftId:        msg.NftId,      // NFT ID
			RejectionFee: totalFeeCoins,  // Fee paid to the NFT class owner
		},
	); evErr != nil {
		k.Logger.Error("failed to emit bid rejected event", "error", evErr)
		return nil, cosmossdkerrors.Wrap(evErr, "failed to emit bid rejected event")
	}

	k.Logger.Info("RejectBid: Completed successfully",
		"nft_class_id", msg.NftClassId,
		"nft_id", msg.NftId,
		"new_valuation", msg.NewValuation.String(),
		"new_expiry", newExpiryTime.Format(time.RFC3339),
		"total_fees", totalFeeCoins.String())

	return &nameservicev1.MsgRejectBidResponse{
		RejectionFee: totalFeeCoins,
	}, nil
}
