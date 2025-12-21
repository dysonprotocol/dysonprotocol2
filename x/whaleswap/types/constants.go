package types

import (
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"
)

// Status constants (not chain-identity dependent)
const (
	OfferStatusOpen      = "open"
	OfferStatusClosed    = "closed"
	OfferStatusCancelled = "cancelled"

	AuctionClassName   = "Whaleswap Auction"
	AuctionClassSymbol = "WSA"
)

// RootNameForSuffix returns the whaleswap root name for a given name suffix (e.g., ".dys" -> "whaleswap.dys").
func RootNameForSuffix(nameSuffix string) string {
	return "whaleswap" + nameSuffix
}

// PoolsDenomPrefixForSuffix returns the prefix for pool shares denoms for a given name suffix.
func PoolsDenomPrefixForSuffix(nameSuffix string) string {
	return RootNameForSuffix(nameSuffix) + "/pools/"
}

// AuctionClassPrefixForSuffix returns the prefix for auction NFT class IDs for a given name suffix.
func AuctionClassPrefixForSuffix(nameSuffix string) string {
	return RootNameForSuffix(nameSuffix) + "/auction/"
}

// MintFeeDenom returns the base denom for mint fees (uses SDK default bond denom).
func MintFeeDenom() string {
	return sdk.DefaultBondDenom
}

// PoolSharesDenomForSuffix builds the pool shares denom for a pool id and name suffix.
func PoolSharesDenomForSuffix(nameSuffix string, id uint64) string {
	return fmt.Sprintf("%s%d", PoolsDenomPrefixForSuffix(nameSuffix), id)
}

// AuctionClassIDForSuffix builds the auction NFT class id for a bid denom and name suffix.
func AuctionClassIDForSuffix(nameSuffix string, bidDenom string) string {
	return AuctionClassPrefixForSuffix(nameSuffix) + bidDenom
}
