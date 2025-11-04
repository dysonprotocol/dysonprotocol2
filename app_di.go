//go:build !app_v1

package dysonprotocol

import (
	"io"

	crontaskkeeper "dysonprotocol.com/x/crontask/keeper"
	nameservicekeeper "dysonprotocol.com/x/nameservice/keeper"
	scriptkeeper "dysonprotocol.com/x/script/keeper"
	storagekeeper "dysonprotocol.com/x/storage/keeper"
	dbm "github.com/cosmos/cosmos-db"

	clienthelpers "cosmossdk.io/client/v2/helpers"
	"cosmossdk.io/depinject"
	"cosmossdk.io/log"
	storetypes "cosmossdk.io/store/types"
	evidencekeeper "cosmossdk.io/x/evidence/keeper"
	feegrantkeeper "cosmossdk.io/x/feegrant/keeper"
	upgradekeeper "cosmossdk.io/x/upgrade/keeper"
	nftkeeper "dysonprotocol.com/x/nft/keeper"

	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/runtime"
	"github.com/cosmos/cosmos-sdk/server/api"
	"github.com/cosmos/cosmos-sdk/server/config"
	servertypes "github.com/cosmos/cosmos-sdk/server/types"
	testdata_pulsar "github.com/cosmos/cosmos-sdk/testutil/testdata/testpb"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/module"
	"github.com/cosmos/cosmos-sdk/x/auth"
	"github.com/cosmos/cosmos-sdk/x/auth/ante"
	authkeeper "github.com/cosmos/cosmos-sdk/x/auth/keeper"
	authsims "github.com/cosmos/cosmos-sdk/x/auth/simulation"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	authzkeeper "github.com/cosmos/cosmos-sdk/x/authz/keeper"
	bankkeeper "github.com/cosmos/cosmos-sdk/x/bank/keeper"
	consensuskeeper "github.com/cosmos/cosmos-sdk/x/consensus/keeper"
	distrkeeper "github.com/cosmos/cosmos-sdk/x/distribution/keeper"

	//epochskeeper "github.com/cosmos/cosmos-sdk/x/epochs/keeper"
	govkeeper "github.com/cosmos/cosmos-sdk/x/gov/keeper"
	mintkeeper "github.com/cosmos/cosmos-sdk/x/mint/keeper"
	protocolpoolkeeper "github.com/cosmos/cosmos-sdk/x/protocolpool/keeper"
	slashingkeeper "github.com/cosmos/cosmos-sdk/x/slashing/keeper"
	stakingkeeper "github.com/cosmos/cosmos-sdk/x/staking/keeper"

	dysondserver "dysonprotocol.com/dysond/server"
	"dysonprotocol.com/dysond/server/dwapp"

	// params for subspaces
	paramstypes "github.com/cosmos/cosmos-sdk/x/params/types"
)

// DefaultNodeHome default home directories for the application daemon
var DefaultNodeHome string

var (
	_ runtime.AppI            = (*DysApp)(nil)
	_ servertypes.Application = (*DysApp)(nil)
)

// DysApp extends an ABCI application, but with most of its parameters exported.
// They are exported for convenience in creating helper functions, as object
// capabilities aren't needed for testing.
type DysApp struct {
	*runtime.App
	legacyAmino       *codec.LegacyAmino
	appCodec          codec.Codec
	txConfig          client.TxConfig
	interfaceRegistry codectypes.InterfaceRegistry

	// essential keepers
	AccountKeeper         authkeeper.AccountKeeper
	BankKeeper            bankkeeper.BaseKeeper
	StakingKeeper         *stakingkeeper.Keeper
	SlashingKeeper        slashingkeeper.Keeper
	MintKeeper            mintkeeper.Keeper
	DistrKeeper           distrkeeper.Keeper
	GovKeeper             *govkeeper.Keeper
	UpgradeKeeper         *upgradekeeper.Keeper
	EvidenceKeeper        evidencekeeper.Keeper
	ConsensusParamsKeeper consensuskeeper.Keeper

	// supplementary keepers
	FeeGrantKeeper feegrantkeeper.Keeper
	AuthzKeeper    authzkeeper.Keeper
	NFTKeeper      nftkeeper.Keeper
	// EpochsKeeper       epochskeeper.Keeper
	ProtocolPoolKeeper protocolpoolkeeper.Keeper

	// Custom module keepers
	NameserviceKeeper nameservicekeeper.Keeper
	ScriptKeeper      scriptkeeper.Keeper
	StorageKeeper     storagekeeper.Keeper
	CrontaskKeeper    crontaskkeeper.Keeper

	// simulation manager
	sm *module.SimulationManager
}

