package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	math "cosmossdk.io/math"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

const (
	SecondsInYear = 31536000
)

// SetValuation updates the self-valuation of an NFT owned by the sender.
//
// Semantics:
//   - Updates the valuation of an owned NFT, triggering Harberger tax payments.
//   - Only charges fee on incremental valuation increases (not decreases).
//   - Calculates pro-rated fee based on remaining time in current valuation period.
//   - Fee goes to class owner or community pool for governance-owned classes.
//   - Valuation expiry remains unchanged (only extended via MsgRenew).
//
// Validation:
//   - NFT must exist and not be expired.
//   - Sender must be the current NFT owner.
//   - No active bids can exist (must reject bids first).
//   - New valuation must be valid according to class rules.
//   - Max valuation fee percent guard (if provided) must not be exceeded.
//
// State Updates:
//   - Updates NFT valuation data with new valuation amount.
//   - If valuation was previously unset, sets initial expiry to 1 year.
//   - Transfers pro-rated fee from NFT owner to appropriate recipient.
//
// Emits:
//   - EventNameValuationUpdated(name, new_valuation) on successful update.
//
// Returns:
//   - *nameservicev1.MsgSetValuationResponse (empty response indicating success).
//
// Errors are returned on NFT not found, expired valuation, unauthorized sender, active bids, invalid valuation, or fee calculation/transfer failures; no panics.
func (k Keeper) SetValuation(ctx context.Context, msg *nameservicev1.MsgSetValuation) (*nameservicev1.MsgSetValuationResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	k.Logger.Info("SetValuation: Processing", "class_id", msg.NftClassId, "nft_id", msg.NftId, "owner", msg.Owner, "valuation", msg.Valuation.String())

	// Extract the NFT data
	nftData, err := k.GetNFTData(ctx, msg.NftClassId, msg.NftId)
	if err != nil {
		k.Logger.Error("SetValuation: NFT not found", "class_id", msg.NftClassId, "nft_id", msg.NftId, "error", err)
		return nil, cosmossdkerrors.Wrapf(err, "failed to get NFT data")
	}

	// If the NFT is expired, return an error
	if nftData.ValuationExpiry.Before(sdkCtx.BlockTime()) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "NFT valuation is expired, use MsgRenew to renew the expiry before setting a new valuation")
	}

	// Get the current owner of the NFT
	ownerAddr := k.nftKeeper.GetOwner(ctx, msg.NftClassId, msg.NftId)
	nftOwner := ownerAddr.String()

	// Convert message sender address
	msgOwnerAddr, err := sdk.AccAddressFromBech32(msg.Owner)
	if err != nil {
		k.Logger.Error("SetValuation: Invalid owner address", "owner", msg.Owner, "error", err)
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid owner address: %s", msg.Owner)
	}

	// Verify that message owner is the NFT owner
	if nftOwner != msg.Owner {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrUnauthorized, "only the NFT owner can set valuation: NFT owner %s != message sender %s", nftOwner, msg.Owner)
	}

	// Validate the valuation using the keeper's validation method
	if err := k.ValidateValuation(ctx, msg.NftClassId, msg.Valuation); err != nil {
		return nil, err
	}

	// -------------------------------------------------------------------
	// Active Bid Check: Disallow valuation change if a bid exists
	// -------------------------------------------------------------------
	if nftData.CurrentBidder != "" {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
			"cannot set valuation while there is an active bid, use MsgRejectBid to reject the bid with a new valuation")
	}

	// Fetch NFT class data to obtain valuation fee parameters for fee calculation
	classData, err := k.GetNFTClassData(ctx, msg.NftClassId)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to get NFT class data for fee calculation")
	}

	feePercentStr := "0"
	if classData.ValuationFeePct != "" {
		feePercentStr = classData.ValuationFeePct
	}
	k.Logger.Info("SetValuation: fee inputs",
		"class_id", msg.NftClassId,
		"nft_id", msg.NftId,
		"valuation_fee_pct_raw", feePercentStr,
		"valuation_period", classData.ValuationPeriod.String(),
		"valuation_expiry", nftData.ValuationExpiry.String(),
	)

	// Calculate the incremental valuation (only if increasing)
	var oldValuation sdk.Coins
	if nftData.Valuation.Amount.IsNil() || nftData.Valuation.Denom == "" {
		oldValuation = sdk.NewCoins()
	} else {
		oldValuation = sdk.NewCoins(nftData.Valuation)
	}
	newValuation := sdk.NewCoins(msg.Valuation)

	// Only charge fee if there's an incremental valuation increase
	if newValuation.IsAllGT(oldValuation) {
		// Calculate the difference between new and old valuation
		incrementalValuation := newValuation.Sub(oldValuation...)

		// Get current and expiry time
		// Note: remainingSeconds is guaranteed positive due to expiry check at function start (line 58)
		currentTime := sdkCtx.BlockTime()
		expiryTime := nftData.ValuationExpiry
		remainingSeconds := expiryTime.Unix() - currentTime.Unix()
		periodSeconds := int64(classData.ValuationPeriod.Seconds())
		if periodSeconds <= 0 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "valuation_period not set for class %s", msg.NftClassId)
		}
		portionRemaining := math.LegacyNewDecFromInt(math.NewInt(remainingSeconds)).
			Quo(math.LegacyNewDecFromInt(math.NewInt(periodSeconds)))

		// Convert the percentage string to a decimal
		feePercent, err := math.LegacyNewDecFromStr(feePercentStr)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to parse annual valuation fee percent")
		}

		// Calculate fee: incremental_valuation * fee_percent * time_proportion
		decValuationDiff := sdk.NewDecCoinsFromCoins(incrementalValuation...)
		decAnnualFee := decValuationDiff.MulDec(feePercent)
		decProportionalFee := decAnnualFee.MulDec(portionRemaining)
		feeCoins, _ := decProportionalFee.TruncateDecimal()

		k.Logger.Info("SetValuation: fee calc",
			"class_id", msg.NftClassId,
			"nft_id", msg.NftId,
			"old_valuation", oldValuation.String(),
			"new_valuation", newValuation.String(),
			"incremental_valuation", incrementalValuation.String(),
			"remaining_seconds", remainingSeconds,
			"period_seconds", periodSeconds,
			"time_proportion", portionRemaining.String(),
			"valuation_fee_pct_dec", feePercent.String(),
			"fee", feeCoins.String())

		// Check if fee exceeds max_valuation_fee_pct
		if msg.MaxValuationFeePct != "" {
			maxPct, err := math.LegacyNewDecFromStr(msg.MaxValuationFeePct)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
					"invalid max_valuation_fee_pct format: %s", msg.MaxValuationFeePct)
			}

			if feePercent.GT(maxPct) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
					"calculated valuation fee percentage %s exceeds maximum allowed %s",
					feePercent.String(), maxPct.String())
			}
		}

		// Get the owner of the NFT class using GetDenomOwner
		classOwner, _, err := k.GetDenomOwner(sdkCtx, msg.NftClassId)
		if err != nil {
			k.Logger.Error("SetValuation: Failed to get NFT class owner", "class_id", msg.NftClassId, "error", err)
			return nil, cosmossdkerrors.Wrap(err, "failed to get NFT class owner")
		}

		// Check if the owner is the authority (governance module)
		if classOwner == k.GetAuthority() {
			// Send fee to community pool
			k.Logger.Info("SetValuation: Sending fee to community pool", "fee", feeCoins.String())
			err = k.communityPoolKeeper.FundCommunityPool(ctx, feeCoins, msgOwnerAddr)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to send fee to community pool")
			}
		} else {
			// Send fee to the owner of the NFT class
			k.Logger.Info("SetValuation: Sending fee to NFT class owner", "owner", classOwner, "fee", feeCoins.String())
			classOwnerAddr, err := sdk.AccAddressFromBech32(classOwner)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to parse NFT class owner address")
			}
			err = k.bankKeeper.SendCoins(ctx, msgOwnerAddr, classOwnerAddr, feeCoins)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to send fee to NFT class owner")
			}
		}
	}

	// Update NFT data
	// Note: expiry is preserved as-is. Use MsgRenew to extend expiry.
	// The expiry check at function start ensures expiry is not zero/past.
	nftData.Valuation = msg.Valuation

	// Update the NFT data
	if err := k.SetNFTData(ctx, msg.NftClassId, msg.NftId, nftData); err != nil {
		k.Logger.Error("SetValuation: Failed to update NFT data", "error", err)
		return nil, cosmossdkerrors.Wrapf(err, "failed to update NFT data")
	}

	// Emit event
	err = sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNameValuationUpdated{
			Name:         msg.NftId,
			NewValuation: &msg.Valuation,
		})
	if err != nil {
		k.Logger.Error("failed to emit valuation updated event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit valuation updated event")
	}

	k.Logger.Info("SetValuation: Completed successfully",
		"class_id", msg.NftClassId,
		"nft_id", msg.NftId,
		"new_valuation", msg.Valuation.String())

	return &nameservicev1.MsgSetValuationResponse{}, nil
}
