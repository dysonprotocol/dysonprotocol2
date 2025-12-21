package types

import (
	"context"

	"cosmossdk.io/core/address"
	"cosmossdk.io/math"

	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
)

type AccountKeeper interface {
	AddressCodec() address.Codec
	GetModuleAddress(moduleName string) sdk.AccAddress
	GetModuleAccount(ctx context.Context, moduleName string) sdk.ModuleAccountI
}

type BankKeeper interface {
	SendCoinsFromAccountToModule(ctx context.Context, senderAddr sdk.AccAddress, recipientModule string, amt sdk.Coins) error
	SendCoinsFromModuleToAccount(ctx context.Context, senderModule string, recipientAddr sdk.AccAddress, amt sdk.Coins) error
	SendCoinsFromModuleToModule(ctx context.Context, senderModule string, recipientModule string, amt sdk.Coins) error
	SendCoins(ctx context.Context, from, to sdk.AccAddress, amt sdk.Coins) error
	MintCoins(ctx context.Context, moduleName string, amounts sdk.Coins) error
	BurnCoins(ctx context.Context, moduleName string, amounts sdk.Coins) error
	GetBalance(ctx context.Context, addr sdk.AccAddress, denom string) sdk.Coin
	SpendableCoins(ctx context.Context, addr sdk.AccAddress) sdk.Coins
	GetSupply(ctx context.Context, denom string) sdk.Coin
	GetDenomMetaData(ctx context.Context, denom string) (banktypes.Metadata, bool)
	// BlockedAddr returns true if the address is blocked from receiving funds (module accounts, etc.)
	BlockedAddr(addr sdk.AccAddress) bool
}

type NameserviceKeeper interface {
	// Minimal hooks used by whaleswap; full API is in nameservice module
	GetParams(ctx context.Context) nameservicev1.Params
	MintCoins(ctx context.Context, msg *nameservicev1.MsgMintCoins) (*nameservicev1.MsgMintCoinsResponse, error)
	BurnCoins(ctx context.Context, msg *nameservicev1.MsgBurnCoins) (*nameservicev1.MsgBurnCoinsResponse, error)
	MoveCoins(ctx context.Context, msg *nameservicev1.MsgMoveCoins) (*nameservicev1.MsgMoveCoinsResponse, error)
	// Name administration
	ResolveNameOrAddress(ctx context.Context, nameOrAddress string) (string, error)
	SetDestination(ctx context.Context, msg *nameservicev1.MsgSetDestination) (*nameservicev1.MsgSetDestinationResponse, error)
	MintNFT(ctx context.Context, msg *nameservicev1.MsgMintNFT) (*nameservicev1.MsgMintNFTResponse, error)
	// Authority helper
	GetAuthority() string
	// Chain identity helpers
	GetNameSuffix(ctx context.Context) string
	NamesClassID(ctx context.Context) string
	// NFT/Class administration used by auctions
	SaveClass(ctx context.Context, msg *nameservicev1.MsgSaveClass) (*nameservicev1.MsgSaveClassResponse, error)
	SetNFTClassAlwaysListed(ctx context.Context, msg *nameservicev1.MsgSetNFTClassAlwaysListed) (*nameservicev1.MsgSetNFTClassAlwaysListedResponse, error)
	SetNFTClassValuationFeePct(ctx context.Context, msg *nameservicev1.MsgSetNFTClassValuationFeePct) (*nameservicev1.MsgSetNFTClassValuationFeePctResponse, error)
	SetNFTClassValuationPeriod(ctx context.Context, msg *nameservicev1.MsgSetNFTClassValuationPeriod) (*nameservicev1.MsgSetNFTClassValuationPeriodResponse, error)
	SetNFTClassBidTimeout(ctx context.Context, msg *nameservicev1.MsgSetNFTClassBidTimeout) (*nameservicev1.MsgSetNFTClassBidTimeoutResponse, error)
	SetNFTClassAllowedDenoms(ctx context.Context, msg *nameservicev1.MsgSetNFTClassAllowedDenoms) (*nameservicev1.MsgSetNFTClassAllowedDenomsResponse, error)
	SetNFTClassMinimumBidPercentIncrease(ctx context.Context, msg *nameservicev1.MsgSetNFTClassMinimumBidPercentIncrease) (*nameservicev1.MsgSetNFTClassMinimumBidPercentIncreaseResponse, error)
	MoveNft(ctx context.Context, msg *nameservicev1.MsgMoveNft) (*nameservicev1.MsgMoveNftResponse, error)
	BurnNFT(ctx context.Context, msg *nameservicev1.MsgBurnNFT) (*nameservicev1.MsgBurnNFTResponse, error)
	// Read NFT data (for bidder checks)
	GetNFTData(ctx context.Context, classId string, nftId string) (nameservicev1.NFTData, error)
}

type NFTKeeper interface {
	// Read current owner of an NFT
	GetOwner(ctx context.Context, classID, nftID string) sdk.AccAddress
	HasNFT(ctx context.Context, classID, nftID string) bool
}

type CommunityPoolKeeper interface{}

type StakingKeeper interface {
	GetDelegatorBonded(ctx context.Context, delegator sdk.AccAddress) (math.Int, error)
	// BondDenom returns the bond denomination from staking params
	BondDenom(ctx context.Context) (string, error)
}
