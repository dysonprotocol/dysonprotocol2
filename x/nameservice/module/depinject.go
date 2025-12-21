package module

import (
	"cosmossdk.io/core/appmodule"
	"cosmossdk.io/core/store"
	"cosmossdk.io/depinject"
	"cosmossdk.io/depinject/appconfig"
	"cosmossdk.io/log"
	sdkcodec "github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"

	modulev1 "dysonprotocol.com/api/nameservice/module/v1"
	nameservicekeeper "dysonprotocol.com/x/nameservice/keeper"
	"dysonprotocol.com/x/nameservice/types"
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

// Module Providers
type ModuleInputs struct {
	depinject.In

	StoreService        store.KVStoreService
	Cdc                 sdkcodec.Codec
	Registry            cdctypes.InterfaceRegistry
	Logger              log.Logger
	BankKeeper          types.BankKeeper
	AccountKeeper       types.AccountKeeper
	CommunityPoolKeeper types.CommunityPoolKeeper
	NFTKeeper           types.NFTKeeper
	StakingKeeper       types.StakingKeeper
	Config              *modulev1.Module
}

type ModuleOutputs struct {
	depinject.Out

	Module appmodule.AppModule
	Keeper nameservicekeeper.Keeper
}

func ProvideModule(in ModuleInputs) ModuleOutputs {

	// Use the authority from the config if provided, otherwise default to gov module account with dys prefix
	authority := authtypes.NewModuleAddress(govtypes.ModuleName).String()

	// If authority is explicitly set in the config, use that instead
	if in.Config != nil && in.Config.Authority != "" {
		authority = in.Config.Authority
	}

	k := nameservicekeeper.NewKeeper(
		in.Cdc,
		in.StoreService,
		in.BankKeeper,
		in.AccountKeeper,
		in.CommunityPoolKeeper,
		in.NFTKeeper,
		in.StakingKeeper,
		in.Logger,
		authority,
	)
	m := NewAppModule(
		in.Cdc,
		k,
		in.Registry,
	)

	return ModuleOutputs{
		Module: m,
		Keeper: k,
	}
}
