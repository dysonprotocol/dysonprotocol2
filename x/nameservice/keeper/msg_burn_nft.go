package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// BurnNFT implements the MsgServer.BurnNFT method
func (k Keeper) BurnNFT(ctx context.Context, msg *nameservicev1.MsgBurnNFT) (*nameservicev1.MsgBurnNFTResponse, error) {
	// Verify destination-based authorization for root name of class ID
	if err := k.VerifyClassRootDestination(ctx, msg.ClassId, msg.NameDestination); err != nil {
		return nil, err
	}

	// Check if the NFT exists
	if !k.nftKeeper.HasNFT(ctx, msg.ClassId, msg.NftId) {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrNotFound,
			"NFT not found: %s/%s",
			msg.ClassId,
			msg.NftId,
		)
	}

	// Burn the NFT
	if err := k.nftKeeper.Burn(ctx, msg.ClassId, msg.NftId); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to burn NFT")
	}

	// Emit event using SDK context
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if evErr := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNFTBurned{
			ClassId: msg.ClassId,
			NftId:   msg.NftId,
		},
	); evErr != nil {
		k.Logger.Error("failed to emit NFT burned event", "error", evErr)
		return nil, cosmossdkerrors.Wrap(evErr, "failed to emit NFT burned event")
	}

	k.Logger.Info("Successfully burned NFT",
		"class_id", msg.ClassId,
		"id", msg.NftId,
		"name_destination", msg.NameDestination)

	return &nameservicev1.MsgBurnNFTResponse{}, nil
}

