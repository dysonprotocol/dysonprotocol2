package keeper

import (
	"context"
	"time"

	cosmossdkerrors "cosmossdk.io/errors"
	math "cosmossdk.io/math"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// Renew extends the valuation expiry period for an NFT by charging proportional fees.
//
// Semantics:
//   - Extends NFT valuation expiry by one full valuation period.
//   - Charges annual valuation fee proportionally based on the renewal duration.
//   - Fee is calculated as: valuation × fee_percent × (renewal_period / valuation_period).
//   - Handles retroactive renewal if expiry has already passed.
//   - Fee is paid to the NFT class owner.
//
// Validation:
//   - Payer address must be valid bech32.
//   - NFT must exist and have valid valuation.
//   - Class must have valuation period and fee percentage configured.
//
// State Updates:
//   - Extends NFT valuation expiry by class valuation period.
//   - Charges proportional fee from payer to NFT class owner.
//
// Emits:
//   - EventNameRenewed(name, new_expiry) on successful renewal.
//
// Returns:
//   - *nameservicev1.MsgRenewResponse with the new expiry timestamp.
//
// Errors are returned on invalid addresses, NFT not found, invalid valuation, missing class config, or fee transfer failures; no panics.
func (k Keeper) Renew(ctx context.Context, msg *nameservicev1.MsgRenew) (*nameservicev1.MsgRenewResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Validate addresses
	payerAddr, err := sdk.AccAddressFromBech32(msg.Payer)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid payer address: %s", msg.Payer)
	}

	// Get the current NFT data
	nftData, err := k.GetNFTData(ctx, msg.NftClassId, msg.NftId)
	if err != nil {
		k.Logger.Error("Renew: Failed to get NFT data",
			"nft_class_id", msg.NftClassId,
			"nft_id", msg.NftId,
			"error", err)
		return nil, cosmossdkerrors.Wrapf(err, "failed to get NFT data for %s", msg.NftId)
	}

	// Validate the valuation from NFT data
	err = k.ValidateValuation(ctx, msg.NftClassId, nftData.Valuation)
	if err != nil {
		return nil, err
	}

	// Get class data for fee and period
	classData, err := k.GetNFTClassData(ctx, msg.NftClassId)
	if err != nil {
		k.Logger.Error("Renew: Failed to get class data", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to get class data for renewal")
	}
	feePercent := classData.ValuationFeePct

	// Convert the single coin to a DecCoins for precise math operations
	decValuation := sdk.NewDecCoinsFromCoins(nftData.Valuation)

	// Calculate the current time and determine the renewal period start time
	currentTime := sdkCtx.BlockTime()

	// Use the later of current expiry and current time as the baseline to avoid negative intervals
	baseTime := nftData.ValuationExpiry
	if baseTime.Before(currentTime) {
		baseTime = currentTime
	}

	period := classData.ValuationPeriod
	if period <= 0 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "valuation_period not set for class %s", msg.NftClassId)
	}
	// Set new expiry to baseline plus valuation_period (never shortens an already-future expiry)
	newExpiry := baseTime.Add(period)

	// Calculate the exact renewal period in seconds using math.Int for precision
	// Charge retroactively for any time elapsed since the previous expiry, plus the newly added period
	renewalPeriodSeconds := math.NewInt(newExpiry.Unix() - nftData.ValuationExpiry.Unix())

	// Calculate the proportion of one valuation_period we're renewing for
	denomSeconds := math.NewInt(int64(period / time.Second))
	periodProportion := math.LegacyNewDecFromInt(renewalPeriodSeconds).Quo(math.LegacyNewDecFromInt(denomSeconds))

	// Convert to LegacyDec for compatibility with SDK DecCoins methods
	legacyFeePercentDec, err := math.LegacyNewDecFromStr(feePercent)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to convert fee percentage to legacy decimal")
	}

	// Calculate fee by multiplying the valuation by fee percentage and the period proportion
	decFees := decValuation.MulDec(legacyFeePercentDec).MulDec(periodProportion)

	// Convert back to regular Coins for blockchain transactions
	fee, _ := decFees.TruncateDecimal()

	// Charge the fee
	if !fee.IsZero() {
		// Get the owner of the NFT class using GetDenomOwner
		classOwner, _, err := k.GetDenomOwner(sdkCtx, msg.NftClassId)
		if err != nil {
			k.Logger.Error("Renew: Failed to get NFT class owner", "class_id", msg.NftClassId, "error", err)
			return nil, cosmossdkerrors.Wrap(err, "failed to get NFT class owner")
		}

		// Check if the owner is the authority (governance module)
		if classOwner == k.GetAuthority() {
			// Send fee to community pool
			k.Logger.Info("Renew: Sending fee to community pool", "fee", fee.String())
			err = k.communityPoolKeeper.FundCommunityPool(ctx, fee, payerAddr)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to send fee to community pool")
			}
		} else {
			// Send fee to the owner of the NFT class
			k.Logger.Info("Renew: Sending fee to NFT class owner", "owner", classOwner, "fee", fee.String())
			classOwnerAddr, err := sdk.AccAddressFromBech32(classOwner)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to parse NFT class owner address")
			}
			err = k.bankKeeper.SendCoins(ctx, payerAddr, classOwnerAddr, fee)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to send fee to NFT class owner")
			}
		}
	}

	// Update expiry in NFT data
	nftData.ValuationExpiry = newExpiry

	// Update the NFT data
	if err := k.SetNFTData(ctx, msg.NftClassId, msg.NftId, nftData); err != nil {
		k.Logger.Error("Renew: Failed to set NFT data",
			"nft_class_id", msg.NftClassId,
			"nft_id", msg.NftId,
			"error", err)
		return nil, cosmossdkerrors.Wrapf(err, "failed to update NFT data for %s", msg.NftId)
	}

	// Emit event
	err = sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNameRenewed{
			Name:      msg.NftId,
			NewExpiry: newExpiry,
		})
	if err != nil {
		k.Logger.Error("failed to emit name renewed event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit name renewed event")
	}

	return &nameservicev1.MsgRenewResponse{
		Expiry: newExpiry,
	}, nil
}
