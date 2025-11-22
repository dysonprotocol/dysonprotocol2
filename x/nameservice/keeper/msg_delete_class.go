package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// DeleteClass implements the MsgServer.DeleteClass method
func (k Keeper) DeleteClass(ctx context.Context, msg *nameservicev1.MsgDeleteClass) (*nameservicev1.MsgDeleteClassResponse, error) {
	// Verify destination-based authorization for root name of class ID
	if err := k.VerifyClassRootDestination(ctx, msg.ClassId, msg.NameDestination); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "authorization failed for class %s", msg.ClassId)
	}

	// Ensure class exists
	if !k.nftKeeper.HasClass(ctx, msg.ClassId) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "cannot delete: class not found: %s", msg.ClassId)
	}

	// Ensure the class has no NFTs
	if total := k.nftKeeper.GetTotalSupply(ctx, msg.ClassId); total != 0 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "cannot delete non-empty class %s: %d NFTs exist", msg.ClassId, total)
	}

	// Remove class from NFT module
	if err := k.nftKeeper.RemoveClass(ctx, msg.ClassId); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to delete NFT class: %s", msg.ClassId)
	}

	// Remove reverse index mapping for this class under its root name
	root := extractRootName(msg.ClassId)
	if err := k.RemoveClassByRootName(ctx, root, msg.ClassId); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to remove reverse index for class root name %s", root)
	}

	// Emit event
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if evErr := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventClassDeleted{ClassId: msg.ClassId},
	); evErr != nil {
		k.Logger.Error("failed to emit class deleted event", "error", evErr)
	}

	k.Logger.Info("Successfully deleted NFT class",
		"class_id", msg.ClassId,
		"name_destination", msg.NameDestination)

	return &nameservicev1.MsgDeleteClassResponse{}, nil
}

