package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// SetDestination implements the MsgServer.SetDestination method
func (k Keeper) SetDestination(ctx context.Context, msg *nameservicev1.MsgSetDestination) (*nameservicev1.MsgSetDestinationResponse, error) {
	k.Logger.Info("SetDestination: Processing request", "name", msg.Name, "owner", msg.Owner, "destination", msg.Destination)

	// Get the name NFT
	nameNFT, found := k.nftKeeper.GetNFT(ctx, k.NamesClassID(ctx), msg.Name)
	if !found {
		k.Logger.Error("SetDestination: Name NFT not found", "name", msg.Name)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrNotFound, "name not found")
	}

	// Get the owner of the NFT
	owner := k.nftKeeper.GetOwner(ctx, k.NamesClassID(ctx), msg.Name)
	ownerStr := owner.String()
	k.Logger.Info("SetDestination: Found name NFT", "name", msg.Name, "owner", ownerStr)

	// Verify owner
	if ownerStr != msg.Owner {
		k.Logger.Error("SetDestination: Unauthorized - not the owner", "name", msg.Name, "nft_owner", ownerStr, "msg_owner", msg.Owner)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "only the owner can set the destination")
	}

	// Store the old destination to update reverse mappings
	oldDestination := nameNFT.Uri
	k.Logger.Info("SetDestination: Current destination", "name", msg.Name, "old_destination", oldDestination, "new_destination", msg.Destination)

	// Validate the destination BEFORE updating the NFT
	if msg.Destination != "" {
		// Check if destination is a valid bech32 address
		_, err := sdk.AccAddressFromBech32(msg.Destination)
		if err != nil {
			k.Logger.Info("SetDestination: Destination is not a valid bech32 address, checking if it's an existing name", "destination", msg.Destination, "error", err)
			// Not a valid address, check if it's an existing name
			_, found := k.nftKeeper.GetNFT(ctx, k.NamesClassID(ctx), msg.Destination)
			k.Logger.Info("SetDestination: Checked for existing name", "destination", msg.Destination, "found", found)
			if !found {
				k.Logger.Error("SetDestination: Invalid destination - not a valid address or existing name", "destination", msg.Destination)
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "destination must be a valid bech32 address or existing name")
			}
			k.Logger.Info("SetDestination: Destination is an existing name", "destination", msg.Destination)

			// Verify the destination name chain resolves properly and doesn't create a cycle
			// Check for self-reference
			if msg.Destination == msg.Name {
				k.Logger.Error("SetDestination: Self-reference detected", "name", msg.Name)
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "name cannot point to itself")
			}

			// Check that the destination chain resolves and doesn't include this name (circular)
			// Also enforce max depth of 10 to prevent excessively long chains
			// The chain includes: source name -> destination -> ... -> terminal address
			// A chain of 10 names total (source + 9 intermediate) is the maximum allowed
			// The 10th name must resolve to an address, not another name
			visited := map[string]bool{msg.Name: true} // Include source name to detect cycles
			current := msg.Destination
			const maxDepth = 9 // Max 9 intermediate names (10 total including source)
			depth := 1         // Count the source -> destination hop
			for depth <= maxDepth {
				if visited[current] {
					k.Logger.Error("SetDestination: Circular reference detected", "name", msg.Name, "destination", msg.Destination, "cycle_at", current)
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "destination creates circular name chain")
				}
				visited[current] = true

				// Check if current resolves to an address (terminal)
				if _, addrErr := sdk.AccAddressFromBech32(current); addrErr == nil {
					break // Reached a terminal address - chain is valid
				}

				// Not an address, so it's another name - increment depth
				depth++
				if depth > maxDepth {
					k.Logger.Error("SetDestination: Chain exceeds maximum depth", "name", msg.Name, "destination", msg.Destination, "depth", depth)
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "destination chain exceeds maximum depth of 10")
				}

				// Get the next hop
				destNFT, destFound := k.nftKeeper.GetNFT(ctx, k.NamesClassID(ctx), current)
				if !destFound {
					k.Logger.Error("SetDestination: Name in chain not found", "name", current)
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "destination chain contains unresolvable name")
				}
				if destNFT.Uri == "" {
					k.Logger.Error("SetDestination: Name in chain has no destination", "name", current)
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "destination chain contains name with no destination")
				}
				current = destNFT.Uri
			}
			k.Logger.Info("SetDestination: Destination chain validated", "name", msg.Name, "destination", msg.Destination, "depth", depth)
		} else {
			k.Logger.Info("SetDestination: Destination is a valid bech32 address", "destination", msg.Destination)
		}
	}

	// Update the NFT (validation passed)
	nameNFT.Uri = msg.Destination
	if err := k.nftKeeper.Update(ctx, nameNFT); err != nil {
		k.Logger.Error("SetDestination: Failed to update NFT", "name", msg.Name, "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to update NFT")
	}

	// Update reverse mappings
	// Remove old mapping if it exists and is not empty
	if oldDestination != "" {
		if err := k.RemoveNameDestinationMapping(ctx, oldDestination, msg.Name); err != nil {
			k.Logger.Error("SetDestination: Failed to remove old reverse mapping", "old_destination", oldDestination, "name", msg.Name, "error", err)
			// Don't fail the transaction for reverse mapping errors, just log
		} else {
			k.Logger.Info("SetDestination: Removed old reverse mapping", "old_destination", oldDestination, "name", msg.Name)
		}
	}

	// Add new mapping if destination is not empty
	if msg.Destination != "" {
		if err := k.SetNameDestinationMapping(ctx, msg.Destination, msg.Name); err != nil {
			k.Logger.Error("SetDestination: Failed to add new reverse mapping", "new_destination", msg.Destination, "name", msg.Name, "error", err)
			// Don't fail the transaction for reverse mapping errors, just log
		} else {
			k.Logger.Info("SetDestination: Added new reverse mapping", "new_destination", msg.Destination, "name", msg.Name)
		}
	}

	k.Logger.Info("SetDestination: Successfully updated name NFT", "name", msg.Name, "destination", nameNFT.Uri)

	// Emit event
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	err := sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNameDestinationSet{
			Name:        msg.Name,
			Destination: nameNFT.Uri,
		})
	if err != nil {
		k.Logger.Error("failed to emit name destination set event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit name destination set event")
	}

	return &nameservicev1.MsgSetDestinationResponse{}, nil
}
