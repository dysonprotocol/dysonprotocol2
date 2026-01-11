package cmd

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	cmtcfg "github.com/cometbft/cometbft/config"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"

	"cosmossdk.io/log"

	"dysonprotocol.com"
	"dysonprotocol.com/dysond/params"
	"dysonprotocol.com/dysond/server/dwapp"

	confixcmd "cosmossdk.io/tools/confix/cmd"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/client/debug"
	"github.com/cosmos/cosmos-sdk/client/keys"
	"github.com/cosmos/cosmos-sdk/client/pruning"
	"github.com/cosmos/cosmos-sdk/client/rpc"
	"github.com/cosmos/cosmos-sdk/client/snapshot"
	"github.com/cosmos/cosmos-sdk/server"
	serverconfig "github.com/cosmos/cosmos-sdk/server/config"
	servertypes "github.com/cosmos/cosmos-sdk/server/types"
	"github.com/cosmos/cosmos-sdk/types/module"
	authcmd "github.com/cosmos/cosmos-sdk/x/auth/client/cli"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	genutilcli "github.com/cosmos/cosmos-sdk/x/genutil/client/cli"
)

// initCometBFTConfig helps to override default CometBFT Config values.
// return cmtcfg.DefaultConfig if no custom configuration is required for the application.
func initCometBFTConfig() *cmtcfg.Config {
	// Initialize with default CometBFT configuration
	cfg := cmtcfg.DefaultConfig()

	// these values put a higher strain on node memory
	// Uncomment to adjust peer connection limits if needed
	// cfg.P2P.MaxNumInboundPeers = 100
	// cfg.P2P.MaxNumOutboundPeers = 40

	return cfg
}