func init() {
	var err error
	DefaultNodeHome, err = clienthelpers.GetNodeHomeDirectory(".dysonprotocol")
	if err != nil {
		panic(err)
	}
}

// NewDysApp returns a reference to an initialized DysApp.
func NewDysApp(
	logger log.Logger,
	db dbm.DB,
	traceStore io.Writer,
	loadLatest bool,
	appOpts servertypes.AppOptions,
	baseAppOptions ...func(*baseapp.BaseApp),
) *DysApp {
	var (
		app        = &DysApp{}
		appBuilder *runtime.AppBuilder

		// merge the AppConfig and other configuration in one config
		appConfig = depinject.Configs(
			AppConfig,
			depinject.Supply(
				// supply the application options
				appOpts,
				// supply the logger
				logger,

				// ADVANCED CONFIGURATION

				//
				// AUTH
				//
				// For providing a custom function required in auth to generate custom account types
				// add it below. By default the auth module uses simulation.RandomGenesisAccounts.
				//
				// authtypes.RandomGenesisAccountsFn(simulation.RandomGenesisAccounts),
				//
				// For providing a custom a base account type add it below.
				// By default the auth module uses authtypes.ProtoBaseAccount().
				//
				// func() sdk.AccountI { return authtypes.ProtoBaseAccount() },
				//
				// For providing a different address codec, add it below.
				// By default the auth module uses a Bech32 address codec,
				// with the prefix defined in the auth module configuration.
				//
				// func() address.Codec { return <- custom address codec type -> }

				//
				// STAKING
				//
				// For provinding a different validator and consensus address codec, add it below.
				// By default the staking module uses the bech32 prefix provided in the auth config,
				// and appends "valoper" and "valcons" for validator and consensus addresses respectively.
				// When providing a custom address codec in auth, custom address codecs must be provided here as well.
				//
				// func() runtime.ValidatorAddressCodec { return <- custom validator address codec type -> }
				// func() runtime.ConsensusAddressCodec { return <- custom consensus address codec type -> }

				//
				// MINT
				//

				// For providing a custom inflation function for x/mint add here your
				// custom function that implements the minttypes.InflationCalculationFn
				// interface.
			),
		)
	)

	// Allow 1-127 character denoms (first char letter, then 0-126 of allowed charset)
	sdk.SetCoinDenomRegex(func() string { return `[a-zA-Z][a-zA-Z0-9/:._-]{0,126}` })

	if err := depinject.Inject(appConfig,
		&appBuilder,
		&app.appCodec,
		&app.legacyAmino,
		&app.txConfig,
		&app.interfaceRegistry,
		&app.AccountKeeper,
		&app.BankKeeper,
		&app.StakingKeeper,
		&app.SlashingKeeper,
		&app.MintKeeper,
		&app.DistrKeeper,
		&app.GovKeeper,
		&app.UpgradeKeeper,
		&app.EvidenceKeeper,
		&app.ConsensusParamsKeeper,

		&app.FeeGrantKeeper,
		&app.AuthzKeeper,
		&app.NFTKeeper,
		// &app.EpochsKeeper,
		&app.ProtocolPoolKeeper,
		&app.NameserviceKeeper,
		&app.ScriptKeeper,
		&app.StorageKeeper,
		&app.CrontaskKeeper,
	); err != nil {
		panic(err)
	}

	// Below we could construct and set an application specific mempool and
	// ABCI 1.0 PrepareProposal and ProcessProposal handlers. These defaults are
	// already set in the SDK's BaseApp, this shows an example of how to override
	// them.
	//
	// Example:
	//
	// app.App = appBuilder.Build(...)
	// nonceMempool := mempool.NewSenderNonceMempool()
	// abciPropHandler := NewDefaultProposalHandler(nonceMempool, app.App.BaseApp)
	//
	// app.App.BaseApp.SetMempool(nonceMempool)
	// app.App.BaseApp.SetPrepareProposal(abciPropHandler.PrepareProposalHandler())
	// app.App.BaseApp.SetProcessProposal(abciPropHandler.ProcessProposalHandler())
	//
	// Alternatively, you can construct BaseApp options, append those to
	// baseAppOptions and pass them to the appBuilder.
	//
	// Example:
	//
	// prepareOpt = func(app *baseapp.BaseApp) {
	// 	abciPropHandler := baseapp.NewDefaultProposalHandler(nonceMempool, app)
	// 	app.SetPrepareProposal(abciPropHandler.PrepareProposalHandler())
	// }
	// baseAppOptions = append(baseAppOptions, prepareOpt)


	app.App = appBuilder.Build(db, traceStore, baseAppOptions...)

	// register streaming services
	if err := app.RegisterStreamingServices(appOpts, app.kvStoreKeys()); err != nil {
		panic(err)
	}

	/****  Module Options ****/

	// RegisterUpgradeHandlers is used for registering any on-chain upgrades.
	app.RegisterUpgradeHandlers()

	// add test gRPC service for testing gRPC queries in isolation
	testdata_pulsar.RegisterQueryServer(app.GRPCQueryRouter(), testdata_pulsar.QueryImpl{})

	// create the simulation manager and define the order of the modules for deterministic simulations
	//
	// NOTE: this is not required apps that don't use the simulator for fuzz testing
	// transactions
	overrideModules := map[string]module.AppModuleSimulation{
		authtypes.ModuleName: auth.NewAppModule(app.appCodec, app.AccountKeeper, authsims.RandomGenesisAccounts, nil),
	}
	app.sm = module.NewSimulationManagerFromAppModules(app.ModuleManager.Modules, overrideModules)

	app.sm.RegisterStoreDecoders()

	// set custom ante handler
	app.setAnteHandler(app.txConfig)

	if err := app.Load(loadLatest); err != nil {
		panic(err)
	}

	return app
}

