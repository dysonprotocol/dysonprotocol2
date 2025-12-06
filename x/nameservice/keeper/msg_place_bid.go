package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservice "dysonprotocol.com/x/nameservice"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// PlaceBid places or outbids on an NFT, escrowing funds and updating bid state.
//
// Semantics:
//   - Places a bid on a listed NFT, refunding any previous bidder.
//   - For first bids: amount must be >= current valuation (if active).
//   - For subsequent bids: amount must exceed current bid by minimum percentage increase.
//   - Bids expire based on class bid timeout or NFT valuation expiry.
//   - Bid funds are escrowed in module account until bid is accepted, rejected, or expires.
//
// Validation:
//   - Bid amount must be valid according to class rules.
//   - NFT must be listed for sale (directly or via class always_listed).
//   - Cannot bid on authority-owned or module-owned NFTs.
//   - Bid denomination must match valuation/current bid denomination.
//   - First bids must meet or exceed valuation; subsequent bids must meet minimum increase.
//
// State Updates:
//   - Escrows bid amount from bidder to module account.
//   - Refunds previous bidder if outbid.
//   - Creates new active bid record, marks previous bid as outbid.
//   - Updates NFT data with current bid info, timestamp, and height.
//   - Updates bid indexes (by bidder, by NFT, active bid mapping).
//
// Emits:
//   - EventBidPlaced(class_id, nft_id, bidder, bid_amount) on successful bid placement.
//
// Returns:
//   - *nameservicev1.MsgPlaceBidResponse (empty response indicating success).
//
// Errors are returned on invalid bid amounts, unlisted NFTs, invalid bidders, insufficient increases, or escrow failures; no panics.
func (k Keeper) PlaceBid(ctx context.Context, msg *nameservicev1.MsgPlaceBid) (*nameservicev1.MsgPlaceBidResponse, error) {
	k.Logger.Info("PlaceBid: Processing bid", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId, "bidder", msg.Bidder, "bid_amount", msg.BidAmount)
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Validate the bid amount using shared validation logic
	if err := k.ValidateValuation(ctx, msg.NftClassId, msg.BidAmount); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invalid bid amount")
	}

	// Load the NFT data
	nftData, err := k.GetNFTData(ctx, msg.NftClassId, msg.NftId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get NFT data for class %s, ID %s", msg.NftClassId, msg.NftId)
	}

	// Ensure the NFT is currently listed for sale either directly or via the class-level always_listed flag
	classData, _ := k.GetNFTClassData(ctx, msg.NftClassId) // ignore error; if not found treated as zero value
	if !(nftData.Listed || classData.AlwaysListed) {
		k.Logger.Error("PlaceBid: NFT not listed for sale", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "NFT is not listed for sale")
	}

	// Get the current owner of the NFT
	nftOwnerAddr := k.nftKeeper.GetOwner(ctx, msg.NftClassId, msg.NftId)

	// Check if the owner is the authority address
	authorityAddr, err := sdk.AccAddressFromBech32(k.GetAuthority())
	if err == nil && nftOwnerAddr.Equals(authorityAddr) {
		k.Logger.Error("PlaceBid: Cannot place bid on NFT owned by the authority",
			"nft_class_id", msg.NftClassId, "nft_id", msg.NftId,
			"nft_owner", nftOwnerAddr.String())
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "cannot place bid on NFT owned by the authority")
	}

	// Disallow bids on NFTs owned by module accounts
	if ownerAcc := k.accountKeeper.GetAccount(sdkCtx, nftOwnerAddr); ownerAcc != nil {
		if _, ok := ownerAcc.(sdk.ModuleAccountI); ok {
			k.Logger.Error("PlaceBid: Cannot place bid on NFT owned by module account",
				"nft_class_id", msg.NftClassId, "nft_id", msg.NftId,
				"nft_owner", nftOwnerAddr.String())
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, "cannot place bid on NFT owned by a module account")
		}
	}

	// Get class data for bidding params
	classDataForBids, _ := k.GetNFTClassData(ctx, msg.NftClassId)

	// Get current timestamp
	currentTime := sdkCtx.BlockTime()

	// Check if valuation has expired
	valuationExpired := false
	if !nftData.Valuation.IsZero() {
		// Check the NFT data for valuation expiry
		if nftData.ValuationExpiry.Before(currentTime) {
			k.Logger.Info("PlaceBid: Valuation has expired",
				"nft_class_id", msg.NftClassId, "nft_id", msg.NftId,
				"valuation_expiry", nftData.ValuationExpiry.String())
			valuationExpired = true
		}
	}

	// Determine if valuation is active and applicable
	hasActiveValuation := !nftData.Valuation.IsZero() && !valuationExpired

	// ---- Validation Phase ----

	// Validate denomination
	if hasActiveValuation && nftData.Valuation.Denom != msg.BidAmount.Denom {
		k.Logger.Error("PlaceBid: Bid denomination does not match valuation denomination",
			"bid_denom", msg.BidAmount.Denom, "valuation_denom", nftData.Valuation.Denom)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest,
			fmt.Sprintf("bid denomination (%s) must match valuation denomination (%s)",
				msg.BidAmount.Denom, nftData.Valuation.Denom))
	}

	// Validate bid amount based on whether there's an existing bid
	if nftData.CurrentBidder != "" {
		// Case: Subsequent bid
		if !nftData.CurrentBid.IsZero() {
			// Ensure bid denomination matches current bid denomination
			if nftData.CurrentBid.Denom != msg.BidAmount.Denom {
				k.Logger.Error("PlaceBid: Bid denomination does not match current bid denomination",
					"bid_denom", msg.BidAmount.Denom, "current_bid_denom", nftData.CurrentBid.Denom)
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest,
					fmt.Sprintf("bid denomination (%s) must match current bid denomination (%s)",
						msg.BidAmount.Denom, nftData.CurrentBid.Denom))
			}

			// Get the minimum bid percentage increase from class data or default 0
			minBidIncrease, err := math.LegacyNewDecFromStr(classDataForBids.MinimumBidPercentIncrease)
			if err != nil {
				k.Logger.Error("PlaceBid: Failed to parse minimum bid percent increase", "error", err)
				return nil, cosmossdkerrors.Wrap(err, "failed to parse minimum bid percent increase")
			}

			// First check if the bid is higher at all
			if !msg.BidAmount.IsGT(nftData.CurrentBid) {
				k.Logger.Error("PlaceBid: Bid amount not higher than current bid",
					"bid_amount", msg.BidAmount, "current_bid", nftData.CurrentBid)
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "bid amount must be higher than current bid")
			}

			// Then check if it meets the minimum percentage increase
			// Convert existing bid amount to Dec for percentage calculation
			currentBidAmountLegacy, err := math.LegacyNewDecFromStr(nftData.CurrentBid.Amount.String())
			if err != nil {
				k.Logger.Error("PlaceBid: Failed to convert current bid amount to decimal", "error", err)
				return nil, cosmossdkerrors.Wrap(err, "failed to convert current bid amount to decimal")
			}

			// Calculate minimum required bid amount: current_bid * (1 + min_increase)
			// Need to convert minBidIncrease (Dec) to LegacyDec
			minBidIncreaseLegacy, err := math.LegacyNewDecFromStr(minBidIncrease.String())
			if err != nil {
				k.Logger.Error("PlaceBid: Failed to convert minimum bid increase to legacy decimal", "error", err)
				return nil, cosmossdkerrors.Wrap(err, "failed to convert minimum bid increase to legacy decimal")
			}

			onePlusIncrease := math.LegacyOneDec().Add(minBidIncreaseLegacy)
			minRequiredBidAmount := currentBidAmountLegacy.Mul(onePlusIncrease).Ceil()

			// Convert new bid amount to Dec for comparison
			newBidAmountLegacy, err := math.LegacyNewDecFromStr(msg.BidAmount.Amount.String())
			if err != nil {
				k.Logger.Error("PlaceBid: Failed to convert new bid amount to decimal", "error", err)
				return nil, cosmossdkerrors.Wrap(err, "failed to convert new bid amount to decimal")
			}

			// Compare the new bid with the minimum required amount
			if newBidAmountLegacy.LT(minRequiredBidAmount) {
				// Compute human-friendly percent (e.g., 1 instead of 0.01%) and integer min required amount
				percentDisplay := minBidIncreaseLegacy.Mul(math.LegacyNewDec(100)).TruncateInt().String()
				minRequiredInt := minRequiredBidAmount.TruncateInt().String()

				k.Logger.Error("PlaceBid: Bid amount does not meet minimum percentage increase",
					"bid_amount", msg.BidAmount.Amount.String(),
					"current_bid", nftData.CurrentBid.Amount.String(),
					"min_required", minRequiredInt,
					"min_increase_percent_display", percentDisplay,
					"denom", msg.BidAmount.Denom)

				// Example: The minimum bid is 1% higher than current bid: 1515000 uatom
				return nil, cosmossdkerrors.Wrap(
					sdkerrors.ErrInvalidRequest,
					fmt.Sprintf(
						"The next minimum acceptable bid is %s%% higher than current bid: %s %s",
						percentDisplay,
						minRequiredInt,
						msg.BidAmount.Denom,
					),
				)
			}

			k.Logger.Info("PlaceBid: New bid meets minimum percentage increase requirement",
				"new_bid", msg.BidAmount, "current_bid", nftData.CurrentBid,
				"min_increase_percent", classDataForBids.MinimumBidPercentIncrease)
		}
		k.Logger.Info("PlaceBid: New bid is higher than current bid",
			"new_bid", msg.BidAmount, "current_bid", nftData.CurrentBid)
	} else {
		// Case: First bid - must be >= valuation if valuation is active
		if hasActiveValuation && !msg.BidAmount.IsGTE(nftData.Valuation) {
			k.Logger.Error("PlaceBid: First bid amount must be >= valuation",
				"bid_amount", msg.BidAmount, "valuation", nftData.Valuation)
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest,
				fmt.Sprintf("first bid amount must be greater than or equal to current valuation: %s", nftData.Valuation.String()))
		}
		k.Logger.Info("PlaceBid: First bid meets or exceeds valuation",
			"bid_amount", msg.BidAmount, "valuation", nftData.Valuation)
	}

	// Convert bidder string to AccAddress
	bidder, err := sdk.AccAddressFromBech32(msg.Bidder)
	if err != nil {
		k.Logger.Error("PlaceBid: Invalid bidder address", "bidder", msg.Bidder, "error", err)
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid bidder address: %s", msg.Bidder)
	}

	// ---- Transaction Phase ----

	// If there's an existing bid, refund the previous bidder
	if nftData.CurrentBidder != "" && nftData.CurrentBidder != msg.Bidder {
		previousBidder, err := sdk.AccAddressFromBech32(nftData.CurrentBidder)
		if err != nil {
			k.Logger.Error("PlaceBid: Invalid previous bidder address", "previous_bidder", nftData.CurrentBidder, "error", err)
			return nil, cosmossdkerrors.Wrapf(err, "invalid previous bidder address: %s", nftData.CurrentBidder)
		}

		// Return the escrowed funds to the previous bidder if current bid is not zero
		if !nftData.CurrentBid.IsZero() {
			prevBidCoins := sdk.NewCoins(nftData.CurrentBid)
			err = k.bankKeeper.SendCoinsFromModuleToAccount(ctx, nameservice.ModuleName, previousBidder, prevBidCoins)
			if err != nil {
				k.Logger.Error("PlaceBid: Failed to refund previous bidder",
					"previous_bidder", nftData.CurrentBidder, "amount", nftData.CurrentBid, "error", err)
				return nil, cosmossdkerrors.Wrap(err, "failed to refund previous bidder")
			}
			k.Logger.Info("PlaceBid: Refunded previous bidder",
				"previous_bidder", nftData.CurrentBidder, "amount", nftData.CurrentBid)
		} else {
			k.Logger.Info("PlaceBid: No refund needed for previous bidder (empty bid)",
				"previous_bidder", nftData.CurrentBidder)
		}
	}

	// Escrow the bid amount from the bidder
	bidCoins := sdk.NewCoins(msg.BidAmount)
	err = k.bankKeeper.SendCoinsFromAccountToModule(ctx, bidder, nameservice.ModuleName, bidCoins)
	if err != nil {
		k.Logger.Error("PlaceBid: Failed to escrow bid amount", "bidder", msg.Bidder, "amount", msg.BidAmount, "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to escrow bid amount")
	}
	k.Logger.Info("PlaceBid: Successfully escrowed bid amount", "bidder", msg.Bidder, "amount", msg.BidAmount)

	// ---- State Update Phase ----

	// --- Bid ledger write ---
	// Determine previous active bid for this NFT, if any
	var (
		prevActiveBidID uint64
		hadPrev         bool
	)
	if bidID, err := k.activeBidForNFT.Get(ctx, collections.Join(msg.NftClassId, msg.NftId)); err == nil {
		prevActiveBidID = bidID
		hadPrev = true
	}

	// Allocate new bid ID
	newBidID, err := k.bidSeq.Next(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to allocate bid id")
	}

	// Create bid record
	bidRecord := nameservicev1.BidRecord{
		BidId:     newBidID,
		ClassId:   msg.NftClassId,
		NftId:     msg.NftId,
		Bidder:    msg.Bidder,
		Amount:    msg.BidAmount,
		Status:    nameservicev1.BidStatus_BID_ACTIVE,
		Timestamp: sdkCtx.BlockTime(),
		Height:    uint64(sdkCtx.BlockHeight()),
	}
	if prevActiveBidID != 0 {
		bidRecord.ReplacesBidId = prevActiveBidID
	}

	// Persist new record and secondary indexes
	if err := k.bids.Set(ctx, newBidID, bidRecord); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to store bid record")
	}
	if err := k.bidsByBidder.Set(ctx, collections.Join(msg.Bidder, newBidID), newBidID); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update bidsByBidder index")
	}
	if err := k.bidsByNFT.Set(ctx, collections.Join3(msg.NftClassId, msg.NftId, newBidID), newBidID); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update bidsByNFT index")
	}
	if err := k.activeBidForNFT.Set(ctx, collections.Join(msg.NftClassId, msg.NftId), newBidID); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update activeBidForNFT index")
	}

	// If there was a previous active bid for this NFT, mark it as outbid and link
	if hadPrev {
		prev, err := k.bids.Get(ctx, prevActiveBidID)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to get previous bid record %d", prevActiveBidID)
		}
		prev.Status = nameservicev1.BidStatus_BID_OUTBID
		prev.ReplacedByBidId = newBidID
		if err := k.bids.Set(ctx, prevActiveBidID, prev); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to update previous bid record %d", prevActiveBidID)
		}
	}

	// Update the NFT bid information
	nftData.CurrentBidder = msg.Bidder
	nftData.CurrentBid = msg.BidAmount
	bidTimestamp := sdkCtx.BlockTime()

	nftData.BidTimestamp = &bidTimestamp
	// Record the block height when the bid was placed
	nftData.BidHeight = uint64(sdkCtx.BlockHeight())

	// Update the NFT data in the store
	if err := k.SetNFTData(ctx, msg.NftClassId, msg.NftId, nftData); err != nil {
		k.Logger.Error("PlaceBid: Failed to update NFT data", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to update NFT data")
	}

	k.Logger.Info("PlaceBid: Successfully updated NFT bid information",
		"nft_class_id", msg.NftClassId,
		"nft_id", msg.NftId,
		"bidder", msg.Bidder,
		"bid_amount", msg.BidAmount)

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventBidPlaced{
			ClassId:   msg.NftClassId,
			NftId:     msg.NftId,
			Bidder:    msg.Bidder,
			BidAmount: &msg.BidAmount,
		},
	); err != nil {
		k.Logger.Error("PlaceBid: Failed to emit event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return &nameservicev1.MsgPlaceBidResponse{}, nil
}