// initAppConfig helps to override default appConfig template and configs.
// It returns a custom app.toml template and default configuration values.
// return "", nil if no custom configuration is required for the application.
func initAppConfig() (string, interface{}) {
	// The following defines custom configuration options for the Dyson protocol

	// CustomConfig defines an arbitrary custom config to extend app.toml.
	// If you don't need it, you can remove it.
	// If you wish to add fields that correspond to flags that aren't in the SDK server config,
	// this custom config can as well help.
	type CustomConfig struct {
		DwApp struct {
			ScriptAddressOrNamePattern string   `mapstructure:"script-address-or-name-pattern"`
			PublicHostTemplate         string   `mapstructure:"public-host-template"`
			Libp2pPort                 int      `mapstructure:"libp2p-port"`
			Libp2pListenAddrs          []string `mapstructure:"libp2p-listen-addrs"`
			Libp2pBootstrapPeers       []string `mapstructure:"libp2p-bootstrap-peers"`
		} `mapstructure:"dwapp"`
	}

	// CustomAppConfig combines the standard SDK config with our custom extensions
	type CustomAppConfig struct {
		serverconfig.Config `mapstructure:",squash"`

		Custom CustomConfig `mapstructure:"custom"`
	}

	// Optionally allow the chain developer to overwrite the SDK's default
	// server config.
	srvCfg := serverconfig.DefaultConfig()
	// The SDK's default minimum gas price is set to "" (empty value) inside
	// app.toml. If left empty by validators, the node will halt on startup.
	// However, the chain developer can set a default app.toml value for their
	// validators here.
	//
	// In summary:
	// - if you leave srvCfg.MinGasPrices = "", all validators MUST tweak their
	//   own app.toml config,
	// - if you set srvCfg.MinGasPrices non-empty, validators CAN tweak their
	//   own app.toml to override, or use this default value.
	//
	// In dysapp, we set the min gas prices to 0.
	srvCfg.MinGasPrices = "0" + params.DefaultBaseDenom
	// srvCfg.BaseConfig.IAVLDisableFastNode = true // disable fastnode by default

	// Set a sensible default for min-retain-blocks based on script module requirements
	// The script module needs access to historical blocks for execution context
	// We set it to DefaultMaxRelativeHistoricalBlocks + 1 to ensure adequate retention
	srvCfg.MinRetainBlocks = uint64(0)

	// Set API Swagger to be enabled by default
	srvCfg.API.Swagger = true
	srvCfg.API.Enable = true

	// Now we set the custom config default values.
	customAppConfig := CustomAppConfig{
		Config: *srvCfg,
		Custom: CustomConfig{
			DwApp: struct {
				ScriptAddressOrNamePattern string   `mapstructure:"script-address-or-name-pattern"`
				PublicHostTemplate         string   `mapstructure:"public-host-template"`
				Libp2pPort                 int      `mapstructure:"libp2p-port"`
				Libp2pListenAddrs          []string `mapstructure:"libp2p-listen-addrs"`
				Libp2pBootstrapPeers       []string `mapstructure:"libp2p-bootstrap-peers"`
			}{
				ScriptAddressOrNamePattern: dwapp.DefaultDwAppPattern,
				PublicHostTemplate:         dwapp.DefaultPublicHostTemplate,
				Libp2pPort:                 dwapp.DefaultConfig().Libp2pPort,
				Libp2pListenAddrs:          dwapp.DefaultConfig().Libp2pListenAddrs,
				Libp2pBootstrapPeers:       dwapp.DefaultConfig().Libp2pBootstrapPeers,
			},
		},
	}

	// The default SDK app template is defined in serverconfig.DefaultConfigTemplate.
	// We append the custom config template to the default one.
	// And we set the default config to the custom app template.
	customAppTemplate := serverconfig.DefaultConfigTemplate + `

###############################################################################
###                         DwApp Configuration                             ###
###############################################################################

[dwapp]
# Regex used to extract a Dyson script identifier from the HTTP Host header.
# 
# Use named capture groups so the server can tell what was matched:
#   - (?P<address>...) matches a dys2 script address (e.g. dys21abcd...)
#   - (?P<name>...)    matches a script name (WITHOUT the .dys suffix it will be added automatically)
#
# Behavior:
#   - If 'address' matches, it is used as the script address.
#   - If 'name' matches, the server automatically appends '.dys' before querying.
#
# Defaults match either a dys2 address or a simple subdomain name anywhere in the host.
#   - Default: '{{ .Custom.DwApp.ScriptAddressOrNamePattern }}'
# Examples:
#   - Host: dys21xyz.example.com   -> address = dys21xyz
#   - Host: myapp.example.com  -> name    = myapp (server uses 'myapp.dys')
#
# Notes:
#   - This must be a valid TOML string literal.
script-address-or-name-pattern = '{{ .Custom.DwApp.ScriptAddressOrNamePattern }}'


# Template for mapping a script id (address or bare name) back to a public host.
# Use {address_or_name} placeholder. Examples:
#   - "{address_or_name}.dys.example.com" -> dys21abc1234567890.dys.example.com or myname.dys.example.com
#   - "{address_or_name}.localhost" -> dys21abc1234567890.localhost or myname.localhost
public-host-template = '{{ .Custom.DwApp.PublicHostTemplate }}'

# Port for the libp2p P2P networking. This port is used for TCP, WebSocket, QUIC, WebTransport, and WebRTC connections.
# Default: 9095
libp2p-port = {{ .Custom.DwApp.Libp2pPort }}

# Custom libp2p listen addresses. If provided, these addresses will be used instead of the default ones.
# When this is set, libp2p-port is ignored. Format: array of multiaddr strings.
# Examples:
#   libp2p-listen-addrs = ["/ip4/0.0.0.0/tcp/9095", "/ip4/0.0.0.0/tcp/9095/ws"]
# Default: [] (empty, uses default addresses with libp2p-port)
libp2p-listen-addrs = {{ .Custom.DwApp.Libp2pListenAddrs }}

# Bootstrap peers for libp2p peer discovery. These are well-known peers that help nodes discover each other.
# Format: array of full multiaddr strings including peer ID.
# Examples:
#   libp2p-bootstrap-peers = [
#     "/ip4/127.0.0.1/tcp/9095/p2p/12D3KooWAbc123...",
#     "/ip4/127.0.0.1/tcp/9096/p2p/12D3KooWDef456..."
#   ]
# Default: [] (no bootstrap peers)
libp2p-bootstrap-peers = {{ .Custom.DwApp.Libp2pBootstrapPeers }}
`

	return customAppTemplate, customAppConfig
}

// GetHomeDir determines the node home directory from environment or default.
func GetHomeDir() string {
	// Check environment variable first
	if home := os.Getenv("DYSON_HOME"); home != "" {
		return home
	}
	return dysonprotocol.DefaultNodeHome
}

// initRootCmd initializes the root command for the Dyson blockchain application.
// It adds all subcommands and flags needed for the full node operation.
// Parameters:
// - rootCmd: The root command to initialize
// - txConfig: Transaction configuration for the app
// - basicManager: Module manager containing all registered modules
func initRootCmd(
	rootCmd *cobra.Command,
	txConfig client.TxConfig,
	basicManager module.BasicManager,
) {

	// Add essential commands for chain initialization and management
	rootCmd.AddCommand(
		genutilcli.InitCmd(basicManager, dysonprotocol.DefaultNodeHome),
		NewTestnetCmd(basicManager, banktypes.GenesisBalancesIterator{}),
		debug.Cmd(),
		confixcmd.ConfigCommand(),
		pruning.Cmd(newApp, dysonprotocol.DefaultNodeHome),
		snapshot.Cmd(newApp),
	)

	// Add commands to start the node with custom options
	server.AddCommandsWithStartCmdOptions(rootCmd, dysonprotocol.DefaultNodeHome, newApp, appExport, server.StartCmdOptions{
		//PostSetup:           setupApps,
		//PostSetupStandalone: setupApps,
	})

	// add keybase, auxiliary RPC, query, genesis, and tx child commands
	rootCmd.AddCommand(
		server.StatusCommand(),
		genesisCommand(txConfig, basicManager),
		queryCommand(),
		txCommand(),
		keys.Commands(),
		joinCommand(),
	)
}

