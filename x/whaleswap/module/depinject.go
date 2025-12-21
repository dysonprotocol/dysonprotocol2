package module

import (
	"cosmossdk.io/core/appmodule"
	"cosmossdk.io/core/store"
	"cosmossdk.io/depinject"
	"cosmossdk.io/depinject/appconfig"
	"cosmossdk.io/log"

	modulev1 "dysonprotocol.com/api/whaleswap/module/v1"
	"dysonprotocol.com/x/whaleswap/keeper"
	whaleswaptypes "dysonprotocol.com/x/whaleswap/types"

	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"
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

type ModuleInputs struct {
	depinject.In

	StoreService store.KVStoreService
	Cdc          codec.Codec
	Registry     cdctypes.InterfaceRegistry
	Logger       log.Logger

	AccountKeeper whaleswaptypes.AccountKeeper
	BankKeeper    whaleswaptypes.BankKeeper
	NamesvcKeeper whaleswaptypes.NameserviceKeeper
	NFTKeeper     whaleswaptypes.NFTKeeper
	StakingKeeper whaleswaptypes.StakingKeeper

	Config *modulev1.Module
}

type ModuleOutputs struct {
	depinject.Out

	Module appmodule.AppModule
	Keeper keeper.Keeper
}

func ProvideModule(in ModuleInputs) ModuleOutputs {
	// Use the authority from the config if provided, otherwise default to gov module account
	authority := authtypes.NewModuleAddress(govtypes.ModuleName).String()
	if in.Config != nil && in.Config.Authority != "" {
		authority = in.Config.Authority
	}

	k := keeper.NewKeeper(
		in.Cdc,
		in.StoreService,
		in.AccountKeeper,
		in.BankKeeper,
		in.NamesvcKeeper,
		in.NFTKeeper,
		in.StakingKeeper,
		in.Logger,
		authority,
	)
	m := NewAppModule(in.Cdc, k, in.Registry)
	return ModuleOutputs{Module: m, Keeper: k}
}
