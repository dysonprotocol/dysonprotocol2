package types

import (
	"fmt"
)

// Protocol identity constants (not runtime-configurable)
const (
	RootName = "whaleswap.dys"
	// LiquidDenomPrefix removed with wrapper denoms
	PoolsDenomPrefix   = "whaleswap.dys/pools/"
	AuctionClassPrefix = "whaleswap.dys/auction/"
	MintFeeDenom       = "udys"

	OfferStatusOpen      = "open"
	OfferStatusClosed    = "closed"
	OfferStatusCancelled = "cancelled"

	AuctionClassName   = "Whaleswap Auction"
	AuctionClassSymbol = "WSA"
)

// Liquid wrapper denoms removed; keep function deleted.

// PoolSharesDenom builds the pool shares denom for a pool id.
func PoolSharesDenom(id uint64) string { return fmt.Sprintf("%s%d", PoolsDenomPrefix, id) }

// AuctionClassID builds the auction NFT class id for a bid denom.
func AuctionClassID(bidDenom string) string { return AuctionClassPrefix + bidDenom }
