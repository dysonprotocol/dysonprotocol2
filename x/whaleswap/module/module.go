package module

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"

	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapcli "dysonprotocol.com/x/whaleswap/client/cli"
	"dysonprotocol.com/x/whaleswap/keeper"
	whaleswaptypes "dysonprotocol.com/x/whaleswap/types"

	autocliv1 "cosmossdk.io/client/v2/autocli"
	"cosmossdk.io/core/appmodule"
	gwruntime "github.com/grpc-ecosystem/grpc-gateway/runtime"
	"github.com/spf13/cobra"

	sdkclient "github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/module"
)

const ConsensusVersion = 1

var (
	_ module.AppModuleBasic        = AppModuleBasic{}
	_ module.AppModule             = AppModule{}
	_ module.HasServices           = AppModule{}
	_ appmodule.AppModule          = AppModule{}
	_ appmodule.HasGenesis         = AppModule{}
	_ autocliv1.HasCustomTxCommand = AppModule{}
)

type AppModuleBasic struct{}

func (AppModuleBasic) Name() string { return whaleswap.ModuleName }
func (AppModuleBasic) RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	whaleswap.RegisterLegacyAminoCodec(cdc)
}
func (b AppModuleBasic) RegisterInterfaces(registry cdctypes.InterfaceRegistry) {
	whaleswap.RegisterInterfaces(registry)
}
func (AppModuleBasic) DefaultGenesis(cdc codec.JSONCodec) json.RawMessage {
	return cdc.MustMarshalJSON(whaleswap.DefaultGenesis())
}
func (AppModuleBasic) ValidateGenesis(cdc codec.JSONCodec, _ sdkclient.TxEncodingConfig, bz json.RawMessage) error {
	// Treat empty or "{}" or "null" as default genesis
	trimmed := bytes.TrimSpace(bz)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("{}")) || bytes.Equal(trimmed, []byte("null")) {
		return whaleswap.ValidateGenesisState(*whaleswap.DefaultGenesis())
	}
	var data whaleswaptypes.GenesisState
	if err := cdc.UnmarshalJSON(bz, &data); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", whaleswap.ModuleName, err)
	}
	return whaleswap.ValidateGenesisState(data)
}
func (AppModuleBasic) RegisterGRPCGatewayRoutes(clientCtx sdkclient.Context, mux *gwruntime.ServeMux) {
	if err := whaleswaptypes.RegisterQueryHandlerClient(context.Background(), mux, whaleswaptypes.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}
func (am AppModule) GetTxCmd() *cobra.Command {
	root := &cobra.Command{Use: whaleswap.ModuleName}
	// Attach custom CLI where we need richer flag parsing than autocli supports
	root.AddCommand(whaleswapcli.CmdTakeOffer())
	root.AddCommand(whaleswapcli.CmdCreatePool())
	root.AddCommand(whaleswapcli.CmdUpdatePoolConfig())
	root.AddCommand(whaleswapcli.CmdCoverPosition())
	return root
}
func (am AppModule) GetQueryCmd() *cobra.Command { return &cobra.Command{Use: whaleswap.ModuleName} }

type AppModule struct {
	cdc      codec.Codec
	registry cdctypes.InterfaceRegistry
	keeper   keeper.Keeper
}

func NewAppModule(cdc codec.Codec, keeper keeper.Keeper, registry cdctypes.InterfaceRegistry) AppModule {
	return AppModule{cdc: cdc, keeper: keeper, registry: registry}
}

func (AppModule) IsAppModule()    {}
func (am AppModule) Name() string { return whaleswap.ModuleName }

// Core API genesis (appmodule.HasGenesis)
func (am AppModule) ValidateGenesis(source appmodule.GenesisSource) error {
	reader, err := source(whaleswap.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get genesis source for %s: %w", whaleswap.ModuleName, err)
	}
	if reader == nil {
		// validate defaults
		return whaleswap.ValidateGenesisState(*whaleswap.DefaultGenesis())
	}
	defer func(rc io.ReadCloser) { _ = rc.Close() }(reader)
	// Read full JSON to detect empty object or null
	raw, err := io.ReadAll(reader)
	if err != nil {
		return fmt.Errorf("failed to read %s genesis: %w", whaleswap.ModuleName, err)
	}
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("{}")) || bytes.Equal(trimmed, []byte("null")) {
		return whaleswap.ValidateGenesisState(*whaleswap.DefaultGenesis())
	}
	var tmp whaleswaptypes.GenesisState
	if err := json.Unmarshal(trimmed, &tmp); err != nil {
		return fmt.Errorf("failed to decode %s genesis: %w", whaleswap.ModuleName, err)
	}
	return whaleswap.ValidateGenesisState(tmp)
}
func (am AppModule) InitGenesis(ctx context.Context, source appmodule.GenesisSource) error {
	reader, err := source(whaleswap.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get genesis source for %s: %w", whaleswap.ModuleName, err)
	}
	var gs *whaleswaptypes.GenesisState
	if reader == nil {
		gs = whaleswap.DefaultGenesis()
	} else {
		defer func(rc io.ReadCloser) { _ = rc.Close() }(reader)
		raw, err := io.ReadAll(reader)
		if err != nil {
			return fmt.Errorf("failed to read %s genesis: %w", whaleswap.ModuleName, err)
		}
		trimmed := bytes.TrimSpace(raw)
		if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("{}")) || bytes.Equal(trimmed, []byte("null")) {
			gs = whaleswap.DefaultGenesis()
		} else {
			var tmp whaleswaptypes.GenesisState
			if err := json.Unmarshal(trimmed, &tmp); err != nil {
				return fmt.Errorf("failed to decode %s genesis: %w", whaleswap.ModuleName, err)
			}
			gs = &tmp
		}
	}
	am.keeper.InitGenesis(sdk.UnwrapSDKContext(ctx), gs)
	return nil
}
func (am AppModule) DefaultGenesis(target appmodule.GenesisTarget) error {
	writer, err := target(whaleswap.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get writer for %s genesis: %w", whaleswap.ModuleName, err)
	}
	defer func(w io.WriteCloser) { _ = w.Close() }(writer)
	return json.NewEncoder(writer).Encode(whaleswap.DefaultGenesis())
}
func (am AppModule) ExportGenesis(ctx context.Context, target appmodule.GenesisTarget) error {
	gs := am.keeper.ExportGenesis(sdk.UnwrapSDKContext(ctx))
	writer, err := target(whaleswap.ModuleName)
	if err != nil {
		return fmt.Errorf("failed to get writer for %s export: %w", whaleswap.ModuleName, err)
	}
	defer func(w io.WriteCloser) { _ = w.Close() }(writer)
	return json.NewEncoder(writer).Encode(gs)
}
func (AppModule) RegisterInterfaces(registrar cdctypes.InterfaceRegistry) {
	whaleswap.RegisterInterfaces(registrar)
}
func (am AppModule) RegisterServices(cfg module.Configurator) {
	whaleswaptypes.RegisterMsgServer(cfg.MsgServer(), am.keeper)
	whaleswaptypes.RegisterQueryServer(cfg.QueryServer(), am.keeper)
}
func (AppModule) RegisterMigrations() error          { return nil }
func (AppModule) ConsensusVersion() uint64           { return ConsensusVersion }
func (AppModule) EndBlock(ctx context.Context) error { return nil }
func (AppModule) RegisterGRPCGatewayRoutes(clientCtx sdkclient.Context, mux *gwruntime.ServeMux) {
	if err := whaleswaptypes.RegisterQueryHandlerClient(context.Background(), mux, whaleswaptypes.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}
func (AppModule) RegisterLegacyAminoCodec(registrar *codec.LegacyAmino) {
	whaleswap.RegisterLegacyAminoCodec(registrar)
}
