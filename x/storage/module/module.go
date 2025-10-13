package module

import (
	"context"
	"encoding/json"
	"fmt"
	"io"

	gwruntime "github.com/grpc-ecosystem/grpc-gateway/runtime"
	"github.com/spf13/cobra"

	autocliv1 "cosmossdk.io/client/v2/autocli"
	"cosmossdk.io/core/appmodule"
	"dysonprotocol.com/x/storage"
	"dysonprotocol.com/x/storage/client/cli"
	"dysonprotocol.com/x/storage/keeper"
	storagetypes "dysonprotocol.com/x/storage/types"

	sdkclient "github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/types/module"
)

const ConsensusVersion = 1

var (
	_ module.AppModuleBasic        = AppModuleBasic{}
	_ module.AppModule             = AppModule{}
	_ module.HasServices           = AppModule{}
	_ appmodule.AppModule          = AppModule{}
	_ appmodule.HasGenesis         = AppModule{}
	_ appmodule.HasEndBlocker      = AppModule{}
	_ autocliv1.HasCustomTxCommand = AppModule{}
)

// AppModuleBasic defines the basic application module used by the storage module.
type AppModuleBasic struct{}

// Name returns the storage module's name.
func (AppModuleBasic) Name() string {
	return storage.ModuleName
}

// RegisterLegacyAminoCodec registers the storage module's types for the given codec.
func (AppModuleBasic) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	storage.RegisterLegacyAminoCodec(cdc)
}

// RegisterInterfaces registers the storage module's interface types
func (b AppModuleBasic) RegisterInterfaces(registry cdctypes.InterfaceRegistry) {
	storage.RegisterInterfaces(registry)
}

// DefaultGenesis returns default genesis state as raw bytes for the storage module.
func (AppModuleBasic) DefaultGenesis(cdc codec.JSONCodec) json.RawMessage {
	return cdc.MustMarshalJSON(storage.DefaultGenesis())
}

// ValidateGenesis performs genesis state validation for the storage module.
func (AppModuleBasic) ValidateGenesis(cdc codec.JSONCodec, config sdkclient.TxEncodingConfig, bz json.RawMessage) error {
	var data storagetypes.GenesisState
	if err := cdc.UnmarshalJSON(bz, &data); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", storage.ModuleName, err)
	}
	return storage.ValidateGenesisState(data)
}

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the storage module.
func (AppModuleBasic) RegisterGRPCGatewayRoutes(clientCtx sdkclient.Context, mux *gwruntime.ServeMux) {
}

// GetTxCmd returns the root tx command for the storage module.
func (am AppModule) GetTxCmd() *cobra.Command {
	return cli.NewTxCmd()
}

// GetQueryCmd returns the root query command for the storage module.
func (am AppModule) GetQueryCmd() *cobra.Command {
	return cli.NewQueryCmd()
}

type AppModule struct {
	cdc      codec.Codec
	registry cdctypes.InterfaceRegistry

	keeper    keeper.Keeper
	accKeeper storage.AccountKeeper
}

// NewAppModule creates a new AppModule object
func NewAppModule(cdc codec.Codec, keeper keeper.Keeper, ak storage.AccountKeeper, registry cdctypes.InterfaceRegistry) AppModule {
	return AppModule{
		cdc:       cdc,
		keeper:    keeper,
		accKeeper: ak,
		registry:  registry,
	}
}

// IsAppModule implements the appmodule.AppModule interface.
func (AppModule) IsAppModule() {}

// Name returns the storage module's name.
func (am AppModule) Name() string {
	return storage.ModuleName
}

// Removed legacy module.HasGenesis methods in favor of core appmodule.HasGenesis

// RegisterInterfaces registers the group module's interface types
func (AppModule) RegisterInterfaces(registrar cdctypes.InterfaceRegistry) {
	storage.RegisterInterfaces(registrar)
}

// RegisterServices registers module services.
func (am AppModule) RegisterServices(configurator module.Configurator) {
	storagetypes.RegisterMsgServer(configurator.MsgServer(), am.keeper)
	storagetypes.RegisterQueryServer(configurator.QueryServer(), am.keeper)
}

// --- Core API genesis (appmodule.HasGenesis) ---

// ValidateGenesis implements appmodule.HasGenesis using the core API
func (am AppModule) ValidateGenesis(source appmodule.GenesisSource) error {
	reader, err := source(storage.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get genesis source for %s: %w", storage.ModuleName, err)
	}

	var gs *storagetypes.GenesisState
	if reader == nil {
		// no data provided – validate defaults
		def := storage.NewGenesisState()
		return storage.ValidateGenesisState(*def)
	}
	defer func(rc io.ReadCloser) { _ = rc.Close() }(reader)

	tmp := storagetypes.GenesisState{}
	if err := json.NewDecoder(reader).Decode(&tmp); err != nil {
		if err == io.EOF {
			def := storage.NewGenesisState()
			return storage.ValidateGenesisState(*def)
		}
		return fmt.Errorf("failed to decode %s genesis for validation: %w", storage.ModuleName, err)
	}
	gs = &tmp
	return storage.ValidateGenesisState(*gs)
}

// InitGenesis implements appmodule.HasGenesis using the core API
func (am AppModule) InitGenesis(ctx context.Context, source appmodule.GenesisSource) error {
	reader, err := source(storage.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get genesis source for %s: %w", storage.ModuleName, err)
	}

	var gs *storagetypes.GenesisState
	if reader == nil {
		gs = storage.NewGenesisState()
	} else {
		defer func(rc io.ReadCloser) { _ = rc.Close() }(reader)
		tmp := storagetypes.GenesisState{}
		if err := json.NewDecoder(reader).Decode(&tmp); err != nil {
			if err == io.EOF {
				gs = storage.NewGenesisState()
			} else {
				return fmt.Errorf("failed to decode %s genesis: %w", storage.ModuleName, err)
			}
		} else {
			gs = &tmp
		}
	}

	am.keeper.InitGenesis(ctx, gs)
	return nil
}

// DefaultGenesis implements appmodule.HasGenesis using the core API
func (am AppModule) DefaultGenesis(target appmodule.GenesisTarget) error {
	writer, err := target(storage.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get writer for %s genesis: %w", storage.ModuleName, err)
	}
	defer func(w io.WriteCloser) { _ = w.Close() }(writer)
	enc := json.NewEncoder(writer)
	if err := enc.Encode(storage.DefaultGenesis()); err != nil {
		return fmt.Errorf("failed to encode %s default genesis: %w", storage.ModuleName, err)
	}
	return nil
}

// ExportGenesis implements appmodule.HasGenesis using the core API
func (am AppModule) ExportGenesis(ctx context.Context, target appmodule.GenesisTarget) error {
	gs := am.keeper.ExportGenesis(ctx)
	writer, err := target(storage.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get writer for %s export: %w", storage.ModuleName, err)
	}
	defer func(w io.WriteCloser) { _ = w.Close() }(writer)
	enc := json.NewEncoder(writer)
	if err := enc.Encode(gs); err != nil {
		return fmt.Errorf("failed to encode %s export: %w", storage.ModuleName, err)
	}
	return nil
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

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the storage module.
func (am AppModule) RegisterGRPCGatewayRoutes(clientCtx sdkclient.Context, mux *gwruntime.ServeMux) {
	if err := storagetypes.RegisterQueryHandlerClient(context.Background(), mux, storagetypes.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}

// RegisterLegacyAminoCodec registers the storage module's types for the given codec.
func (AppModule) RegisterLegacyAminoCodec(registrar *codec.LegacyAmino) {
	storage.RegisterLegacyAminoCodec(registrar)
}