// genesisCommand builds genesis-related `simd genesis` command.
// Users may provide application specific commands as a parameter.
// Parameters:
// - txConfig: Transaction configuration for genesis operations
// - basicManager: Module manager with access to all modules for genesis creation
// - cmds: Optional additional commands to include under the genesis command
// Returns: A cobra.Command with all genesis-related functionality
func genesisCommand(txConfig client.TxConfig, basicManager module.BasicManager, cmds ...*cobra.Command) *cobra.Command {
	cmd := genutilcli.Commands(txConfig, basicManager, dysonprotocol.DefaultNodeHome)

	// Add any additional sub-commands provided by the application
	for _, subCmd := range cmds {
		cmd.AddCommand(subCmd)
	}
	return cmd
}

// queryCommand returns a root CLI command handler for all query commands in the application.
// It aggregates various query subcommands from different modules.
// Returns: A cobra.Command that serves as the parent for all query subcommands
func queryCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:                        "query",
		Aliases:                    []string{"q"},
		Short:                      "Querying subcommands",
		DisableFlagParsing:         false,
		SuggestionsMinimumDistance: 2,
		RunE:                       client.ValidateCmd,
	}

	// Add query subcommands from various modules
	cmd.AddCommand(
		rpc.WaitTxCmd(),               // Wait for a transaction to be included in a block
		server.QueryBlockCmd(),        // Query a block by height
		authcmd.QueryTxsByEventsCmd(), // Query transactions by events
		server.QueryBlocksCmd(),       // Query a range of blocks
		authcmd.QueryTxCmd(),          // Query a specific transaction by hash
		server.QueryBlockResultsCmd(), // Query block results (events, transactions)
	)

	return cmd
}

// txCommand returns a root CLI command handler for all transaction commands.
// This function creates a command tree for transaction operations in the application.
// Returns: A cobra.Command that serves as the parent for all transaction subcommands
func txCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:                        "tx",
		Short:                      "Transactions subcommands",
		DisableFlagParsing:         false,
		SuggestionsMinimumDistance: 2,
		RunE:                       client.ValidateCmd,
	}

	// Add transaction subcommands for signing, broadcasting, encoding/decoding
	cmd.AddCommand(
		authcmd.GetSignCommand(),               // Sign transactions
		authcmd.GetSignBatchCommand(),          // Sign multiple transactions at once
		authcmd.GetMultiSignCommand(),          // Multi-signature for transactions
		authcmd.GetMultiSignBatchCmd(),         // Multi-signature for multiple transactions
		authcmd.GetValidateSignaturesCommand(), // Validate transaction signatures
		authcmd.GetBroadcastCommand(),          // Broadcast signed transactions to the network
		authcmd.GetEncodeCommand(),             // Encode transactions to binary format
		authcmd.GetDecodeCommand(),             // Decode transactions from binary format
		authcmd.GetSimulateCmd(),               // Simulate transaction execution without committing
	)

	return cmd
}

// newApp creates a new instance of the Dyson application.
// This function is used to initialize the application during node startup.
// Parameters:
// - logger: Logger instance for application logging
// - db: Database instance for state persistence
// - traceStore: Writer for recording traces (if enabled)
// - appOpts: Application options for configuration
// Returns: A servertypes.Application instance ready for block processing
func newApp(
	logger log.Logger,
	db dbm.DB,
	traceStore io.Writer,
	appOpts servertypes.AppOptions,
) servertypes.Application {
	// Prepare baseapp options with default settings
	baseappOptions := server.DefaultBaseappOptions(appOpts)

	// Create and return a new Dyson application instance
	return dysonprotocol.NewDysApp(
		logger, db, traceStore, true, // true indicates this is a new application (not loading from existing state)
		appOpts,
		baseappOptions...,
	)
}

