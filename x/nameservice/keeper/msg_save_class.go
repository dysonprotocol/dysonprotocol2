package keeper

import (
	"context"
	"strings"

	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	"dysonprotocol.com/x/nft"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// SaveClass implements the MsgServer.SaveClass method
func (k Keeper) SaveClass(ctx context.Context, msg *nameservicev1.MsgSaveClass) (*nameservicev1.MsgSaveClassResponse, error) {
	// Verify destination-based authorization for root name of class ID
	if err := k.VerifyClassRootDestination(ctx, msg.ClassId, msg.NameDestination); err != nil {
		return nil, err
	}

	// If the class already exists we treat this call as an **update** (upsert behaviour).
	if k.nftKeeper.HasClass(ctx, msg.ClassId) {
		// Fetch existing class
		existing, found := k.nftKeeper.GetClass(ctx, msg.ClassId)
		if !found {
			// This should never happen because HasClass returned true, but guard anyway
			return nil, cosmossdkerrors.Wrapf(
				sdkerrors.ErrNotFound,
				"class not found after HasClass=true: %s",
				msg.ClassId,
			)
		}

		// Merge non-blank fields coming from the message
		updated := existing // copy
		if strings.TrimSpace(msg.Name) != "" {
			updated.Name = msg.Name
		}
		if strings.TrimSpace(msg.Symbol) != "" {
			updated.Symbol = msg.Symbol
		}
		if strings.TrimSpace(msg.Description) != "" {
			updated.Description = msg.Description
		}
		if strings.TrimSpace(msg.Uri) != "" {
			updated.Uri = msg.Uri
		}
		if strings.TrimSpace(msg.UriHash) != "" {
			updated.UriHash = msg.UriHash
		}

		// Persist update
		if err := k.nftKeeper.UpdateClass(ctx, updated); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to update NFT class")
		}

		// Maintain reverse index for this class under its root name
		root := extractRootName(msg.ClassId)
		if err := k.SetClassByRootName(ctx, root, msg.ClassId); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to update reverse index for class root name")
		}

		// Emit event
		sdkCtx := sdk.UnwrapSDKContext(ctx)
		if evErr := sdkCtx.EventManager().EmitTypedEvent(
			&nameservicev1.EventClassSaved{ // reuse same event structure
				ClassId: msg.ClassId,
			},
		); evErr != nil {
			k.Logger.Error("failed to emit class updated event", "error", evErr)
			return nil, cosmossdkerrors.Wrap(evErr, "failed to emit class updated event")
		}

		k.Logger.Info("Successfully updated NFT class",
			"class_id", msg.ClassId,
			"name_destination", msg.NameDestination)

		return &nameservicev1.MsgSaveClassResponse{}, nil
	}

	// ------------------------------
	// Class does NOT yet exist → create new as before

	// 1. Validate class ID already done by verifyClassIDOwner

	// 2. Create the NFT class from supplied fields
	class := nft.Class{
		Id:          msg.ClassId,
		Name:        msg.Name,
		Symbol:      msg.Symbol,
		Description: msg.Description,
		Uri:         msg.Uri,
		UriHash:     msg.UriHash,
	}

	if err := k.nftKeeper.SaveClass(ctx, class); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to save NFT class")
	}

	// Set default per-class bidding params by copying from nameservice.dys
	if !k.nftKeeper.HasClass(ctx, k.NamesClassID(ctx)) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "default class %s not found to seed params", k.NamesClassID(ctx))
	}

	// Set default per-class bidding params by copying from nameservice.dys, they can be updated later
	defaultData, err := k.GetNFTClassData(ctx, k.NamesClassID(ctx))
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to get default class params from nameservice.dys")
	}

	if err := k.SetNFTClassData(ctx, msg.ClassId, defaultData); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to set default class params")
	}

	// Maintain reverse index for this class under its root name
	root := extractRootName(msg.ClassId)
	if err := k.SetClassByRootName(ctx, root, msg.ClassId); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to set reverse index for class root name")
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if evErr := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventClassSaved{ClassId: msg.ClassId},
	); evErr != nil {
		k.Logger.Error("failed to emit class saved event", "error", evErr)
		return nil, cosmossdkerrors.Wrap(evErr, "failed to emit class saved event")
	}

	k.Logger.Info("Successfully created NFT class",
		"class_id", msg.ClassId,
		"name_destination", msg.NameDestination)

	return &nameservicev1.MsgSaveClassResponse{}, nil
}

