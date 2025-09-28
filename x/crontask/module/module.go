package module

import (
	"context"
	"encoding/json"
	"fmt"
	"io"

	gwruntime "github.com/grpc-ecosystem/grpc-gateway/runtime"
	"github.com/spf13/cobra"

	"cosmossdk.io/core/appmodule"
	"dysonprotocol.com/x/crontask"
	"dysonprotocol.com/x/crontask/keeper"
	"dysonprotocol.com/x/crontask/types"

	sdkclient "github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/module"
	simtypes "github.com/cosmos/cosmos-sdk/types/simulation"
)

// ConsensusVersion defines the current x/crontask module consensus version.
const ConsensusVersion = 1

var (
	_ module.AppModuleBasic     = AppModuleBasic{}
	_ appmodule.AppModule       = AppModule{}
	_ appmodule.HasBeginBlocker = AppModule{}
	_ appmodule.HasGenesis      = AppModule{}
	_ appmodule.HasEndBlocker   = AppModule{}
)

// AppModuleBasic defines the basic application module used by the crontask module.
type AppModuleBasic struct{}

// Name returns the crontask module's name.
func (AppModuleBasic) Name() string {
	return crontask.ModuleName
}

// RegisterLegacyAminoCodec registers the crontask module's types for the given codec.
func (AppModuleBasic) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	types.RegisterLegacyAminoCodec(cdc)
}

// RegisterInterfaces registers the crontask module's interface types
func (b AppModuleBasic) RegisterInterfaces(registry cdctypes.InterfaceRegistry) {
	types.RegisterInterfaces(registry)
}

// DefaultGenesis returns default genesis state as raw bytes for the crontask module.
func (AppModuleBasic) DefaultGenesis(cdc codec.JSONCodec) json.RawMessage {
	return cdc.MustMarshalJSON(types.NewGenesisState())
}