// appExport creates a new DysApp instance (optionally at a given height) and exports its state.
// This function is used for state export operations, such as upgrades or snapshots.
// Parameters:
// - logger: Logger instance for application logging
// - db: Database instance with chain state
// - traceStore: Writer for recording traces
// - height: The height at which to export state (-1 for latest height)
// - forZeroHeight: Whether to export state for block height 0
// - jailAllowedAddrs: List of addresses to not jail during export
// - appOpts: Application options for configuration
// - modulesToExport: List of specific modules to export (empty for all)
// Returns: Exported application state and error (if any)
func appExport(
	logger log.Logger,
	db dbm.DB,
	traceStore io.Writer,
	height int64,
	forZeroHeight bool,
	jailAllowedAddrs []string,
	appOpts servertypes.AppOptions,
	modulesToExport []string,
) (servertypes.ExportedApp, error) {
	// Ensure appOpts is the expected viper.Viper type
	viperAppOpts, ok := appOpts.(*viper.Viper)
	if !ok {
		return servertypes.ExportedApp{}, errors.New("appOpts is not viper.Viper")
	}

	// Set invariant check period to 1 for export operations
	viperAppOpts.Set(server.FlagInvCheckPeriod, 1)
	appOpts = viperAppOpts

	var dysApp *dysonprotocol.DysApp
	if height != -1 {
		// Initialize app at specific height for historical export
		dysApp = dysonprotocol.NewDysApp(logger, db, traceStore, false, appOpts)

		// Load state at the requested height
		if err := dysApp.LoadHeight(height); err != nil {
			return servertypes.ExportedApp{}, err
		}
	} else {
		// Initialize app with latest state
		dysApp = dysonprotocol.NewDysApp(logger, db, traceStore, true, appOpts)
	}

	// Export application state and validators
	return dysApp.ExportAppStateAndValidators(forZeroHeight, jailAllowedAddrs, modulesToExport)
}

// RPC response structs for parsing status and genesis responses
type RPCStatusResponse struct {
	Result struct {
		NodeInfo struct {
			ID         string `json:"id"`
			Network    string `json:"network"`
			ListenAddr string `json:"listen_addr"`
		} `json:"node_info"`
		SyncInfo struct {
			LatestBlockHash   string `json:"latest_block_hash"`
			LatestBlockHeight string `json:"latest_block_height"`
		} `json:"sync_info"`
	} `json:"result"`
}

type RPCGenesisResponse struct {
	Result struct {
		Genesis interface{} `json:"genesis"`
	} `json:"result"`
}

// Libp2pBootstrapResponse holds the response from /libp2p/bootstrap endpoint
type Libp2pBootstrapResponse struct {
	PeerID           string   `json:"peerId"`
	Addrs            []string `json:"addrs"`
	RelayListenAddrs []string `json:"relayListenAddrs"`
	ChainID          string   `json:"chainId"`
	BootstrapPeers   []string `json:"bootstrapPeers"`
	TopicPrefix      string   `json:"topicPrefix"`
	Version          string   `json:"version"`
}