// setAnteHandler sets custom ante handlers.
// "x/auth/tx" pre-defined ante handler have been disabled in app_config.
func (app *DysApp) setAnteHandler(txConfig client.TxConfig) {
	// Create a HandlerOptions using the proper fields from the latest Cosmos SDK
	handlerOpts := ante.HandlerOptions{
		AccountKeeper:   app.AccountKeeper,
		BankKeeper:      app.BankKeeper,
		SignModeHandler: txConfig.SignModeHandler(),
		FeegrantKeeper:  app.FeeGrantKeeper,
		SigGasConsumer:  ante.DefaultSigVerificationGasConsumer,
		// Add SigVerifyOptions for unordered transactions
		SigVerifyOptions: []ante.SigVerificationDecoratorOption{
			ante.WithUnorderedTxGasCost(ante.DefaultUnorderedTxGasCost),
			ante.WithMaxUnorderedTxTimeoutDuration(ante.DefaultMaxTimeoutDuration),
		},
	}

	anteHandler, err := NewAnteHandler(
		HandlerOptions{
			handlerOpts,
		},
	)
	if err != nil {
		panic(err)
	}

	// Set the AnteHandler for the app
	app.SetAnteHandler(anteHandler)
}

// LegacyAmino returns DysApp's amino codec.
//
// NOTE: This is solely to be used for testing purposes as it may be desirable
// for modules to register their own custom testing types.
func (app *DysApp) LegacyAmino() *codec.LegacyAmino {
	return app.legacyAmino
}

// AppCodec returns DysApp's app codec.
//
// NOTE: This is solely to be used for testing purposes as it may be desirable
// for modules to register their own custom testing types.
func (app *DysApp) AppCodec() codec.Codec {
	return app.appCodec
}

// InterfaceRegistry returns DysApp's InterfaceRegistry.
func (app *DysApp) InterfaceRegistry() codectypes.InterfaceRegistry {
	return app.interfaceRegistry
}

