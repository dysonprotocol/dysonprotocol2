package types

import (
	"context"

	sdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// AccountKeeper defines the expected account keeper
type AccountKeeper interface {
	GetAccount(ctx context.Context, addr sdk.AccAddress) sdk.AccountI
	GetModuleAccount(ctx context.Context, moduleName string) sdk.ModuleAccountI
}

// BankKeeper defines the expected bank keeper
type BankKeeper interface {
	HasBalance(ctx context.Context, addr sdk.AccAddress, amt sdk.Coin) bool
	GetBalance(ctx context.Context, addr sdk.AccAddress, denom string) sdk.Coin
	SendCoinsFromAccountToModule(ctx context.Context, senderAddr sdk.AccAddress, recipientModule string, amt sdk.Coins) error
}

// StakingKeeper defines the expected interface needed to retrieve delegation information.
type StakingKeeper interface {
	// GetDelegatorBonded returns the total amount a delegator has bonded.
	GetDelegatorBonded(ctx context.Context, delegator sdk.AccAddress) (sdkmath.Int, error)
}

// BranchKeeper defines the expected branch keeper for atomic execution
type BranchKeeper interface {
	NewBranch(ctx sdk.Context) (sdk.Context, func(), func())
}