// joinCommand creates the 'join' command for joining an existing chain via state sync
func joinCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "join [host]",
		Short: "Join an existing chain using state sync",
		Long: `Join an existing Dyson Protocol chain using state sync.

This command configures your local node to join an existing chain by:
1. Fetching the genesis file from the remote node
2. Getting network status to extract node ID and latest block info  
3. Configuring state sync in config.toml with appropriate settings
4. Setting up p2p.seeds to connect to the remote node
5. Updating client.toml with the chain ID
6. Configuring libp2p bootstrap peers in app.toml (for browser mesh)

By default, uses path-based routing (common with reverse proxies):
  - RPC: {host}/rpc  (for /status, /genesis)
  - API: {host}      (for /libp2p/bootstrap)

Examples:
  # Default path-based routing
  dysond join https://dys2.dysonprotocol.com

  # Custom RPC path
  dysond join https://node.example.com --rpc-path /rpc

  # Port-based routing (no reverse proxy)
  dysond join https://node.example.com --rpc-port 26657 --api-port 1317

  # Skip libp2p configuration
  dysond join https://dys2.dysonprotocol.com --skip-libp2p

Prerequisites:
  - Local node must be initialized: dysond init <moniker>
`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			baseHost := strings.TrimSuffix(args[0], "/")

			// Get flags
			rpcPath, _ := cmd.Flags().GetString("rpc-path")
			rpcPort, _ := cmd.Flags().GetInt("rpc-port")
			apiPort, _ := cmd.Flags().GetInt("api-port")
			skipLibp2p, _ := cmd.Flags().GetBool("skip-libp2p")

			// Build endpoints from base host
			endpoints := buildEndpoints(baseHost, rpcPath, rpcPort, apiPort)

			// Get client context for home directory
			clientCtx := client.GetClientContextFromCmd(cmd)
			homeDir := clientCtx.HomeDir

			// Validate that node is initialized
			configDir := filepath.Join(homeDir, "config")
			if _, err := os.Stat(configDir); os.IsNotExist(err) {
				return fmt.Errorf("node not initialized. Please run: dysond init <moniker>")
			}

			fmt.Printf("Using home directory: %s\n", homeDir)
			fmt.Printf("RPC endpoint: %s\n", endpoints.RPC)
			fmt.Printf("API endpoint: %s\n", endpoints.API)

			// Fetch genesis file
			if err := fetchGenesis(endpoints.RPC, homeDir); err != nil {
				return fmt.Errorf("failed to fetch genesis: %w", err)
			}

			// Get RPC status
			statusInfo, err := getRPCStatus(endpoints.RPC)
			if err != nil {
				return fmt.Errorf("failed to get RPC status: %w", err)
			}

			// Configure state sync
			if err := configureStateSync(homeDir, endpoints.RPC, statusInfo); err != nil {
				return fmt.Errorf("failed to configure state sync: %w", err)
			}

			// Configure client settings
			if err := configureClient(homeDir, endpoints.RPC, statusInfo); err != nil {
				return fmt.Errorf("failed to configure client: %w", err)
			}

			// Configure libp2p bootstrap peers from API endpoint
			if !skipLibp2p {
				if err := configureLibp2pBootstrap(homeDir, endpoints.API); err != nil {
					// Log warning but don't fail - libp2p is optional for node operation
					fmt.Printf("\n⚠️  Warning: Could not configure libp2p bootstrap peers: %v\n", err)
					fmt.Println("   You can manually configure libp2p-bootstrap-peers in app.toml later.")
					fmt.Println("   Or use --skip-libp2p to skip this step.")
				}
			} else {
				fmt.Println("Skipping libp2p configuration (--skip-libp2p)")
			}

			fmt.Println("\n🎉 Node configuration complete!")
			fmt.Println("\nNext steps:")
			fmt.Println("1. Start your node: dysond start")
			fmt.Println("2. Wait for state sync to complete")
			fmt.Println("3. Your node should sync to the latest block height")
			fmt.Printf("\nNetwork: %s\n", statusInfo.Network)
			fmt.Printf("Target height: ~%s\n", statusInfo.LatestBlockHeight)

			return nil
		},
	}

	cmd.Flags().String("rpc-path", "/rpc", "Path prefix for RPC endpoints (e.g., /rpc for {host}/rpc/status)")
	cmd.Flags().Int("rpc-port", 0, "RPC port (if set, uses port-based routing instead of path-based)")
	cmd.Flags().Int("api-port", 0, "API port (if set, uses port-based routing instead of path-based)")
	cmd.Flags().Bool("skip-libp2p", false, "Skip libp2p bootstrap peer configuration")

	return cmd
}

// Endpoints holds the constructed endpoint URLs
type Endpoints struct {
	RPC string // e.g., https://dys2.dysonprotocol.com/rpc
	API string // e.g., https://dys2.dysonprotocol.com
}

// buildEndpoints constructs RPC and API endpoints from a base host
// Supports both path-based routing (default) and port-based routing
func buildEndpoints(baseHost, rpcPath string, rpcPort, apiPort int) *Endpoints {
	// If ports are specified, use port-based routing
	if rpcPort > 0 || apiPort > 0 {
		parsed, err := url.Parse(baseHost)
		if err != nil {
			return &Endpoints{
				RPC: fmt.Sprintf("%s:%d", baseHost, rpcPort),
				API: fmt.Sprintf("%s:%d", baseHost, apiPort),
			}
		}

		scheme := parsed.Scheme
		if scheme == "" {
			scheme = "https"
		}
		host := parsed.Hostname()

		rp := rpcPort
		if rp == 0 {
			rp = 26657
		}
		ap := apiPort
		if ap == 0 {
			ap = 1317
		}

		return &Endpoints{
			RPC: fmt.Sprintf("%s://%s:%d", scheme, host, rp),
			API: fmt.Sprintf("%s://%s:%d", scheme, host, ap),
		}
	}

	// Default: path-based routing
	// RPC at {host}/rpc, API at {host}
	rpcPath = strings.TrimSuffix(rpcPath, "/")
	return &Endpoints{
		RPC: baseHost + rpcPath,
		API: baseHost,
	}
}

// StatusInfo holds the parsed status information from RPC
type StatusInfo struct {
	NodeID            string
	Network           string
	ListenAddr        string
	LatestBlockHash   string
	LatestBlockHeight string
}

