package keeper

import (
	"context"
	"strings"

	cosmossdkerrors "cosmossdk.io/errors"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"golang.org/x/text/cases"
	"golang.org/x/text/language"
)

// GetDenomOwner extracts the owner address for a given denom
// A denom in the nameservice follows the pattern "name.dys" or "name.dys/subdenom"
// where the name before any slash is a registered name in the nameservice
// Returns the owner address and nil if successful, or empty string and error if not
func (k Keeper) GetDenomOwner(ctx sdk.Context, denom string) (string, string, error) {
	k.Logger.Info("GetDenomOwner called", "denom", denom)

	rootName := extractRootName(denom)
	k.Logger.Info("Extracted root name", "rootName", rootName)

	// Check if it's a valid nameservice name (must end with configured suffix)
	suffix := k.GetNameSuffix(ctx)
	if !strings.HasSuffix(rootName, suffix) {
		k.Logger.Error("Invalid denom format", "rootName", rootName)
		return "", "", cosmossdkerrors.Wrapf(
			sdkerrors.ErrInvalidRequest,
			"invalid denom format, root name must be a valid %s name: %s",
			suffix, rootName,
		)
	}

	// Check if the name exists and get its owner
	owner, found := k.GetNameOwner(ctx, rootName)
	if !found {
		k.Logger.Error("Root name not found", "rootName", rootName)
		return "", "", cosmossdkerrors.Wrapf(
			sdkerrors.ErrNotFound,
			"root name not found: %s",
			rootName,
		)
	}

	k.Logger.Info("Found name", "name", rootName, "owner", owner)

	// Return the owner of the name
	return owner, rootName, nil
}

// VerifyDenomOwner checks if the provided address is the owner of the denom
// Returns nil if the address is the owner, or an error if not
func (k Keeper) VerifyDenomOwner(ctx sdk.Context, denom string, address string) error {
	k.Logger.Info("VerifyDenomOwner called", "denom", denom, "address", address)

	owner, _, err := k.GetDenomOwner(ctx, denom)
	if err != nil {
		return err
	}

	k.Logger.Info("Comparing owners", "owner from record", owner, "requesting address", address)

	if owner != address {
		k.Logger.Error("Authorization failed", "denom", denom, "owner", owner, "requester", address)
		return cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"you do not own the name required to use denom %s, owner: %s, sender: %s",
			denom,
			owner,
			address,
		)
	}

	k.Logger.Info("Authorization successful", "denom", denom, "address", address)
	return nil
}

// VerifyDenomDestination checks if the provided address is the resolved destination
// of the root name for the given denom. Returns nil if it matches, or an error if not.
func (k Keeper) VerifyDenomDestination(ctx context.Context, denom string, address string) error {
	_, rootName, resolvedAddr, err := k.ResolveRootDestination(ctx, denom)
	if err != nil {
		return err
	}

	if resolvedAddr != address {
		return cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"you do not control destination for denom %s (root %s). destination: %s, sender: %s",
			denom,
			rootName,
			resolvedAddr,
			address,
		)
	}

	return nil
}

// VerifyClassRootDestination checks that the provided address equals the resolved
// destination of the root name from the given classID (e.g. root of "foo.dys/bar").
func (k Keeper) VerifyClassRootDestination(ctx context.Context, classID string, address string) error {
	_, rootName, resolvedAddr, err := k.ResolveRootDestination(ctx, classID)
	if err != nil {
		return err
	}

	if resolvedAddr != address {
		return cosmossdkerrors.Wrapf(
			sdkerrors.ErrUnauthorized,
			"you do not control destination for class %s (root %s). destination: %s, sender: %s",
			classID,
			rootName,
			resolvedAddr,
			address,
		)
	}

	return nil
}

// ResolveRootDestination resolves an identifier's root name (before '/') to its destination address.
// Returns: owner (if known), rootName, resolvedAddress.
func (k Keeper) ResolveRootDestination(ctx context.Context, identifier string) (owner string, rootName string, resolvedAddress string, err error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	rootName = extractRootName(identifier)

	// Ensure the name exists and capture the owner when available
	owner, found := k.GetNameOwner(sdkCtx, rootName)
	if !found {
		return "", "", "", cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "root name not found: %s", rootName)
	}

	// Resolve destination
	resolved, resErr := k.ResolveNameOrAddress(ctx, rootName)
	if resErr != nil {
		return "", "", "", cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "failed resolving destination for %s: %v", rootName, resErr)
	}

	return owner, rootName, resolved, nil
}

// extractRootName returns the substring before the first '/' in an identifier.
// If '/' is not present, the identifier itself is returned.
func extractRootName(identifier string) string {
	if idx := strings.Index(identifier, "/"); idx > 0 {
		return identifier[:idx]
	}
	return identifier
}

// ensureDenomMetadata creates minimal denom metadata on first mint if missing.
// Case 1: base denom equals root name (e.g. my-name.dys)
//
//	description: ""
//	denom_units: [{denom: base, exponent: 0}, {denom: display (root without suffix), exponent: 6}]
//	base: base
//	display: root without suffix
//	symbol: root without suffix
//	uri, uri_hash: ""
//
// Case 2: base denom is a subdenom (has '/'): display equals base, only base unit.
func (k Keeper) ensureDenomMetadata(ctx context.Context, denom string) {
	if k.bankKeeper.HasDenomMetaData(ctx, denom) {
		return
	}

	root := extractRootName(denom)
	suffix := k.GetNameSuffix(ctx)
	metadata := banktypes.Metadata{Description: ""}

	if denom == root {
		display := strings.TrimSuffix(root, suffix)
		metadata.Base = denom
		metadata.Display = display
		metadata.Name = strings.ReplaceAll(cases.Title(language.English).String(display), "-", " ")
		metadata.Symbol = display
		metadata.DenomUnits = []*banktypes.DenomUnit{
			{Denom: denom, Exponent: 0, Aliases: nil},
			{Denom: display, Exponent: 6, Aliases: nil},
		}
		metadata.URI = ""
		metadata.URIHash = ""
	} else {
		metadata.Base = denom
		metadata.Display = denom
		metadata.Name = denom
		metadata.Symbol = denom
		metadata.DenomUnits = []*banktypes.DenomUnit{
			{Denom: denom, Exponent: 0, Aliases: nil},
		}
		metadata.URI = ""
		metadata.URIHash = ""
	}

	k.bankKeeper.SetDenomMetaData(ctx, metadata)
}
