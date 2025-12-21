package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"

	nameservicev1 "dysonprotocol.com/x/nameservice/types"
)

// SetNFTMetadata handles a MsgSetNFTMetadata message
func (k Keeper) SetNFTMetadata(ctx context.Context, msg *nameservicev1.MsgSetNFTMetadata) (*nameservicev1.MsgSetNFTMetadataResponse, error) {
	// Verify authorization: signer must match resolved destination of class root name
	if err := k.VerifyClassRootDestination(ctx, msg.ClassId, msg.NameDestination); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "unauthorized to set NFT metadata")
	}

	// Get current NFT data
	nftData, err := k.GetNFTData(ctx, msg.ClassId, msg.NftId)
	if err != nil {
		k.Logger.Error("SetNFTMetadata: Failed to get NFT data",
			"class_id", msg.ClassId,
			"nft_id", msg.NftId,
			"error", err)
		return nil, cosmossdkerrors.Wrapf(
			err,
			"NFT not found class %s, id %s",
			msg.ClassId,
			msg.NftId,
		)
	}
	k.Logger.Info("SetNFTMetadata: setting metadata", "class_id", msg.ClassId, "nft_id", msg.NftId, "nftData", nftData)
	// Update the metadata field
	nftData.Metadata = msg.Metadata

	// Always update the URI and URI hash fields (even if empty)
	// Get the current NFT from the nft module to update its URI/URI hash
	nft, found := k.nftKeeper.GetNFT(ctx, msg.ClassId, msg.NftId)
	if !found {
		return nil, cosmossdkerrors.Wrapf(
			sdkerrors.ErrNotFound,
			"NFT not found in nft module: class %s, id %s",
			msg.ClassId,
			msg.NftId,
		)
	}

	// Store the old URI for reverse mapping updates
	oldUri := nft.Uri
	k.Logger.Info("SetNFTMetadata: URI/URIHash change", "class_id", msg.ClassId, "nft_id", msg.NftId, "old_uri", oldUri, "new_uri", msg.Uri)

	// Update the URI and URI hash and save it back
	nft.Uri = msg.Uri
	nft.UriHash = msg.UriHash

	// Get the owner of the NFT and update it
	owner := k.nftKeeper.GetOwner(ctx, msg.ClassId, msg.NftId)
	if err := k.nftKeeper.Update(ctx, nft); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update NFT URI/URI hash for class %s, id %s", msg.ClassId, msg.NftId)
	}

	// Update reverse mappings for name NFTs only
	if msg.ClassId == k.NamesClassID(ctx) {
		// Remove old mapping if it exists and is not empty
		if oldUri != "" {
			if err := k.RemoveNameDestinationMapping(ctx, oldUri, msg.NftId); err != nil {
				k.Logger.Error("SetNFTMetadata: Failed to remove old reverse mapping", "old_uri", oldUri, "name", msg.NftId, "error", err)
				// Don't fail the transaction for reverse mapping errors, just log
			} else {
				k.Logger.Info("SetNFTMetadata: Removed old reverse mapping", "old_uri", oldUri, "name", msg.NftId)
			}
		}

		// Add new mapping only if new URI is not empty
		if msg.Uri != "" {
			if err := k.SetNameDestinationMapping(ctx, msg.Uri, msg.NftId); err != nil {
				k.Logger.Error("SetNFTMetadata: Failed to add new reverse mapping", "new_uri", msg.Uri, "name", msg.NftId, "error", err)
				// Don't fail the transaction for reverse mapping errors, just log
			} else {
				k.Logger.Info("SetNFTMetadata: Added new reverse mapping", "new_uri", msg.Uri, "name", msg.NftId)
			}
		}
	}

	k.Logger.Info("SetNFTMetadata: updated URI and URI hash", "class_id", msg.ClassId, "nft_id", msg.NftId, "uri", msg.Uri, "uri_hash", msg.UriHash, "owner", owner.String())

	k.Logger.Info("SetNFTMetadata: Validate Basic")
	// Validate the updated NFT data
	if err := nftData.ValidateBasic(); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid NFT data for class %s, id %s", msg.ClassId, msg.NftId)
	}

	k.Logger.Info("SetNFTMetadata: SetNFTData")
	// Set the updated NFT data
	if err := k.SetNFTData(ctx, msg.ClassId, msg.NftId, nftData); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to update NFT data for class %s, id %s", msg.ClassId, msg.NftId)
	}

	// Emit event
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if evErr := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNFTMetadataUpdated{
			ClassId: msg.ClassId,
			NftId:   msg.NftId,
		},
	); evErr != nil {
		k.Logger.Error("failed to emit NFT metadata updated event", "error", evErr)
		return nil, cosmossdkerrors.Wrap(evErr, "failed to emit NFT metadata updated event")
	}

	k.Logger.Info("Successfully updated NFT metadata",
		"class_id", msg.ClassId,
		"nft_id", msg.NftId,
		"name_destination", msg.NameDestination)

	return &nameservicev1.MsgSetNFTMetadataResponse{}, nil
}