// sanitizePeerAddress normalizes a CometBFT listen address into host:port for p2p.seeds.
// - Strips schemes like tcp://, http://, https://
// - Replaces wildcard/loopback hosts (0.0.0.0, 127.0.0.1, ::, localhost) with the host from rpcEndpoint
// - Preserves the port from the listen address when available
func sanitizePeerAddress(rpcEndpoint, listenAddr string) string {
	addr := strings.TrimSpace(listenAddr)
	for _, prefix := range []string{"tcp://", "http://", "https://"} {
		addr = strings.TrimPrefix(addr, prefix)
	}
	addr = strings.TrimSuffix(addr, "/")

	return addr
}

// fetchGenesis fetches the genesis file from RPC endpoint and saves it
func fetchGenesis(rpcEndpoint, homeDir string) error {
	genesisURL := strings.TrimSuffix(rpcEndpoint, "/") + "/genesis"
	fmt.Printf("Fetching genesis from %s...\n", genesisURL)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Get(genesisURL)
	if err != nil {
		return fmt.Errorf("failed to fetch genesis: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("genesis request failed with status: %d", resp.StatusCode)
	}

	var genesisResp RPCGenesisResponse
	if err := json.NewDecoder(resp.Body).Decode(&genesisResp); err != nil {
		return fmt.Errorf("failed to parse genesis response: %w", err)
	}

	// Write genesis to file
	genesisPath := filepath.Join(homeDir, "config", "genesis.json")
	genesisFile, err := os.Create(genesisPath)
	if err != nil {
		return fmt.Errorf("failed to create genesis file: %w", err)
	}
	defer genesisFile.Close()

	encoder := json.NewEncoder(genesisFile)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(genesisResp.Result.Genesis); err != nil {
		return fmt.Errorf("failed to write genesis file: %w", err)
	}

	fmt.Printf("Genesis saved to %s\n", genesisPath)
	return nil
}

// getRPCStatus fetches and parses the RPC status response
func getRPCStatus(rpcEndpoint string) (*StatusInfo, error) {
	statusURL := strings.TrimSuffix(rpcEndpoint, "/") + "/status"
	fmt.Printf("Fetching status from %s...\n", statusURL)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Get(statusURL)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch status: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("status request failed with status: %d", resp.StatusCode)
	}

	var statusResp RPCStatusResponse
	if err := json.NewDecoder(resp.Body).Decode(&statusResp); err != nil {
		return nil, fmt.Errorf("failed to parse status response: %w", err)
	}

	result := statusResp.Result
	statusInfo := &StatusInfo{
		NodeID:            result.NodeInfo.ID,
		Network:           result.NodeInfo.Network,
		ListenAddr:        result.NodeInfo.ListenAddr,
		LatestBlockHash:   result.SyncInfo.LatestBlockHash,
		LatestBlockHeight: result.SyncInfo.LatestBlockHeight,
	}

	fmt.Printf("Node ID: %s\n", statusInfo.NodeID)
	fmt.Printf("Network: %s\n", statusInfo.Network)
	fmt.Printf("Listen address: %s\n", statusInfo.ListenAddr)
	fmt.Printf("Latest block height: %s\n", statusInfo.LatestBlockHeight)
	fmt.Printf("Latest block hash: %s\n", statusInfo.LatestBlockHash)

	return statusInfo, nil
}

// configureStateSync modifies config.toml to set up state sync
func configureStateSync(homeDir, rpcEndpoint string, statusInfo *StatusInfo) error {
	configPath := filepath.Join(homeDir, "config", "config.toml")
	fmt.Printf("Configuring state sync in %s...\n", configPath)

	// Read existing config
	configData, err := os.ReadFile(configPath)
	if err != nil {
		return fmt.Errorf("failed to read config file: %w", err)
	}

	configStr := string(configData)

	// Configure p2p seeds (ensure listen address is host:port without scheme and not wildcard/loopback)
	peerAddr := sanitizePeerAddress(rpcEndpoint, statusInfo.ListenAddr)
	seeds := fmt.Sprintf("%s@%s", statusInfo.NodeID, peerAddr)
	configStr = updateConfigValue(configStr, "seeds", seeds)
	fmt.Printf("Set p2p.seeds = %s\n", seeds)

	// Configure state sync
	configStr = updateConfigValue(configStr, "enable", "true")
	fmt.Println("Set statesync.enable = true")

	// Set RPC servers
	rpcServers := fmt.Sprintf("%s,%s", rpcEndpoint, rpcEndpoint)
	configStr = updateConfigValue(configStr, "rpc_servers", rpcServers)
	fmt.Printf("Set statesync.rpc_servers = %s\n", rpcServers)

	// Set trust height and hash (use latest block from status)
	height, err := strconv.ParseInt(statusInfo.LatestBlockHeight, 10, 64)
	if err != nil {
		return fmt.Errorf("failed to parse block height: %w", err)
	}

	configStr = updateConfigValue(configStr, "trust_height", strconv.FormatInt(height, 10))
	configStr = updateConfigValue(configStr, "trust_hash", fmt.Sprintf(`"%s"`, statusInfo.LatestBlockHash))
	fmt.Printf("Set statesync.trust_height = %d\n", height)
	fmt.Printf("Set statesync.trust_hash = %s\n", statusInfo.LatestBlockHash)

	// Write updated config
	if err := os.WriteFile(configPath, []byte(configStr), 0644); err != nil {
		return fmt.Errorf("failed to write config file: %w", err)
	}

	fmt.Println("Configuration updated successfully!")
	return nil
}

