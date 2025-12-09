package dwapp

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync"

	"cosmossdk.io/log"
	serverconfig "github.com/cosmos/cosmos-sdk/server/config"
	"github.com/spf13/viper"

	"github.com/cosmos/cosmos-sdk/client"
)

const (
	ServerName                = "dwapp"
	DefaultDwAppPattern       = `((?P<address>dys21[a-z0-9]+)|(?P<name>[a-z0-9-]+))\.`
	DefaultPublicHostTemplate = "{address_or_name}.localhost:1317"
)

// CfgOption defines a function to modify the configuration.
type CfgOption func(*DwAppConfig)

// Config represents the configuration data structure for the DW APP Server.
type DwAppConfig struct {
	// Inherit from the standard server config
	serverconfig.Config `mapstructure:",squash"`

	// Additional fields specific to dwapp
	Enable                     bool     `mapstructure:"enable"`
	ScriptAddressOrNamePattern string   `mapstructure:"script-address-or-name-pattern"`
	PublicHostTemplate         string   `mapstructure:"public-host-template"`
	Libp2pPort                 int      `mapstructure:"libp2p-port"`
	Libp2pListenAddrs          []string `mapstructure:"libp2p-listen-addrs"`
	Libp2pBootstrapPeers       []string `mapstructure:"libp2p-bootstrap-peers"`
}

// Combined explicit server configuration
type ListenAddressConfig struct {
	DwApp DwAppConfig `json:"dwapp"`
}

// DefaultConfig returns the default configuration for the DW APP Server.
func DefaultConfig() *DwAppConfig {
	return &DwAppConfig{
		Config:                     *serverconfig.DefaultConfig(),
		Enable:                     true,
		ScriptAddressOrNamePattern: DefaultDwAppPattern,
		PublicHostTemplate:         DefaultPublicHostTemplate,
		Libp2pPort:                 9095,
		Libp2pListenAddrs:          []string{},
		Libp2pBootstrapPeers:       []string{},
	}
}

// ExtractListenAddressConfig extracts server configuration from viper
func ExtractListenAddressConfig(viperCfg *viper.Viper) *ListenAddressConfig {
	dwAppConfig := DwAppConfig{}
	if err := viperCfg.UnmarshalKey("dwapp", &dwAppConfig); err != nil {
		// raise error
		panic(err)
	}
	return &ListenAddressConfig{DwApp: dwAppConfig}
}

// Server mainly exists to serve DysonScript APIs and HTML UIs using gRPC client context
type Server struct {
	logger              log.Logger
	router              *http.ServeMux
	httpServer          *http.Server
	config              *DwAppConfig
	listenAddressConfig *ListenAddressConfig
	cfgOptions          []CfgOption
	clientCtx           client.Context
	mtx                 sync.Mutex
}

// APIHandler sets up the HTTP endpoints for the Dyson Script API
func APIHandler(router *http.ServeMux, srv *Server) {
	// Add the listenaddress.json endpoint
	/*
		router.HandleFunc("/_/listenaddress.json", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet {
				http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
				return
			}

			jsonData, err := json.MarshalIndent(srv.listenAddressConfig, "", "  ")
			if err != nil {
				http.Error(w, "Failed to marshal config: "+err.Error(), http.StatusInternalServerError)
				return
			}

			w.Header().Set("Content-Type", "application/json")
			w.Write(jsonData)
		})

		// Add the endpoint listing

		router.HandleFunc("/_/", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet {
				http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
				return
			}

			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			fmt.Fprintln(w, "<html><body><h1>Available Endpoints</h1><ul>")

			// Define endpoints with their URLs and descriptions
			type endpoint struct {
				URL         string
				Method      string
				Description string
			}

			endpoints := []endpoint{
				{URL: "/", Method: "GET", Description: "Main application endpoint"},
				{URL: "/_/", Method: "GET", Description: "List all available endpoints"},
				{URL: "/_/listenaddress.json", Method: "GET", Description: "Server listen address configuration"},
			}

			// Generate list items with clickable links
			for _, ep := range endpoints {
				fmt.Fprintf(w, "<li><a href=\"%s\">%s</a> - %s (%s)</li>\n",
					ep.URL, ep.URL, ep.Description, ep.Method)
			}

			fmt.Fprintln(w, "</ul></body></html>")
		})
	*/
}