// TxConfig returns DysApp's TxConfig
func (app *DysApp) TxConfig() client.TxConfig {
	return app.txConfig
}

// GetKey returns the KVStoreKey for the provided store key.
//
// NOTE: This is solely to be used for testing purposes.
func (app *DysApp) GetKey(storeKey string) *storetypes.KVStoreKey {
	sk := app.UnsafeFindStoreKey(storeKey)
	kvStoreKey, ok := sk.(*storetypes.KVStoreKey)
	if !ok {
		return nil
	}
	return kvStoreKey
}

func (app *DysApp) kvStoreKeys() map[string]*storetypes.KVStoreKey {
	keys := make(map[string]*storetypes.KVStoreKey)
	for _, k := range app.GetStoreKeys() {
		if kv, ok := k.(*storetypes.KVStoreKey); ok {
			keys[kv.Name()] = kv
		}
	}

	return keys
}

// SimulationManager implements the SimulationApp interface
func (app *DysApp) SimulationManager() *module.SimulationManager {
	return app.sm
}

// RegisterAPIRoutes registers all application module routes with the provided
// API server.
func (app *DysApp) RegisterAPIRoutes(apiSvr *api.Server, apiConfig config.APIConfig) {
	app.App.RegisterAPIRoutes(apiSvr, apiConfig)
	// register swagger API in app.go so that other applications can override easily

	// Get the dwapp configuration values
	scriptPattern := ""
	publicHostTemplate := ""
	libp2pPort := dwapp.DefaultConfig().Libp2pPort
	libp2pListenAddrs := dwapp.DefaultConfig().Libp2pListenAddrs

	// Read from viper if available
	libp2pBootstrapPeers := []string{}
	if apiSvr.ClientCtx.Viper != nil {
		if apiSvr.ClientCtx.Viper.IsSet("dwapp.libp2p-port") {
			libp2pPort = apiSvr.ClientCtx.Viper.GetInt("dwapp.libp2p-port")
		}
		if apiSvr.ClientCtx.Viper.IsSet("dwapp.libp2p-listen-addrs") {
			libp2pListenAddrs = apiSvr.ClientCtx.Viper.GetStringSlice("dwapp.libp2p-listen-addrs")
		}
		if apiSvr.ClientCtx.Viper.IsSet("dwapp.libp2p-bootstrap-peers") {
			libp2pBootstrapPeers = apiSvr.ClientCtx.Viper.GetStringSlice("dwapp.libp2p-bootstrap-peers")
		}
	}

	if err := dysondserver.RegisterDysonServer(apiSvr.ClientCtx, apiSvr.Router, apiConfig, scriptPattern, publicHostTemplate, libp2pPort, libp2pListenAddrs, libp2pBootstrapPeers); err != nil {
		panic(err)
	}
}

// GetMaccPerms returns a copy of the module account permissions
//
// NOTE: This is solely to be used for testing purposes.
func GetMaccPerms() map[string][]string {
	dup := make(map[string][]string)
	for _, perms := range moduleAccPerms {
		dup[perms.Account] = perms.Permissions
	}

	return dup
}

// BlockedAddresses returns all the app's blocked account addresses.
func BlockedAddresses() map[string]bool {
	result := make(map[string]bool)

	if len(blockAccAddrs) > 0 {
		for _, addr := range blockAccAddrs {
			result[addr] = true
		}
	} else {
		for addr := range GetMaccPerms() {
			result[addr] = true
		}
	}

	return result
}

// GetSubspace returns a param subspace for a given module name.
// since our app uses app_config.go for configuration instead of ParamsKeeper.
func (app *DysApp) GetSubspace(moduleName string) paramstypes.Subspace {
	// Return a dummy subspace that doesn't actually store or retrieve data
	return paramstypes.Subspace{}
}

// MsgServiceRouter returns the app's MsgServiceRouter.
func (app *DysApp) MsgServiceRouter() *baseapp.MsgServiceRouter {
	return app.App.MsgServiceRouter()
}
func (app *DysApp) initializeIBCModules() {
	// This function is intentionally empty
}