// ValidateGenesis performs genesis state validation for the crontask module.
func (AppModuleBasic) ValidateGenesis(cdc codec.JSONCodec, config sdkclient.TxEncodingConfig, bz json.RawMessage) error {
	// Treat empty or missing data as default genesis for consistency with the
	// appmodule.HasGenesis path.
	if len(bz) == 0 || string(bz) == "{}" {
		def := types.NewGenesisState()
		return types.ValidateGenesis(def)
	}
	var data types.GenesisState
	if err := cdc.UnmarshalJSON(bz, &data); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", crontask.ModuleName, err)
	}
	return types.ValidateGenesis(&data)
}

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the crontask module.
func (AppModuleBasic) RegisterGRPCGatewayRoutes(clientCtx sdkclient.Context, mux *gwruntime.ServeMux) {
	if err := types.RegisterQueryHandlerClient(context.Background(), mux, types.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}

type AppModule struct {
	cdc      codec.Codec
	registry cdctypes.InterfaceRegistry

	keeper        keeper.Keeper
	accountKeeper crontask.AccountKeeper
}

// NewAppModule creates a new AppModule object
func NewAppModule(cdc codec.Codec, keeper keeper.Keeper, ak crontask.AccountKeeper, registry cdctypes.InterfaceRegistry) AppModule {
	return AppModule{
		cdc:           cdc,
		keeper:        keeper,
		accountKeeper: ak,
		registry:      registry,
	}
}

// IsAppModule implements the appmodule.AppModule interface.
func (AppModule) IsAppModule() {}

// Name returns the crontask module's name.
func (am AppModule) Name() string {
	return crontask.ModuleName
}

// GetTxCmd returns the transaction commands for the crontask module
func (am AppModule) GetTxCmd() *cobra.Command {
	// Return nil to let autocli handle commands
	return nil
}

// GetQueryCmd returns the query commands for the crontask module
func (am AppModule) GetQueryCmd() *cobra.Command {
	// Return nil to let autocli handle commands
	return nil
}

// RegisterInterfaces registers the crontask module's interface types
func (am AppModule) RegisterInterfaces(registry cdctypes.InterfaceRegistry) {
	types.RegisterInterfaces(registry)
}

// RegisterServices registers module services.
func (am AppModule) RegisterServices(cfg module.Configurator) {
	types.RegisterMsgServer(cfg.MsgServer(), &am.keeper)
	types.RegisterQueryServer(cfg.QueryServer(), keeper.NewQueryServer(am.keeper))
}

// ConsensusVersion implements HasConsensusVersion
func (AppModule) ConsensusVersion() uint64 { return ConsensusVersion }

// RegisterStoreDecoder registers a decoder for crontask module's types
func (am AppModule) RegisterStoreDecoder(sdr simtypes.StoreDecoderRegistry) {
	// No custom store decoder needed for this module
}

// WeightedOperations returns the all the crontask module operations with their respective weights.
func (am AppModule) WeightedOperations(_ module.SimulationState) []simtypes.WeightedOperation {
	return []simtypes.WeightedOperation{}
}

// BeginBlock implements the appmodule.HasBeginBlocker interface
func (am AppModule) BeginBlock(ctx context.Context) error {
	return am.keeper.BeginBlocker(sdk.UnwrapSDKContext(ctx))
}

// EndBlock implements the appmodule.HasEndBlocker interface
func (am AppModule) EndBlock(ctx context.Context) error {
	return am.keeper.EndBlocker(sdk.UnwrapSDKContext(ctx))
}

// ValidateGenesis validates the genesis state for the crontask module.
// It now matches the appmodule.HasGenesis interface.
func (am AppModule) ValidateGenesis(source appmodule.GenesisSource) error {
	reader, err := source(crontask.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get genesis source for %s module for validation: %w", crontask.ModuleName, err)
	}

	var genesisState *types.GenesisState
	if reader == nil {
		// No data for this module. Validate the default genesis state.
		genesisState = types.NewGenesisState()
	} else {
		defer reader.Close()
		gs := types.GenesisState{} // Local var for decoding
		if err := json.NewDecoder(reader).Decode(&gs); err != nil {
			// EOF could mean an empty JSON object `{}` was provided.
			// This might be valid if it represents a default/empty state.
			if err == io.EOF {
				genesisState = types.NewGenesisState() // Use default for empty/EOF
			} else {
				return fmt.Errorf("failed to decode %s genesis state from JSON for validation: %w", crontask.ModuleName, err)
			}
		} else {
			genesisState = &gs // Use decoded state
		}
	}

	if genesisState == nil { // Safeguard if somehow still nil
		genesisState = types.NewGenesisState()
	}

	// Perform the actual validation using the module's types.ValidateGenesis
	return types.ValidateGenesis(genesisState)
}

// InitGenesis performs genesis initialization for the crontask module.
// It now matches the appmodule.HasGenesis interface.
func (am AppModule) InitGenesis(ctx context.Context, source appmodule.GenesisSource) error {
	// Use the module name to get the specific genesis data for this module.
	reader, err := source(crontask.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get genesis source for %s module: %w", crontask.ModuleName, err)
	}

	var genesisState *types.GenesisState
	if reader == nil {
		// No data for this module. Use the default genesis state.
		genesisState = types.NewGenesisState()
	} else {
		defer reader.Close()
		gs := types.GenesisState{} // Local var for decoding
		// Decode the JSON data from the reader into the GenesisState struct.
		if err := json.NewDecoder(reader).Decode(&gs); err != nil {
			// If EOF is met and it's an empty stream, it's like having no specific genesis data.
			if err == io.EOF {
				genesisState = types.NewGenesisState() // Use default for empty/EOF
			} else {
				return fmt.Errorf("failed to decode %s genesis state from JSON: %w", crontask.ModuleName, err)
			}
		} else {
			genesisState = &gs // Use decoded state
		}
	}

	if genesisState == nil { // Safeguard if somehow still nil
		genesisState = types.NewGenesisState()
	}

	// Call the keeper's InitGenesis with the unmarshaled state.
	return am.keeper.InitGenesis(ctx, genesisState)
}

// DefaultGenesis returns default genesis state as raw bytes for the crontask module.
func (am AppModule) DefaultGenesis(target appmodule.GenesisTarget) error {
	genesisState := types.NewGenesisState()
	writer, err := target(crontask.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get writer for %s genesis state: %w", crontask.ModuleName, err)
	}
	defer writer.Close()

	encoder := json.NewEncoder(writer)
	if err := encoder.Encode(genesisState); err != nil {
		return fmt.Errorf("failed to encode %s genesis state: %w", crontask.ModuleName, err)
	}

	return nil
}

func (am AppModule) ExportGenesis(ctx context.Context, target appmodule.GenesisTarget) error {
	genesisState, err := am.keeper.ExportGenesis(ctx)
	if err != nil {
		return fmt.Errorf("failed to export %s genesis state: %w", crontask.ModuleName, err)
	}

	writer, err := target(crontask.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get writer for %s genesis state: %w", crontask.ModuleName, err)
	}
	defer writer.Close()

	encoder := json.NewEncoder(writer)
	if err := encoder.Encode(genesisState); err != nil {
		return fmt.Errorf("failed to encode %s genesis state: %w", crontask.ModuleName, err)
	}

	return nil
}

// RegisterGRPCGatewayRoutes registers the gRPC Gateway routes for the crontask module.
func (am AppModule) RegisterGRPCGatewayRoutes(clientCtx sdkclient.Context, mux *gwruntime.ServeMux) {
	if err := types.RegisterQueryHandlerClient(context.Background(), mux, types.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}

// RegisterLegacyAminoCodec registers the crontask module's types for the given codec.
func (am AppModule) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	types.RegisterLegacyAminoCodec(cdc)
}