// New creates a new Server with default config for HTTP DW APP Server
func New(
	logger log.Logger,
	clientCtx client.Context,
	viperConfig *viper.Viper,
	cfgOptions ...CfgOption,
) (*Server, error) {
	srv := &Server{
		logger:     logger.With("module", ServerName),
		cfgOptions: cfgOptions,
		router:     http.NewServeMux(),
		clientCtx:  clientCtx,
	}

	// Parse the configuration from viper
	serverCfg := DefaultConfig()

	// Apply custom configuration options
	for _, opt := range cfgOptions {
		opt(serverCfg)
	}

	srv.config = serverCfg
	srv.listenAddressConfig = ExtractListenAddressConfig(viperConfig)

	// Override default config with values from viper if they exist

	if viperConfig.IsSet("dwapp.enable") {
		srv.config.Enable = viperConfig.GetBool("dwapp.enable")
		srv.logger.Info("Overriding default enable with config value", "enable", srv.config.Enable)
	}
	if viperConfig.IsSet("dwapp.script-address-or-name-pattern") {
		srv.config.ScriptAddressOrNamePattern = viperConfig.GetString("dwapp.script-address-or-name-pattern")
		srv.logger.Info("Overriding default pattern with config value", "pattern", srv.config.ScriptAddressOrNamePattern)
	}
	if viperConfig.IsSet("dwapp.public-host-template") {
		srv.config.PublicHostTemplate = viperConfig.GetString("dwapp.public-host-template")
		srv.logger.Info("Overriding default public host template with config value", "public_host_template", srv.config.PublicHostTemplate)
	}
	if viperConfig.IsSet("dwapp.libp2p-port") {
		srv.config.Libp2pPort = viperConfig.GetInt("dwapp.libp2p-port")
		srv.logger.Info("Overriding default libp2p port with config value", "libp2p_port", srv.config.Libp2pPort)
	}
	if viperConfig.IsSet("dwapp.libp2p-listen-addrs") {
		srv.config.Libp2pListenAddrs = viperConfig.GetStringSlice("dwapp.libp2p-listen-addrs")
		srv.logger.Info("Overriding default libp2p listen addresses with config value", "libp2p_listen_addrs", srv.config.Libp2pListenAddrs)
	}
	if viperConfig.IsSet("dwapp.libp2p-bootstrap-peers") {
		srv.config.Libp2pBootstrapPeers = viperConfig.GetStringSlice("dwapp.libp2p-bootstrap-peers")
		srv.logger.Info("Overriding default libp2p bootstrap peers with config value", "libp2p_bootstrap_peers", srv.config.Libp2pBootstrapPeers)
	}

	srv.httpServer = &http.Server{

		Handler: srv.router,
	}

	logger.Info("DWApp config",
		"enable", srv.config.Enable,
		"pattern", srv.config.ScriptAddressOrNamePattern,
	)

	srv.router.Handle("/", NewDefaultHandler(srv.logger, clientCtx, srv.config.ScriptAddressOrNamePattern, srv.config.PublicHostTemplate, srv.config.Libp2pBootstrapPeers))
	// Pass the server to APIHandler
	APIHandler(srv.router, srv)

	return srv, nil
}

// Name returns the name of the server
func (s *Server) Name() string {
	return ServerName
}

// Start starts the server
func (s *Server) Start(ctx context.Context) error {
	s.mtx.Lock()

	// Check if server is enabled
	if !s.config.Enable {
		s.logger.Info(fmt.Sprintf("%s DWApp is disabled via config", s.Name()))
		s.mtx.Unlock()
		return nil
	}

	s.mtx.Unlock()

	// Create error channel for server errors
	errCh := make(chan error, 1)

	// Start the server in a goroutine
	go func() {
		//s.logger.Info("starting DWApp server", "address", s.config.Address)
		if err := s.httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			s.logger.Error("failed to start DWApp server", "error", err)
			errCh <- err
		}
	}()

	// Wait for either context cancellation or an error
	select {
	case <-ctx.Done():
		// Context was canceled, shut down gracefully
		return s.Stop(context.Background())
	case err := <-errCh:
		return err
	}
}

// Stop stops the server
func (s *Server) Stop(ctx context.Context) error {
	s.mtx.Lock()
	defer s.mtx.Unlock()

	// Check if server is enabled
	if !s.config.Enable {
		return nil
	}

	s.logger.Info("stopping DWApp server")
	return s.httpServer.Shutdown(ctx)
}
