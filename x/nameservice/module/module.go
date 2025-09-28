package module

import (
	"context"
	"encoding/json"
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"

	"cosmossdk.io/core/appmodule"
	"github.com/cosmos/cosmos-sdk/client"
	gwruntime "github.com/grpc-ecosystem/grpc-gateway/runtime"

	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/types/module"

	nameservice "dysonprotocol.com/x/nameservice"
	"dysonprotocol.com/x/nameservice/keeper"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
)

// ConsensusVersion defines the current x/nameservice module consensus version.
const ConsensusVersion = 1

var (
	_ module.AppModuleBasic = AppModuleBasic{}

	_ module.HasGenesis  = AppModule{}
	_ module.HasServices = AppModule{}

	_ appmodule.AppModule     = AppModule{}
	_ appmodule.HasEndBlocker = AppModule{}
)

// AppModuleBasic defines the basic application module used by the nameservice module.
type AppModuleBasic struct{}

// Name returns the nameservice module's name.
func (AppModuleBasic) Name() string {
	return nameservice.ModuleName
}

// RegisterLegacyAminoCodec registers the nameservice module's types for the given codec.
func (AppModuleBasic) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	nameservicev1.RegisterLegacyAminoCodec(cdc)
}

// RegisterInterfaces registers the nameservice module's interface types
func (b AppModuleBasic) RegisterInterfaces(registry cdctypes.InterfaceRegistry) {
	nameservicev1.RegisterInterfaces(registry)
}

// DefaultGenesis returns default genesis state as raw bytes for the nameservice module.
func (AppModuleBasic) DefaultGenesis(cdc codec.JSONCodec) json.RawMessage {
	return cdc.MustMarshalJSON(nameservicev1.DefaultGenesis())
}

// ValidateGenesis performs genesis state validation for the gov module.
func (AppModuleBasic) ValidateGenesis(cdc codec.JSONCodec, config client.TxEncodingConfig, bz json.RawMessage) error {
	var data nameservicev1.GenesisState
	if err := cdc.UnmarshalJSON(bz, &data); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", nameservice.ModuleName, err)
	}

	return nameservicev1.ValidateGenesis(&data)
}

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the nameservice module.
func (AppModuleBasic) RegisterGRPCGatewayRoutes(clientCtx client.Context, mux *gwruntime.ServeMux) {
	if err := nameservicev1.RegisterQueryHandlerClient(context.Background(), mux, nameservicev1.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}

type AppModule struct {
	cdc      codec.Codec
	registry cdctypes.InterfaceRegistry

	keeper keeper.Keeper
}

// NewAppModule creates a new AppModule object
func NewAppModule(cdc codec.Codec, k keeper.Keeper, registry cdctypes.InterfaceRegistry) AppModule {
	return AppModule{
		cdc:      cdc,
		keeper:   k,
		registry: registry,
	}
}

// IsAppModule implements the appmodule.AppModule interface.
func (AppModule) IsAppModule() {}

// Name returns the nameservice module's name.
func (am AppModule) Name() string {
	return nameservice.ModuleName
}

// RegisterInterfaces registers the nameservice module's interface types
func (am AppModule) RegisterInterfaces(registry cdctypes.InterfaceRegistry) {
	nameservicev1.RegisterInterfaces(registry)
}

// RegisterServices registers module services.
func (am AppModule) RegisterServices(cfg module.Configurator) {
	nameservicev1.RegisterMsgServer(cfg.MsgServer(), &am.keeper)
	nameservicev1.RegisterQueryServer(cfg.QueryServer(), &am.keeper)
}

// InitGenesis performs genesis initialization for the gov module. It returns
// no validator updates.
func (am AppModule) InitGenesis(ctx sdk.Context, cdc codec.JSONCodec, data json.RawMessage) {
	var genesisState nameservicev1.GenesisState
	cdc.MustUnmarshalJSON(data, &genesisState)
	if err := am.keeper.SetParams(ctx, genesisState.Params); err != nil {
		panic(fmt.Errorf("failed to set nameservice parameters: %w", err))
	}

	// Initialize commitments
	for _, commitment := range genesisState.Commitments {
		if err := am.keeper.SetCommitment(ctx, commitment); err != nil {
			panic(fmt.Errorf("failed to set nameservice commitment %s: %w", commitment.Hexhash, err))
		}
	}

	// Rebuild derived reverse indexes from existing on-chain data to ensure
	// they are present after import.
	if err := am.keeper.EnsureNamesClassExists(ctx); err != nil {
		panic(fmt.Errorf("failed to ensure names class: %w", err))
	}
}

// DefaultGenesis returns default genesis state as raw bytes for the nameservice module.
func (AppModule) DefaultGenesis(cdc codec.JSONCodec) json.RawMessage {
	return cdc.MustMarshalJSON(nameservicev1.DefaultGenesis())
}

// ValidateGenesis performs genesis state validation for the nameservice module.
func (AppModule) ValidateGenesis(cdc codec.JSONCodec, config client.TxEncodingConfig, bz json.RawMessage) error {
	var data nameservicev1.GenesisState
	if err := cdc.UnmarshalJSON(bz, &data); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", nameservice.ModuleName, err)
	}
	return nameservicev1.ValidateGenesis(&data)
}

// ExportGenesis returns the exported genesis state as raw bytes for the gov
// ExportGenesis returns the exported genesis state as raw bytes for the gov
// module.
func (am AppModule) ExportGenesis(ctx sdk.Context, cdc codec.JSONCodec) json.RawMessage {
	gs, err := am.keeper.ExportGenesis(ctx)
	if err != nil {
		panic(err)
	}
	return cdc.MustMarshalJSON(gs)
}

// RegisterMigrations registers module migrations
func (am AppModule) RegisterMigrations() error {
	return nil
}

// ConsensusVersion implements HasConsensusVersion
func (AppModule) ConsensusVersion() uint64 { return ConsensusVersion }

// EndBlock implements the appmodule.HasEndBlocker interface
func (am AppModule) EndBlock(ctx context.Context) error {
	return nil
}

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the module.
func (AppModule) RegisterGRPCGatewayRoutes(clientCtx client.Context, mux *gwruntime.ServeMux) {
	if err := nameservicev1.RegisterQueryHandlerClient(context.Background(), mux, nameservicev1.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}

// RegisterLegacyAminoCodec registers the storage module's types for the given codec.
func (AppModule) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	nameservicev1.RegisterLegacyAminoCodec(cdc)
}
