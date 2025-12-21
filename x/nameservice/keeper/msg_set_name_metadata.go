package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// SetNameMetadata allows the owner of a name (NFT in nameservice.dys) to set the metadata string
func (k Keeper) SetNameMetadata(ctx context.Context, msg *nameservicev1.MsgSetNameMetadata) (*nameservicev1.MsgSetNameMetadataResponse, error) {
	// BUG: Redundant NFT existence check - GetNFTData() below also checks NFT existence
	// This creates a potential race condition if NFT is deleted between the two checks.
	// The GetNFTData() call already handles the "not found" case with proper error wrapping,
	// so this early check is unnecessary and could cause inconsistent behavior.
	_, found := k.nftKeeper.GetNFT(ctx, k.NamesClassID(ctx), msg.Name)
	if !found {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrNotFound, "name not found")
	}

	// Verify the signer is the NFT owner (NOT destination)
	owner := k.nftKeeper.GetOwner(ctx, k.NamesClassID(ctx), msg.Name)
	if owner.String() != msg.Owner {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "only the owner can set metadata")
	}

	// Load current NFT data, set metadata string only
	nftData, err := k.GetNFTData(ctx, k.NamesClassID(ctx), msg.Name)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to load NFT data")
	}
	nftData.Metadata = msg.Metadata

	if err := nftData.ValidateBasic(); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invalid NFT data")
	}
	if err := k.SetNFTData(ctx, k.NamesClassID(ctx), msg.Name, nftData); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update NFT data")
	}

	// Emit event (re-use existing NFT metadata updated event)
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if evErr := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNFTMetadataUpdated{
			ClassId: k.NamesClassID(ctx),
			NftId:   msg.Name,
		},
	); evErr != nil {
		return nil, cosmossdkerrors.Wrap(evErr, "failed to emit NFT metadata updated event")
	}

	return &nameservicev1.MsgSetNameMetadataResponse{}, nil
}
