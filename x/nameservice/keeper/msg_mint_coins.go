package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservice "dysonprotocol.com/x/nameservice"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// MintCoins implements the MsgServer.MintCoins method
func (k Keeper) MintCoins(ctx context.Context, msg *nameservicev1.MsgMintCoins) (*nameservicev1.MsgMintCoinsResponse, error) {
	// 1. Validate signer address
	ownerAddr, err := sdk.AccAddressFromBech32(msg.NameDestination)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid name_destination address: %s", msg.NameDestination)
	}

	// 2. Validate coins
	if msg.Amount.Empty() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "no coins to mint")
	}

	// Regex for valid coin denom format - centralized in types
	validDenomPattern := nameservicev1.ValidDenomRegex

	// 3. For each coin, verify that the owner owns the root name
	for _, coin := range msg.Amount {
		// Validate coin denom with regex
		if !validDenomPattern.MatchString(coin.Denom) {
			return nil, cosmossdkerrors.Wrapf(
				sdkerrors.ErrInvalidRequest,
				"invalid denom format, must match pattern: %s",
				validDenomPattern.String(),
			)
		}

		// Verify the sender controls the destination for the denom's root name
		if err := k.VerifyDenomDestination(ctx, coin.Denom, msg.NameDestination); err != nil {
			return nil, err
		}
	}

	// 4. Calculate and collect minting fee (skip if destination is a module account)
	// Detect module account destination
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	isModuleDest := false
	if acc := k.accountKeeper.GetAccount(sdkCtx, ownerAddr); acc != nil {
		if modAcc, ok := acc.(sdk.ModuleAccountI); ok {
			modAccAddr := modAcc.GetAddress()
			if modAccAddr.Equals(ownerAddr) {
				// if the module account address is the same as the owner address, then it is a module destination
				isModuleDest = true
			} else {
				// this should never happen
				k.Logger.Error("MintCoins: Module account address does not match owner address", "module_account_address", modAccAddr.String(), "owner_address", ownerAddr.String())
			}
		}
	}

	params := k.GetParams(ctx)
	mintFeePerCoin, err := params.GetMintFeePerCoinAsDec()
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to parse mint fee per coin")
	}

	var feeCharged sdk.Coins
	if !isModuleDest && !mintFeePerCoin.IsZero() {
		// Calculate total fee: total_units_minted × mint_fee_per_coin
		totalUnits := math.NewInt(0)
		for _, coin := range msg.Amount {
			totalUnits = totalUnits.Add(coin.Amount)
		}
		// Round up to the closest int
		totalFeeAmount := mintFeePerCoin.MulInt(totalUnits).Ceil().TruncateInt()

		// Explicit authorization: require provided mint_fee >= required
		// Use bond denom from staking params (canonical source of truth)
		baseDenom, err := k.GetBondDenom(ctx)
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to get bond denom")
		}
		if msg.MintFee.Denom != baseDenom {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "mint_fee denom must be '%s', got %s", baseDenom, msg.MintFee.Denom)
		}
		if msg.MintFee.Amount.LT(totalFeeAmount) {
			return nil, cosmossdkerrors.Wrapf(
				sdkerrors.ErrInsufficientFee,
				"mint_fee amount %s is less than required fee %s",
				msg.MintFee.Amount.String(), totalFeeAmount.String(),
			)
		}

		if !totalFeeAmount.IsZero() {
			feeCharged = sdk.NewCoins(sdk.NewCoin(baseDenom, totalFeeAmount))

			// Collect fee to community pool before minting
			if err := k.communityPoolKeeper.FundCommunityPool(ctx, feeCharged, ownerAddr); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to fund community pool with minting fee")
			}

			k.Logger.Info("MintCoins: Collected minting fee",
				"name_destination", msg.NameDestination,
				"units_minted", totalUnits.String(),
				"fee_charged", feeCharged.String())
		}
	} else if isModuleDest {
		k.Logger.Info("MintCoins: Skipping mint fee for module destination", "name_destination", msg.NameDestination)
	}

	// 5. Mint the coins to the module account
	err = k.bankKeeper.MintCoins(ctx, nameservice.ModuleName, msg.Amount)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to mint coins")
	}

	// 6. Send the minted coins from the module to the owner
	moduleAddr := k.accountKeeper.GetModuleAddress(nameservice.ModuleName)
	err = k.bankKeeper.SendCoins(ctx, moduleAddr, ownerAddr, msg.Amount)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to send minted coins to owner")
	}

	// 6b. Ensure denom entries exist in reverse index. Bank module holds supply, we only index on first mint.
	for _, coin := range msg.Amount {
		// auto-create denom metadata on first mint
		k.ensureDenomMetadata(ctx, coin.Denom)
		if err := k.setDenomTracked(ctx, coin.Denom); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to index denom %s", coin.Denom)
		}
	}

	// 7. Emit empty event (fields removed)
	if evErr := sdk.UnwrapSDKContext(ctx).EventManager().EmitTypedEvent(
		&nameservicev1.EventCoinsMinted{},
	); evErr != nil {
		k.Logger.Error("failed to emit coins minted event", "error", evErr)
		return nil, cosmossdkerrors.Wrap(evErr, "failed to emit coins minted event")
	}

	k.Logger.Info("MintCoins: Successfully minted coins", "name_destination", msg.NameDestination, "amount", msg.Amount.String())

	return &nameservicev1.MsgMintCoinsResponse{}, nil
}
