package keeper

import (
	"context"
	"time"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservice "dysonprotocol.com/x/nameservice"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// ClaimBid allows a bidder to claim an NFT after the bid timeout has expired without acceptance.
//
// Semantics:
//   - Allows a bidder to claim NFT ownership after bid timeout expires.
//   - Extends valuation expiry by one period (if remaining ≤ period, prevents >2× accumulation).
//   - Distributes escrowed bid with fair fee allocation:
//   - Surplus fee: (bid - oldValuation) × feePercent × remainingTime/period
//   - Renewal fee: bid × feePercent × 1.0 (for the new period)
//   - Seller receives: bid - totalFee
//   - Fee goes to class owner (or community pool for governance-owned classes)
//   - Transfers NFT ownership to bidder.
//   - Updates NFT valuation to the claimed bid amount.
//
// Fee Rationale:
//   - Surplus fee: pays for valuation increase during remaining time (seller already paid for this)
//   - Renewal fee: pays for the new period being added (bidder pays for their protection)
//   - If remaining > period: no extension allowed, only surplus fee (capped at 1 period)
//   - This prevents sybil bidding exploits while ensuring bidders get working names
//
// Validation:
//   - NFT must have an active bid.
//   - Sender must be the current bidder.
//   - Bid timeout period (from class config) must have elapsed since bid placement.
//
// State Updates:
//   - Extends valuation expiry by one period (if allowed).
//   - Transfers fee from escrow to class owner or community pool.
//   - Transfers remaining bid (bid - fee) from escrow to previous NFT owner.
//   - Transfers NFT ownership to bidder.
//   - Updates NFT valuation to claimed bid amount.
//   - Clears current bid data (bidder, amount, timestamp, height).
//   - Marks active bid record as claimed.
//
// Emits:
//   - EventBidClaimed(class_id, nft_id, bidder) on successful bid claim.
//
// Returns:
//   - *nameservicev1.MsgClaimBidResponse (empty response indicating success).
//
// Errors are returned on no active bid, unauthorized bidder, timeout not elapsed, or transfer failures; no panics.
func (k Keeper) ClaimBid(ctx context.Context, msg *nameservicev1.MsgClaimBid) (*nameservicev1.MsgClaimBidResponse, error) {
	k.Logger.Info("ClaimBid: Processing claim request", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId, "bidder", msg.Bidder)

	// Get current NFT data
	nftData, err := k.GetNFTData(ctx, msg.NftClassId, msg.NftId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get NFT data for class %s, id %s", msg.NftClassId, msg.NftId)
	}

	// Check if there is an active bid
	if nftData.CurrentBidder == "" {
		k.Logger.Error("ClaimBid: No active bid found", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrNotFound, "no active bid found for this NFT")
	}

	// Verify bidder is the one who placed the bid
	if nftData.CurrentBidder != msg.Bidder {
		k.Logger.Error("ClaimBid: Unauthorized - not the bidder",
			"nft_class_id", msg.NftClassId,
			"nft_id", msg.NftId,
			"record_bidder", nftData.CurrentBidder,
			"msg_bidder", msg.Bidder)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "only the bidder can claim the NFT")
	}

	// Check if bid timeout has elapsed
	currentTime := sdk.UnwrapSDKContext(ctx).BlockTime()
	// params := k.GetParams(ctx)

	// Check if BidTimestamp is set
	if nftData.BidTimestamp == nil {
		k.Logger.Error("ClaimBid: No bid timestamp set", "nft_class_id", msg.NftClassId, "nft_id", msg.NftId)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "no bid timestamp set")
	}

	// Calculate timeout time by adding the class BidTimeout duration to the bid timestamp
	classData, err := k.GetNFTClassData(ctx, msg.NftClassId)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to get class data")
	}
	timeoutTime := nftData.BidTimestamp.Add(classData.BidTimeout)

	// Check if current time is before the timeout time
	if currentTime.Before(timeoutTime) {
		k.Logger.Error("ClaimBid: Bid timeout has not elapsed",
			"current_time", currentTime.Format(time.RFC3339),
			"bid_timestamp", nftData.BidTimestamp.Format(time.RFC3339),
			"timeout_time", timeoutTime.Format(time.RFC3339))
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "bid timeout has not elapsed")
	}

	k.Logger.Info("ClaimBid: Bid timeout has elapsed",
		"current_time", currentTime.Format(time.RFC3339),
		"bid_timestamp", nftData.BidTimestamp.Format(time.RFC3339),
		"timeout_time", timeoutTime.Format(time.RFC3339))

	// Get the current owner of the NFT
	currentOwnerAddr := k.nftKeeper.GetOwner(ctx, msg.NftClassId, msg.NftId)
	currentOwner := currentOwnerAddr.String()

	// Convert bidder string to AccAddress
	bidderAddr, err := sdk.AccAddressFromBech32(msg.Bidder)
	if err != nil {
		k.Logger.Error("ClaimBid: Invalid bidder address", "bidder", msg.Bidder, "error", err)
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid bidder address: %s", msg.Bidder)
	}

	// Calculate fee and determine new expiry
	// Unified logic: always extend by 1 period if remaining <= period (like Renew)
	// Fee = surplus fee (for valuation increase) + renewal fee (for new period)
	bidAmount := nftData.CurrentBid
	oldValuation := nftData.Valuation
	period := classData.ValuationPeriod
	periodSeconds := int64(period.Seconds())

	// Parse fee percent
	feePercentStr := "0"
	if classData.ValuationFeePct != "" {
		feePercentStr = classData.ValuationFeePct
	}
	feePercent, err := math.LegacyNewDecFromStr(feePercentStr)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to parse valuation fee percent")
	}

	// Calculate remaining time (can be negative if expired)
	remainingSeconds := nftData.ValuationExpiry.Unix() - currentTime.Unix()

	// Determine if we can extend (remaining <= period, prevents >2× accumulation)
	canExtend := remainingSeconds <= periodSeconds
	var newExpiry time.Time
	if canExtend {
		// Extend from max(now, currentExpiry) + period
		baseTime := nftData.ValuationExpiry
		if baseTime.Before(currentTime) {
			baseTime = currentTime
		}
		newExpiry = baseTime.Add(period)
	} else {
		// Can't extend - already have >1 period remaining
		newExpiry = nftData.ValuationExpiry
	}

	// Calculate fees
	var feeCoins sdk.Coins
	if !bidAmount.IsZero() && periodSeconds > 0 && !feePercent.IsZero() {
		decBid := sdk.NewDecCoinsFromCoins(bidAmount)
		var totalDecFee sdk.DecCoins

		// 1. Surplus fee: for valuation increase during remaining time
		if bidAmount.Amount.GT(oldValuation.Amount) && remainingSeconds > 0 {
			surplus := sdk.NewCoin(bidAmount.Denom, bidAmount.Amount.Sub(oldValuation.Amount))
			decSurplus := sdk.NewDecCoinsFromCoins(surplus)
			// Cap remaining at 1 period for fee calculation
			effectiveRemaining := remainingSeconds
			if effectiveRemaining > periodSeconds {
				effectiveRemaining = periodSeconds
			}
			portionRemaining := math.LegacyNewDecFromInt(math.NewInt(effectiveRemaining)).
				Quo(math.LegacyNewDecFromInt(math.NewInt(periodSeconds)))
			surplusFee := decSurplus.MulDec(feePercent).MulDec(portionRemaining)
			totalDecFee = totalDecFee.Add(surplusFee...)

			k.Logger.Info("ClaimBid: Calculated surplus fee",
				"surplus", surplus.String(),
				"remaining_seconds", effectiveRemaining,
				"surplus_fee", surplusFee.String())
		}

		// 2. Renewal fee: for the new period being added (only if extending)
		if canExtend {
			renewalFee := decBid.MulDec(feePercent)
			totalDecFee = totalDecFee.Add(renewalFee...)

			k.Logger.Info("ClaimBid: Calculated renewal fee",
				"bid", bidAmount.String(),
				"renewal_fee", renewalFee.String())
		}

		feeCoins, _ = totalDecFee.TruncateDecimal()
		k.Logger.Info("ClaimBid: Total fee calculated",
			"bid", bidAmount.String(),
			"old_valuation", oldValuation.String(),
			"remaining_seconds", remainingSeconds,
			"can_extend", canExtend,
			"new_expiry", newExpiry.Format(time.RFC3339),
			"total_fee", feeCoins.String())
	}

	// Distribute escrowed bid
	if !bidAmount.IsZero() {
		// Send fee to class owner or community pool (from module escrow)
		if !feeCoins.IsZero() {
			sdkCtx := sdk.UnwrapSDKContext(ctx)
			classOwner, _, err := k.GetDenomOwner(sdkCtx, msg.NftClassId)
			if err != nil {
				k.Logger.Error("ClaimBid: Failed to get class owner for fee", "error", err)
				return nil, cosmossdkerrors.Wrap(err, "failed to get class owner for fee routing")
			}

			if classOwner == k.GetAuthority() {
				// Send fee to community pool from module account.
				// FundCommunityPool properly updates FeePool.CommunityPool accounting.
				moduleAddr := k.accountKeeper.GetModuleAddress(nameservice.ModuleName)
				if err := k.communityPoolKeeper.FundCommunityPool(ctx, feeCoins, moduleAddr); err != nil {
					k.Logger.Error("ClaimBid: Failed to send fee to community pool", "fee", feeCoins.String(), "error", err)
					return nil, cosmossdkerrors.Wrap(err, "failed to send fee to community pool")
				}
				k.Logger.Info("ClaimBid: Sent fee to community pool", "fee", feeCoins.String())
			} else {
				// Send fee to class owner
				classOwnerAddr, err := sdk.AccAddressFromBech32(classOwner)
				if err != nil {
					return nil, cosmossdkerrors.Wrap(err, "failed to parse class owner address")
				}
				if err := k.bankKeeper.SendCoinsFromModuleToAccount(ctx, nameservice.ModuleName, classOwnerAddr, feeCoins); err != nil {
					k.Logger.Error("ClaimBid: Failed to send fee to class owner", "fee", feeCoins.String(), "error", err)
					return nil, cosmossdkerrors.Wrap(err, "failed to send fee to class owner")
				}
				k.Logger.Info("ClaimBid: Sent fee to class owner", "owner", classOwner, "fee", feeCoins.String())
			}
		}

		// Send remaining bid (bid - fee) to previous owner
		sellerAmount := sdk.NewCoins(bidAmount)
		if !feeCoins.IsZero() {
			sellerAmount = sellerAmount.Sub(feeCoins...)
		}
		if !sellerAmount.IsZero() {
			if err := k.bankKeeper.SendCoinsFromModuleToAccount(ctx, nameservice.ModuleName, currentOwnerAddr, sellerAmount); err != nil {
				k.Logger.Error("ClaimBid: Failed to transfer to seller", "amount", sellerAmount.String(), "error", err)
				return nil, cosmossdkerrors.Wrap(err, "failed to transfer bid amount to previous owner")
			}
			k.Logger.Info("ClaimBid: Transferred to seller", "amount", sellerAmount.String(), "owner", currentOwner)
		}
	}

	// Update the NFT data - set valuation to bid amount
	var valuationCoin sdk.Coin
	if !bidAmount.IsZero() {
		valuationCoin = bidAmount
	} else {
		// If CurrentBid is invalid, use the first allowed denomination with zero amount
		if len(classData.AllowedDenoms) > 0 {
			valuationCoin = sdk.NewCoin(classData.AllowedDenoms[0], math.ZeroInt())
		} else {
			k.Logger.Error("ClaimBid: No allowed denominations configured")
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "no allowed denominations configured")
		}
	}

	// Update valuation and expiry
	// Expiry is extended by 1 period if remaining <= period (bidder pays renewal fee)
	// If remaining > period, expiry preserved (can't accumulate >2× period)
	nftData.Valuation = valuationCoin
	nftData.ValuationExpiry = newExpiry

	// Clear the bid information
	nftData.CurrentBidder = ""
	nftData.CurrentBid = sdk.Coin{}
	nftData.BidTimestamp = nil
	// Clear bid height after claim
	nftData.BidHeight = 0

	// Reset NFT data for the new owner
	if err := k.SetNFTData(ctx, msg.NftClassId, msg.NftId, nftData); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update NFT data")
	}

	// --- Bid ledger update: mark active bid as CLAIMED and clear active index ---
	bidID, err := k.activeBidForNFT.Get(ctx, collections.Join(msg.NftClassId, msg.NftId))
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get active bid ID for NFT %s/%s", msg.NftClassId, msg.NftId)
	}
	rec, err := k.bids.Get(ctx, bidID)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get bid record %d", bidID)
	}
	rec.Status = nameservicev1.BidStatus_BID_CLAIMED
	if err := k.bids.Set(ctx, bidID, rec); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update bid record %d", bidID)
	}
	if err := k.activeBidForNFT.Remove(ctx, collections.Join(msg.NftClassId, msg.NftId)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to remove active bid index for NFT %s/%s", msg.NftClassId, msg.NftId)
	}

	// Transfer the NFT to the bidder
	err = k.nftKeeper.Transfer(ctx, msg.NftClassId, msg.NftId, bidderAddr)
	if err != nil {
		k.Logger.Error("ClaimBid: Failed to transfer NFT to bidder", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to transfer NFT to bidder")
	}

	// Emit event
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	err = sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventBidClaimed{
			ClassId: msg.NftClassId,
			NftId:   msg.NftId,
			Bidder:  msg.Bidder,
		})
	if err != nil {
		k.Logger.Error("ClaimBid: Failed to emit event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	k.Logger.Info("ClaimBid: Successfully claimed NFT",
		"nft_class_id", msg.NftClassId,
		"nft_id", msg.NftId,
		"bidder", msg.Bidder,
		"prev_owner", currentOwner)

	return &nameservicev1.MsgClaimBidResponse{}, nil
}