// updateConfigValue updates a TOML config value in a string
func updateConfigValue(config, key, value string) string {
	replacement := fmt.Sprintf(`%s = %s`, key, value)

	// Special handling for quoted values - don't quote if already quoted, is a bool, number, or array
	needsQuotes := !strings.HasPrefix(value, `"`) &&
		!strings.HasPrefix(value, `[`) &&
		key != "enable" &&
		key != "trust_height"
	if needsQuotes {
		replacement = fmt.Sprintf(`%s = "%s"`, key, value)
	}

	if strings.Contains(config, key+" =") || strings.Contains(config, key+"=") {
		// Use simple string replacement for now
		lines := strings.Split(config, "\n")
		for i, line := range lines {
			trimmed := strings.TrimSpace(line)
			if strings.HasPrefix(trimmed, key+" =") || strings.HasPrefix(trimmed, key+"=") {
				// Preserve indentation
				indent := ""
				for _, char := range line {
					if char == ' ' || char == '\t' {
						indent += string(char)
					} else {
						break
					}
				}
				lines[i] = indent + replacement
				break
			}
		}
		config = strings.Join(lines, "\n")
	}

	return config
}

// configureClient modifies client.toml to set up chain ID and node endpoint
func configureClient(homeDir, rpcEndpoint string, statusInfo *StatusInfo) error {
	clientConfigPath := filepath.Join(homeDir, "config", "client.toml")
	fmt.Printf("Configuring client settings in %s...\n", clientConfigPath)

	// Read existing client config
	clientConfigData, err := os.ReadFile(clientConfigPath)
	if err != nil {
		return fmt.Errorf("failed to read client config file: %w", err)
	}

	clientConfigStr := string(clientConfigData)

	// Configure chain ID
	clientConfigStr = updateConfigValue(clientConfigStr, "chain-id", statusInfo.Network)
	fmt.Printf("Set chain-id = %s\n", statusInfo.Network)

	// TODO: maybe prompt to set node endpoint
	// Configure node endpoint
	//clientConfigStr = updateConfigValue(clientConfigStr, "node", rpcEndpoint)
	//fmt.Printf("Set node = %s\n", rpcEndpoint)

	// Write updated client config
	if err := os.WriteFile(clientConfigPath, []byte(clientConfigStr), 0644); err != nil {
		return fmt.Errorf("failed to write client config file: %w", err)
	}

	fmt.Println("Client configuration updated successfully!")
	return nil
}

