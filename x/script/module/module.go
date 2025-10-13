package module

import (
	"context"
	"encoding/json"
	"fmt"

	gwruntime "github.com/grpc-ecosystem/grpc-gateway/runtime"
	"github.com/spf13/cobra"

	autocliv1 "cosmossdk.io/client/v2/autocli"
	"cosmossdk.io/core/appmodule"
	"dysonprotocol.com/x/script/client/cli"
	"dysonprotocol.com/x/script/keeper"

	sdkclient "github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/module"
	simtypes "github.com/cosmos/cosmos-sdk/types/simulation"

	"dysonprotocol.com/x/script"
	scripttypes "dysonprotocol.com/x/script/types"
	"google.golang.org/grpc"
)

// ConsensusVersion defines the current x/script module consensus version.
const ConsensusVersion = 1

var (
	_ module.AppModuleBasic = AppModuleBasic{}

	_ appmodule.AppModule = AppModule{}
	//_ appmodule.HasServices           = AppModule{}
	_ module.HasGenesis               = AppModule{}
	_ appmodule.HasBeginBlocker       = AppModule{}
	_ appmodule.HasEndBlocker         = AppModule{}
	_ autocliv1.HasCustomTxCommand    = AppModule{}
	_ autocliv1.HasCustomQueryCommand = AppModule{}
)

// AppModuleBasic defines the basic application module used by the script module.
type AppModuleBasic struct{}

// Name returns the script module's name.
func (AppModuleBasic) Name() string {
	return script.ModuleName
}

// RegisterLegacyAminoCodec registers the script module's types for the given codec.
func (AppModuleBasic) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	script.RegisterLegacyAminoCodec(cdc)
}

// RegisterInterfaces registers the script module's interface types
func (b AppModuleBasic) RegisterInterfaces(registry cdctypes.InterfaceRegistry) {
	script.RegisterInterfaces(registry)
}

// DefaultGenesis returns default genesis state as raw bytes for the script module.
func (AppModuleBasic) DefaultGenesis(cdc codec.JSONCodec) json.RawMessage {
	return cdc.MustMarshalJSON(script.NewGenesisState())
}

// ValidateGenesis performs genesis state validation for the script module.
func (AppModuleBasic) ValidateGenesis(cdc codec.JSONCodec, config sdkclient.TxEncodingConfig, bz json.RawMessage) error {
	var data scripttypes.GenesisState
	if err := cdc.UnmarshalJSON(bz, &data); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", script.ModuleName, err)
	}
	return script.ValidateGenesis(&data)
}

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the script module.
func (AppModuleBasic) RegisterGRPCGatewayRoutes(clientCtx sdkclient.Context, mux *gwruntime.ServeMux) {
	if err := scripttypes.RegisterQueryHandlerClient(context.Background(), mux, scripttypes.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}

type AppModule struct {
	cdc      codec.Codec
	registry cdctypes.InterfaceRegistry

	keeper     keeper.Keeper
	bankKeeper scripttypes.BankKeeper
	accKeeper  scripttypes.AccountKeeper
}

// NewAppModule creates a new AppModule object
func NewAppModule(cdc codec.Codec, keeper keeper.Keeper, ak scripttypes.AccountKeeper, bk scripttypes.BankKeeper, registry cdctypes.InterfaceRegistry) AppModule {
	return AppModule{
		cdc:        cdc,
		keeper:     keeper,
		bankKeeper: bk,
		accKeeper:  ak,
		registry:   registry,
	}
}

// IsAppModule implements the appmodule.AppModule interface.
func (AppModule) IsAppModule() {}

// Name returns the script module's name.
func (am AppModule) Name() string {
	return script.ModuleName
}

// GetTxCmd returns the root tx command for the script module.
func (AppModule) GetTxCmd() *cobra.Command {
	return cli.NewTxCmd()
}

// GetQueryCmd returns the root query command for the script module.
func (AppModule) GetQueryCmd() *cobra.Command {
	return cli.GetQueryCmd()
}

// RegisterServices registers module services.
func (am AppModule) RegisterServices(registrar grpc.ServiceRegistrar) error {
	scripttypes.RegisterMsgServer(registrar, &am.keeper)
	scripttypes.RegisterQueryServer(registrar, &am.keeper)
	return nil
}

// RegisterMigrations registers module migrations
func (am AppModule) RegisterMigrations() error {
	return nil
}

// ConsensusVersion implements HasConsensusVersion
func (AppModule) ConsensusVersion() uint64 { return ConsensusVersion }

// BeginBlock implements the script module's BeginBlock.
func (am AppModule) BeginBlock(ctx context.Context) error {
	return am.keeper.BeginBlocker(ctx)
}

// EndBlock implements the script module's EndBlock.
func (am AppModule) EndBlock(ctx context.Context) error {
	return am.keeper.EndBlocker(ctx)
}

// DefaultGenesis returns default genesis state as raw bytes for the script module.
func (am AppModule) DefaultGenesis(cdc codec.JSONCodec) json.RawMessage {
	return cdc.MustMarshalJSON(script.NewGenesisState())
}

// ValidateGenesis performs genesis state validation for the script module.
func (am AppModule) ValidateGenesis(cdc codec.JSONCodec, config sdkclient.TxEncodingConfig, bz json.RawMessage) error {
	var data scripttypes.GenesisState
	if err := cdc.UnmarshalJSON(bz, &data); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", script.ModuleName, err)
	}
	return script.ValidateGenesis(&data)
}

// InitGenesis performs genesis initialization for the script module.
func (am AppModule) InitGenesis(ctx sdk.Context, cdc codec.JSONCodec, data json.RawMessage) {
	if err := am.keeper.InitGenesis(ctx, cdc, data); err != nil {
		panic(err)
	}
}

// ExportGenesis returns the exported genesis state as raw bytes for the script module.
func (am AppModule) ExportGenesis(ctx sdk.Context, cdc codec.JSONCodec) json.RawMessage {
	gs, err := am.keeper.ExportGenesis(ctx, cdc)
	if err != nil {
		panic(err)
	}
	return cdc.MustMarshalJSON(gs)
}

// GenerateGenesisState creates a randomized GenState of the group module.
func (AppModule) GenerateGenesisState(simState *module.SimulationState) {
	// Empty implementation
}

// RegisterStoreDecoder registers a decoder for scripts module's types
func (am AppModule) RegisterStoreDecoder(sdr simtypes.StoreDecoderRegistry) {
	// Empty implementation
}

// WeightedOperations returns the all the script module operations with their respective weights.
func (am AppModule) WeightedOperations(simState module.SimulationState) []simtypes.WeightedOperation {
	return nil
}

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the script module.
func (am AppModule) RegisterGRPCGatewayRoutes(clientCtx sdkclient.Context, mux *gwruntime.ServeMux) {
	if err := scripttypes.RegisterQueryHandlerClient(context.Background(), mux, scripttypes.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}

// RegisterInterfaces registers the script module's interface types
func (am AppModule) RegisterInterfaces(registry cdctypes.InterfaceRegistry) {
	script.RegisterInterfaces(registry)
}

// RegisterLegacyAminoCodec registers the script module's types for the given codec.
func (am AppModule) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	script.RegisterLegacyAminoCodec(cdc)
}
