package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	"dysonprotocol.com/x/nft"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// MintNFT implements the MsgServer.MintNFT method
func (k Keeper) MintNFT(ctx context.Context, msg *nameservicev1.MsgMintNFT) (*nameservicev1.MsgMintNFTResponse, error) {
	// Verify destination-based authorization for root name of class ID
	if err := k.VerifyClassRootDestination(ctx, msg.ClassId, msg.NameDestination); err != nil {
		return nil, err
	}

	// Check if the class exists
	if !k.nftKeeper.HasClass(ctx, msg.ClassId) {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrNotFound,
			"class not found: %s",
			msg.ClassId,
		)
	}

	// Check if NFT already exists
	if k.nftKeeper.HasNFT(ctx, msg.ClassId, msg.NftId) {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"NFT already exists in class %s with ID %s",
			msg.ClassId,
			msg.NftId,
		)
	}

	// Convert signer to account address
	ownerAddr, err := sdk.AccAddressFromBech32(msg.NameDestination)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid name_destination address: %s", msg.NameDestination)
	}

	// Create the NFT
	token := nft.NFT{
		ClassId: msg.ClassId,
		Id:      msg.NftId,
		Uri:     msg.Uri,
		UriHash: msg.UriHash,
	}

	// Mint the NFT first
	if err := k.nftKeeper.Mint(ctx, token, ownerAddr); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to mint NFT")
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Now set the NFT data after the NFT exists
	// Default ValuationExpiry to now + class valuation_period
	classData, err := k.GetNFTClassData(ctx, msg.ClassId)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to get class data for valuation expiry")
	}
	period := classData.ValuationPeriod
	if period <= 0 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "valuation_period not set for class %s", msg.ClassId)
	}
	nftData := nameservicev1.NFTData{
		Listed:          false,
		Valuation:       sdk.Coin{},
		ValuationExpiry: sdkCtx.BlockTime().Add(period),
		CurrentBidder:   "",
		CurrentBid:      sdk.Coin{},
		BidTimestamp:    nil,
		BidHeight:       0,
		Metadata:        "",
	}
	if err := k.SetNFTData(ctx, token.ClassId, token.Id, nftData); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set NFT data for class %s, id %s", token.ClassId, token.Id)
	}

	// Emit event using SDK context
	if evErr := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNFTMinted{
			ClassId: msg.ClassId,
			NftId:   msg.NftId,
		},
	); evErr != nil {
		k.Logger.Error("failed to emit NFT minted event", "error", evErr)
		return nil, cosmossdkerrors.Wrap(evErr, "failed to emit NFT minted event")
	}

	k.Logger.Info("Successfully minted NFT",
		"class_id", msg.ClassId,
		"id", msg.NftId,
		"name_destination", msg.NameDestination)

	return &nameservicev1.MsgMintNFTResponse{}, nil
}

