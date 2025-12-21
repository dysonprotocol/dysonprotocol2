package keeper

import (
	"context"
	"time"

	cosmossdkerrors "cosmossdk.io/errors"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	"dysonprotocol.com/x/nft"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// Names NFT class constants
const (
	NamesClassURI = ""

	// CommitmentTTL is the maximum age of a commitment before it expires.
	// Commitments older than this are pruned in EndBlock and cannot be revealed.
	CommitmentTTL = time.Hour
)

// NamesClassID returns the NFT class ID for names (e.g., "nameservice.dys").
// Derived from the name suffix in params.
func (k Keeper) NamesClassID(ctx context.Context) string {
	return "nameservice" + k.GetNameSuffix(ctx)
}

// NamesClassName returns the human-readable name for the names NFT class.
func (k Keeper) NamesClassName(ctx context.Context) string {
	// Display denom is derived from suffix base (e.g., ".dys" -> "DYS" -> "DYS Names")
	base := k.GetNameSuffixBase(ctx)
	return toUpper(base) + " Names"
}

// NamesClassSymbol returns the symbol for the names NFT class.
func (k Keeper) NamesClassSymbol(ctx context.Context) string {
	base := k.GetNameSuffixBase(ctx)
	return toUpper(base) + "NAME"
}

// NamesClassDescription returns the description for the names NFT class.
func (k Keeper) NamesClassDescription(ctx context.Context) string {
	base := k.GetNameSuffixBase(ctx)
	return toUpper(base) + " Protocol registered names"
}

// toUpper converts a string to uppercase (simple ASCII conversion)
func toUpper(s string) string {
	result := make([]byte, len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c >= 'a' && c <= 'z' {
			result[i] = c - 32
		} else {
			result[i] = c
		}
	}
	return string(result)
}

// EnsureNamesClassExists ensures that the "nameservice" NFT class exists
// If it doesn't exist, it creates it with the module account as the owner
// It also ensures that an NFT with ID=NamesClassID exists and is owned by the authority
func (k Keeper) EnsureNamesClassExists(ctx context.Context) error {
	classID := k.NamesClassID(ctx)

	// Step 1: Ensure the NFT class exists
	if !k.nftKeeper.HasClass(ctx, classID) {
		// Create the NFT class with empty data first
		class := nft.Class{
			Id:          classID,
			Name:        k.NamesClassName(ctx),
			Symbol:      k.NamesClassSymbol(ctx),
			Description: k.NamesClassDescription(ctx),
			Uri:         NamesClassURI,
			UriHash:     "",
			Data:        nil, // We'll set this using SetNFTClassData after creating the class
		}

		// Save the class
		if err := k.nftKeeper.SaveClass(ctx, class); err != nil {
			return cosmossdkerrors.Wrap(err, "failed to save Names NFT class")
		}

		// Create NFT class data
		nftClassData := nameservicev1.NewNFTClassData()
		nftClassData.AlwaysListed = true                    // Names are always listed for sale
		nftClassData.ValuationFeePct = "0.01"               // 1% per valuation period by default
		nftClassData.ValuationPeriod = time.Hour * 24 * 365 // default 1 year
		// Seed per-class bidding defaults so core flows work out of the box
		// Use bond denom from staking params (canonical source of truth)
		bondDenom, err := k.GetBondDenom(ctx)
		if err != nil {
			return cosmossdkerrors.Wrap(err, "failed to get bond denom for names class")
		}
		nftClassData.AllowedDenoms = []string{bondDenom}
		nftClassData.BidTimeout = time.Second * 2
		nftClassData.RejectBidValuationFeePercent = "0.03"
		nftClassData.MinimumBidPercentIncrease = "0.01"

		// Use the SetNFTClassData helper function to set the class data
		if err := k.SetNFTClassData(ctx, classID, *nftClassData); err != nil {
			return cosmossdkerrors.Wrap(err, "failed to set NFT class data")
		}

		k.Logger.Info("Successfully created Names NFT class",
			"class_id", classID,
			"always_listed", nftClassData.AlwaysListed,
			"valuation_fee_pct", nftClassData.ValuationFeePct)
	}

	// Step 2: Ensure the authority NFT exists
	if !k.nftKeeper.HasNFT(ctx, classID, classID) {
		// Get the authority address
		authorityAddr, err := sdk.AccAddressFromBech32(k.GetAuthority())
		if err != nil {
			return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid authority address: %s", k.GetAuthority())
		}

		// Create the authority NFT with empty data first
		token := nft.NFT{
			ClassId: classID,
			Id:      classID,
			Uri:     authorityAddr.String(),
			UriHash: "",
			Data:    nil, // We'll set this using SetNFTData after minting
		}

		// Mint the authority NFT
		if err := k.nftKeeper.Mint(ctx, token, authorityAddr); err != nil {
			return cosmossdkerrors.Wrap(err, "failed to mint authority NFT")
		}

		// Create default NFT data
		nftData := nameservicev1.NewNFTData()
		nftData.Listed = false // Authority NFT is not listed by default

		// Use SetNFTData to set the NFT data
		if err := k.SetNFTData(ctx, classID, classID, *nftData); err != nil {
			return cosmossdkerrors.Wrapf(err, "failed to set NFT data for %s", classID)
		}

		// Maintain reverse index for this class under its root name
		root := extractRootName(classID)
		if err := k.SetClassByRootName(ctx, root, classID); err != nil {
			return cosmossdkerrors.Wrap(err, "failed to set reverse index for class root name")
		}

		k.Logger.Info("Successfully minted authority NFT",
			"owner", k.GetAuthority(),
			"class_id", classID,
			"nft_id", classID)
	}

	return nil
}

// MintNameNFT mints a new NFT in the names class for a registered name
func (k Keeper) MintNameNFT(ctx context.Context, name string, owner string) error {
	// Ensure the names class exists
	if err := k.EnsureNamesClassExists(ctx); err != nil {
		return err
	}

	classID := k.NamesClassID(ctx)

	// Convert owner to account address
	ownerAddr, err := sdk.AccAddressFromBech32(owner)
	if err != nil {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid owner address: %s", owner)
	}

	// Check if NFT already exists (should not normally happen)
	if k.nftKeeper.HasNFT(ctx, classID, name) {
		return cosmossdkerrors.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"NFT already exists in class %s with ID %s",
			classID,
			name,
		)
	}

	// Create the NFT with empty data first
	token := nft.NFT{
		ClassId: classID,
		Id:      name,
		Uri:     "", // Can be set to point to name metadata if needed
		UriHash: "",
		Data:    nil, // We'll set this using SetNFTData after minting
	}

	// Mint the NFT
	if err := k.nftKeeper.Mint(ctx, token, ownerAddr); err != nil {
		return cosmossdkerrors.Wrap(err, "failed to mint Name NFT")
	}

	// Create NFT data with default values
	nftData := nameservicev1.NewNFTData()
	nftData.Listed = true // Names are always listed by default

	// Use SetNFTData to set the NFT data
	if err := k.SetNFTData(ctx, classID, name, *nftData); err != nil {
		return cosmossdkerrors.Wrapf(err, "failed to set NFT data for %s", name)
	}

	k.Logger.Info("Successfully minted Name NFT",
		"owner", owner,
		"class_id", classID,
		"nft_id", name,
		"valuation", nftData.Valuation.String())

	return nil
}
