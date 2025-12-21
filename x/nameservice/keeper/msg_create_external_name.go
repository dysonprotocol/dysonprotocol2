package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	"dysonprotocol.com/x/nft"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// CreateExternalName implements the MsgServer.CreateExternalName method.
// This is a governance-only operation that creates a "bridged name" - a name NFT
// representing an external domain (e.g., example.com) or even a .dys name that
// bypasses the normal commit-reveal registration process.
//
// Note: .dys suffix names ARE allowed here intentionally. This enables governance
// to create reserved names (e.g., "dys.dys", "protocol.dys") without going through
// the standard registration flow. The ExternalNameRegex is a superset of NameRegex.
func (k Keeper) CreateExternalName(ctx context.Context, msg *nameservicev1.MsgCreateExternalName) (*nameservicev1.MsgCreateExternalNameResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Validate authority address
	if k.GetAuthority() != msg.Authority {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrUnauthorized, "invalid authority; expected %s, got %s", k.GetAuthority(), msg.Authority)
	}

	// Validate name is not empty
	if msg.Name == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "name cannot be empty")
	}

	// Validate name format using ExternalNameRegex (superset of NameRegex)
	// This allows both external domains (example.com) and .dys names (reserved.dys)
	if !nameservicev1.ExternalNameRegex.MatchString(msg.Name) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid external name format: must be lowercase alphanumeric with optional dashes (e.g., example.com, sub.domain.org, example)")
	}

	classID := k.NamesClassID(ctx)

	// Check if name is already registered
	if k.nftKeeper.HasNFT(ctx, classID, msg.Name) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "name is already registered")
	}

	// Ensure the Names NFT class exists
	if err := k.EnsureNamesClassExists(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to ensure names NFT class exists")
	}

	// Get authority address for NFT ownership
	authorityAddr, err := sdk.AccAddressFromBech32(msg.Authority)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid authority address: %s", msg.Authority)
	}

	// Get bond denom from staking params
	bondDenom, err := k.GetBondDenom(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to get bond denom")
	}

	// Create NFT data with zero valuation (external names don't have valuation)
	nftData := &nameservicev1.NFTData{
		Listed:          false, // External names are not listed by default
		Valuation:       sdk.NewCoin(bondDenom, math.ZeroInt()),
		ValuationExpiry: sdkCtx.BlockTime().AddDate(100, 0, 0), // Far future expiry
		Metadata:        "external_name",
	}

	// Marshal the NFT data
	nftDataAny, err := codectypes.NewAnyWithValue(nftData)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to marshal NFT data")
	}

	// Create the NFT
	token := nft.NFT{
		ClassId: classID,
		Id:      msg.Name,
		Uri:     msg.Authority,
		UriHash: "",
		Data:    nftDataAny,
	}

	// Mint the NFT to the authority
	if err := k.nftKeeper.Mint(ctx, token, authorityAddr); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to mint external name NFT")
	}

	// Emit event
	err = sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNameRegistered{
			Name: msg.Name,
			Fee:  sdk.Coins{}, // No fee for external names
		})
	if err != nil {
		k.Logger.Error("failed to emit external name registered event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit external name registered event")
	}

	return &nameservicev1.MsgCreateExternalNameResponse{}, nil
}
