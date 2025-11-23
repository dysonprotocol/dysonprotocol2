package module

import (
	"cosmossdk.io/core/appmodule"
	"cosmossdk.io/core/store"
	"cosmossdk.io/depinject"
	"cosmossdk.io/depinject/appconfig"
	"cosmossdk.io/log"
	modulev1 "dysonprotocol.com/api/crontask/module/v1"
	"dysonprotocol.com/x/crontask"
	"dysonprotocol.com/x/crontask/keeper"

	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	authkeeper "github.com/cosmos/cosmos-sdk/x/auth/keeper"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"
	stakingkeeper "github.com/cosmos/cosmos-sdk/x/staking/keeper"
)

var _ depinject.OnePerModuleType = AppModule{}

// IsOnePerModuleType implements the depinject.OnePerModuleType interface.
func (am AppModule) IsOnePerModuleType() {}

func init() {
	appconfig.RegisterModule(
		&modulev1.Module{},
		appconfig.Provide(ProvideModule),
	)
}

// CrontaskInputs is the input for the dep inject
type CrontaskInputs struct {
	depinject.In

	ModuleKey        depinject.OwnModuleKey
	Config           *modulev1.Module
	Cdc              codec.Codec
	AccountKeeper    authkeeper.AccountKeeper
	BankKeeper       crontask.BankKeeper
	StakingKeeper    *stakingkeeper.Keeper
	StoreService     store.KVStoreService
	Registry         cdctypes.InterfaceRegistry
	Logger           log.Logger
	MsgServiceRouter *baseapp.MsgServiceRouter
}

// CrontaskOutputs is the output for the dep inject
type CrontaskOutputs struct {
	depinject.Out

	Module         appmodule.AppModule
	CrontaskKeeper keeper.Keeper
}

// ProvideModule provides the app module
func ProvideModule(in CrontaskInputs) CrontaskOutputs {
	// Use the authority from the config if provided, otherwise default to gov module account
	authority := authtypes.NewModuleAddress(govtypes.ModuleName).String()

	// If authority is explicitly set in the config, use that instead
	if in.Config != nil && in.Config.Authority != "" {
		authority = in.Config.Authority
	}

	k := keeper.NewKeeper(
		in.Cdc,
		in.StoreService,
		in.AccountKeeper,
		in.BankKeeper,
		in.StakingKeeper,
		in.MsgServiceRouter,
		*crontask.DefaultConfig(),
		authority,
		in.Logger,
	)

	m := NewAppModule(
		in.Cdc,
		k,
		in.AccountKeeper,
		in.Registry,
	)

	return CrontaskOutputs{
		Module:         m,
		CrontaskKeeper: k,
	}
}