// getLibp2pBootstrap fetches bootstrap info from the /libp2p/bootstrap endpoint
func getLibp2pBootstrap(apiEndpoint string) (*Libp2pBootstrapResponse, error) {
	bootstrapURL := strings.TrimSuffix(apiEndpoint, "/") + "/libp2p/bootstrap"
	fmt.Printf("Fetching libp2p bootstrap from %s...\n", bootstrapURL)

	httpClient := &http.Client{Timeout: 30 * time.Second}
	resp, err := httpClient.Get(bootstrapURL)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch libp2p bootstrap: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusServiceUnavailable {
		return nil, fmt.Errorf("libp2p is disabled on the remote node")
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("bootstrap request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var bootstrapResp Libp2pBootstrapResponse
	if err := json.NewDecoder(resp.Body).Decode(&bootstrapResp); err != nil {
		return nil, fmt.Errorf("failed to parse bootstrap response: %w", err)
	}

	return &bootstrapResp, nil
}

// configureLibp2pBootstrap fetches bootstrap info and updates app.toml
func configureLibp2pBootstrap(homeDir, apiEndpoint string) error {
	// Fetch bootstrap info from remote node
	bootstrapInfo, err := getLibp2pBootstrap(apiEndpoint)
	if err != nil {
		return err
	}

	if bootstrapInfo.PeerID == "" {
		return fmt.Errorf("remote node returned empty peer ID")
	}

	fmt.Printf("Remote libp2p peer ID: %s\n", bootstrapInfo.PeerID)
	fmt.Printf("Remote libp2p addresses: %d total\n", len(bootstrapInfo.Addrs))

	// Build bootstrap peer multiaddrs
	// Note: addresses from /libp2p/bootstrap already include /p2p/{peerID} suffix
	var bootstrapPeers []string
	for _, addr := range bootstrapInfo.Addrs {
		// Only use addresses that are externally reachable (not localhost/0.0.0.0)
		if isExternalAddress(addr) {
			// Address already includes peer ID, use as-is
			bootstrapPeers = append(bootstrapPeers, addr)
		}
	}

	// Also include any pre-configured bootstrap peers from the remote node
	bootstrapPeers = append(bootstrapPeers, bootstrapInfo.BootstrapPeers...)

	if len(bootstrapPeers) == 0 {
		return fmt.Errorf("no usable bootstrap peer addresses found")
	}

	// Update app.toml
	appConfigPath := filepath.Join(homeDir, "config", "app.toml")
	fmt.Printf("Configuring libp2p bootstrap peers in %s...\n", appConfigPath)

	appConfigData, err := os.ReadFile(appConfigPath)
	if err != nil {
		return fmt.Errorf("failed to read app config file: %w", err)
	}

	appConfigStr := string(appConfigData)

	// Format bootstrap peers as TOML array
	peersFormatted := formatTOMLStringArray(bootstrapPeers)
	appConfigStr = updateConfigValue(appConfigStr, "libp2p-bootstrap-peers", peersFormatted)

	if err := os.WriteFile(appConfigPath, []byte(appConfigStr), 0644); err != nil {
		return fmt.Errorf("failed to write app config file: %w", err)
	}

	fmt.Printf("Set libp2p-bootstrap-peers with %d peer(s)\n", len(bootstrapPeers))
	for _, peer := range bootstrapPeers {
		fmt.Printf("  - %s\n", peer)
	}

	return nil
}

// isExternalAddress checks if a multiaddr is externally reachable
func isExternalAddress(addr string) bool {
	// Skip localhost, loopback, and wildcard addresses
	localPatterns := []string{
		"/ip4/127.",
		"/ip4/0.0.0.0",
		"/ip6/::1",
		"/ip6/::",
		"/dns4/localhost",
		"/dns6/localhost",
	}

	for _, pattern := range localPatterns {
		if strings.Contains(addr, pattern) {
			return false
		}
	}

	return true
}

// formatTOMLStringArray formats a string slice as a TOML array
func formatTOMLStringArray(items []string) string {
	if len(items) == 0 {
		return "[]"
	}

	var quoted []string
	for _, item := range items {
		quoted = append(quoted, fmt.Sprintf(`"%s"`, item))
	}

	return "[" + strings.Join(quoted, ", ") + "]"
}

/*
// setupDwApp initializes and starts the dwapp server for serving script web applications
func setupDwApp(svrCtx *server.Context, clientCtx client.Context, ctx context.Context, g *errgroup.Group) error {
	// Get the dwapp configuration from viper
	svrCtx.Logger.Info("Setting up dwapp server")
	dwappConfig := dwapp.DefaultConfig()

	// Try to get configuration from viper
	if v := svrCtx.Viper.Get("custom.dwapp"); v != nil {
		if err := svrCtx.Viper.UnmarshalKey("custom.dwapp", dwappConfig); err != nil {
			return fmt.Errorf("failed to parse dwapp config: %w", err)
		}
	}

	// Check CLI flag overrides
	if svrCtx.Viper.IsSet("dwapp.enable") {
		dwappConfig.Enable = svrCtx.Viper.GetBool("dwapp.enable")
	}

	if svrCtx.Viper.IsSet("dwapp.script-address-or-name-pattern") {
		dwappConfig.ScriptAddressOrNamePattern = svrCtx.Viper.GetString("dwapp.script-address-or-name-pattern")
	}

	// If dwapp is not enabled, don't start it
	if !dwappConfig.Enable {
		svrCtx.Logger.Info("dwapp server is disabled")
		return nil
	}

	// Create and start the dwapp server
	// We use client context for gRPC queries instead of direct app access
	dwappServer, err := dwapp.New(svrCtx.Logger, clientCtx, svrCtx.Viper)
	if err != nil {
		return fmt.Errorf("failed to create dwapp server: %w", err)
	}

	// Add to the errgroup to manage lifecycle
	g.Go(func() error {
		return dwappServer.Start(ctx)
	})

	return nil
}

// setupApps initializes and starts all servers: demo app and dwapp
func setupApps(svrCtx *server.Context, clientCtx client.Context, ctx context.Context, g *errgroup.Group) error {
	svrCtx.Logger.Info("Setting up application servers")

	// First set up the dwapp
	if err := setupDwApp(svrCtx, clientCtx, ctx, g); err != nil {
		return fmt.Errorf("failed to set up dw app: %w", err)
	}

	return nil

*/
