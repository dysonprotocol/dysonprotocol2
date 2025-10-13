package module

import (
	"context"
	"encoding/json"
	"fmt"
	"io"

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

	_ module.HasServices = AppModule{}

	_ appmodule.AppModule     = AppModule{}
	_ appmodule.HasGenesis    = AppModule{}
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

// ValidateGenesis performs genesis state validation for the nameservice module.
func (AppModuleBasic) ValidateGenesis(cdc codec.JSONCodec, config client.TxEncodingConfig, bz json.RawMessage) error {
	var data nameservicev1.GenesisState
	if err := cdc.UnmarshalJSON(bz, &data); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", nameservice.ModuleName, err)
	}

	return nameservicev1.ValidateGenesis(&data)
}

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the nameservice module.
func (AppModuleBasic) RegisterGRPCGatewayRoutes(clientCtx client.Context, mux *gwruntime.ServeMux) {}

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

// Core API genesis (appmodule.HasGenesis)
func (am AppModule) ValidateGenesis(source appmodule.GenesisSource) error {
	reader, err := source(nameservice.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get genesis source for %s: %w", nameservice.ModuleName, err)
	}
	if reader == nil {
		def := nameservicev1.DefaultGenesis()
		return nameservicev1.ValidateGenesis(def)
	}
	defer func(rc io.ReadCloser) { _ = rc.Close() }(reader)
	var gs nameservicev1.GenesisState
	if err := json.NewDecoder(reader).Decode(&gs); err != nil {
		if err == io.EOF {
			def := nameservicev1.DefaultGenesis()
			return nameservicev1.ValidateGenesis(def)
		}
		return fmt.Errorf("failed to decode %s genesis: %w", nameservice.ModuleName, err)
	}
	return nameservicev1.ValidateGenesis(&gs)
}

func (am AppModule) InitGenesis(ctx context.Context, source appmodule.GenesisSource) error {
	reader, err := source(nameservice.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get genesis source for %s: %w", nameservice.ModuleName, err)
	}
	var gs *nameservicev1.GenesisState
	if reader == nil {
		def := nameservicev1.DefaultGenesis()
		gs = def
	} else {
		defer func(rc io.ReadCloser) { _ = rc.Close() }(reader)
		tmp := nameservicev1.GenesisState{}
		if err := json.NewDecoder(reader).Decode(&tmp); err != nil {
			if err == io.EOF {
				gs = nameservicev1.DefaultGenesis()
			} else {
				return fmt.Errorf("failed to decode %s genesis: %w", nameservice.ModuleName, err)
			}
		} else {
			gs = &tmp
		}
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if err := am.keeper.SetParams(sdkCtx, gs.Params); err != nil {
		return fmt.Errorf("failed to set nameservice parameters: %w", err)
	}
	for _, commitment := range gs.Commitments {
		if err := am.keeper.SetCommitment(sdkCtx, commitment); err != nil {
			return fmt.Errorf("failed to set nameservice commitment %s: %w", commitment.Hexhash, err)
		}
	}

	// Restore bid ledger authoritative data
	if err := am.keeper.SetBidSeq(sdkCtx, gs.BidSeq); err != nil {
		return fmt.Errorf("failed to set bid sequence: %w", err)
	}
	if err := am.keeper.ImportBids(sdkCtx, gs.Bids); err != nil {
		return fmt.Errorf("failed to import bids: %w", err)
	}
	if err := am.keeper.EnsureNamesClassExists(sdkCtx); err != nil {
		return fmt.Errorf("failed to ensure names class: %w", err)
	}
	// Rebuild derived indexes that are not persisted in genesis
	if err := am.keeper.RebuildDerivedIndexes(sdkCtx); err != nil {
		return fmt.Errorf("failed to rebuild derived indexes: %w", err)
	}
	return nil
}

// DefaultGenesis returns default genesis state as raw bytes for the nameservice module.
func (am AppModule) DefaultGenesis(target appmodule.GenesisTarget) error {
	writer, err := target(nameservice.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get writer for %s genesis: %w", nameservice.ModuleName, err)
	}
	defer func(w io.WriteCloser) { _ = w.Close() }(writer)
	return json.NewEncoder(writer).Encode(nameservicev1.DefaultGenesis())
}

// ValidateGenesis performs genesis state validation for the nameservice module.
// removed legacy ValidateGenesis

// ExportGenesis returns the exported genesis state for the nameservice module.
func (am AppModule) ExportGenesis(ctx context.Context, target appmodule.GenesisTarget) error {
	gs, err := am.keeper.ExportGenesis(ctx)
	if err != nil {
		return err
	}
	writer, err := target(nameservice.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get writer for %s export: %w", nameservice.ModuleName, err)
	}
	defer func(w io.WriteCloser) { _ = w.Close() }(writer)
	return json.NewEncoder(writer).Encode(gs)
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

// RegisterLegacyAminoCodec registers the nameservice module's types for the given codec.
func (AppModule) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	nameservicev1.RegisterLegacyAminoCodec(cdc)
}
