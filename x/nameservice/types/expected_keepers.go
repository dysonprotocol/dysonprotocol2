package types

import (
	"context"

	nft "dysonprotocol.com/x/nft"
	sdk "github.com/cosmos/cosmos-sdk/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
)

// AccountKeeper defines the expected account keeper
type AccountKeeper interface {
	GetAccount(ctx context.Context, addr sdk.AccAddress) sdk.AccountI
	GetModuleAccount(ctx context.Context, moduleName string) sdk.ModuleAccountI
	GetModuleAddress(moduleName string) sdk.AccAddress
}

// BankKeeper defines the expected bank keeper
type BankKeeper interface {
	SpendableCoins(ctx context.Context, addr sdk.AccAddress) sdk.Coins
	GetBalance(ctx context.Context, addr sdk.AccAddress, denom string) sdk.Coin
	HasSupply(ctx context.Context, denom string) bool
	SendCoins(ctx context.Context, fromAddr sdk.AccAddress, toAddr sdk.AccAddress, amt sdk.Coins) error
	SendCoinsFromModuleToAccount(ctx context.Context, senderModule string, recipientAddr sdk.AccAddress, amt sdk.Coins) error
	SendCoinsFromAccountToModule(ctx context.Context, senderAddr sdk.AccAddress, recipientModule string, amt sdk.Coins) error
	MintCoins(ctx context.Context, moduleName string, amt sdk.Coins) error
	BurnCoins(ctx context.Context, moduleName string, amt sdk.Coins) error
	// Metadata helpers
	GetDenomMetaData(ctx context.Context, denom string) (banktypes.Metadata, bool)
	HasDenomMetaData(ctx context.Context, denom string) bool
	SetDenomMetaData(ctx context.Context, denomMetaData banktypes.Metadata)
	GetAllDenomMetaData(ctx context.Context) []banktypes.Metadata
}

// CommunityPoolKeeper defines the expected community pool keeper
type CommunityPoolKeeper interface {
	FundCommunityPool(ctx context.Context, amount sdk.Coins, sender sdk.AccAddress) error
}

// StakingKeeper defines the expected staking keeper
type StakingKeeper interface {
	// BondDenom returns the bond denomination from staking params
	BondDenom(ctx context.Context) (string, error)
}

// NFTKeeper defines the expected NFT keeper
type NFTKeeper interface {
	// Class methods
	SaveClass(ctx context.Context, class nft.Class) error
	UpdateClass(ctx context.Context, class nft.Class) error
	GetClass(ctx context.Context, classID string) (nft.Class, bool)
	HasClass(ctx context.Context, classID string) bool
	// List all classes
	GetClasses(ctx context.Context) (classes []*nft.Class)
	// GetTotalSupply returns the number of NFTs in the class
	GetTotalSupply(ctx context.Context, classID string) uint64
	// RemoveClass deletes an NFT class; must only be called when empty
	RemoveClass(ctx context.Context, classID string) error

	// NFT methods
	Mint(ctx context.Context, token nft.NFT, receiver sdk.AccAddress) error
	Burn(ctx context.Context, classID string, nftID string) error
	Update(ctx context.Context, token nft.NFT) error
	GetNFT(ctx context.Context, classID string, nftID string) (nft.NFT, bool)
	GetOwner(ctx context.Context, classID string, nftID string) sdk.AccAddress
	HasNFT(ctx context.Context, classID string, nftID string) bool
	// List all NFTs in a class
	GetNFTsOfClass(ctx context.Context, classID string) (nfts []nft.NFT)
	// Transfer transfers an NFT to a new owner
	Transfer(ctx context.Context, classID string, nftID string, receiver sdk.AccAddress) error
}
