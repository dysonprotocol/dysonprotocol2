package server

import (
	"context"
	"fmt"
	"io/fs"
	"net/http"
	"strings"

	"cosmossdk.io/log"
	"github.com/gorilla/mux"

	docs "dysonprotocol.com/client/docs"
	"dysonprotocol.com/dysond/server/dwapp"
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/server/config"
)

// RegisterDysonServer provides a common function which registers APIs with API Server
// This includes both Swagger API (if enabled) and the dwapp handler for DysonScript web applications
func RegisterDysonServer(clientCtx client.Context, logger log.Logger, rtr *mux.Router, config config.APIConfig, scriptPattern string, publicHostTemplate string, libp2pPort int, libp2pListenAddrs []string, libp2pBootstrapPeers []string) error {
	if logger == nil {
		logger = log.NewNopLogger()
	}

	// Register the DysonScript app handler
	// Use provided pattern or default if empty
	patternString := scriptPattern
	if patternString == "" {
		patternString = dwapp.DefaultDwAppPattern
	}

	// Register Swagger UI if enabled
	if config.Swagger {
		swaggerUI, err := fs.Sub(docs.SwaggerUI, "swagger-ui")
		if err != nil {
			return err
		}

		staticServer := http.FileServer(http.FS(swaggerUI))

		rtr.PathPrefix("/swagger/").Handler(http.StripPrefix("/swagger/", staticServer))
		rtr.PathPrefix("/favicon.ico").Handler(staticServer)

		protoJsonSchema, err := fs.Sub(docs.ProtoJSONSchema, "proto-json-schema")
		if err != nil {
			return err
		}
		rtr.PathPrefix("/proto-json-schema/").Handler(http.StripPrefix("/proto-json-schema/", http.FileServer(http.FS(protoJsonSchema))))

		swaggerGen, err := fs.Sub(docs.SwaggerUI, "swagger-ui/swagger-gen")
		if err != nil {
			return err
		}
		rtr.PathPrefix("/swagger-gen/").Handler(http.StripPrefix("/swagger-gen/", http.FileServer(http.FS(swaggerGen))))
	}

	if config.Enable {
		// Determine public host template: prefer provided value, fallback to default
		if publicHostTemplate == "" {
			publicHostTemplate = dwapp.DefaultConfig().PublicHostTemplate
		}

		// Determine libp2p listen addresses
		var listenAddrs []string
		if len(libp2pListenAddrs) > 0 {
			// Use custom listen addresses if provided
			listenAddrs = libp2pListenAddrs
		} else {
			// Use default addresses with configurable port
			// Generate default listen addresses
			listenAddrs = []string{
				fmt.Sprintf("/ip4/0.0.0.0/tcp/%d", libp2pPort),
				fmt.Sprintf("/ip4/0.0.0.0/tcp/%d/ws", libp2pPort),
				fmt.Sprintf("/ip4/0.0.0.0/udp/%d/quic-v1", libp2pPort),
				fmt.Sprintf("/ip4/0.0.0.0/udp/%d/quic-v1/webtransport", libp2pPort),
				fmt.Sprintf("/ip4/0.0.0.0/udp/%d/webrtc-direct", libp2pPort),
				fmt.Sprintf("/ip6/::/tcp/%d", libp2pPort),
				fmt.Sprintf("/ip6/::/tcp/%d/ws", libp2pPort),
				fmt.Sprintf("/ip6/::/udp/%d/quic-v1", libp2pPort),
				fmt.Sprintf("/ip6/::/udp/%d/quic-v1/webtransport", libp2pPort),
				fmt.Sprintf("/ip6/::/udp/%d/webrtc-direct", libp2pPort),
			}
		}

		// Start embedded P2P service once before middleware
		var p2pService *dwapp.P2PService
		if svc, err := dwapp.NewP2PService(dwapp.P2PConfig{
			HomeDir:        clientCtx.HomeDir,
			ChainID:        clientCtx.ChainID,
			ListenAddrs:    listenAddrs,
			BootstrapPeers: libp2pBootstrapPeers,
			Logger:         logger,
		}); err == nil {
			p2pService = svc
			if ctx := clientCtx.CmdContext; ctx != nil {
				go func(c context.Context) {
					<-c.Done()
					if err := svc.Close(); err != nil {
						logger.Error("failed to close libp2p service", "err", err)
					}
				}(ctx)
			}
		} else {
			logger.Error("failed to start embedded libp2p", "err", err)
		}

		// Middleware to check path condition explicitly
		rtr.Use(func(next http.Handler) http.Handler {
			dwappHandler := dwapp.NewDefaultHandler(logger, clientCtx, patternString, publicHostTemplate, libp2pBootstrapPeers)
			if h, ok := dwappHandler.(*dwapp.DefaultHandler); ok && p2pService != nil {
				h.SetP2PService(p2pService)
			}
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if !(strings.HasPrefix(r.URL.Path, "/dysonprotocol/") ||
					strings.HasPrefix(r.URL.Path, "/cosmos/") ||
					strings.HasPrefix(r.URL.Path, "/ibc/") ||
					strings.HasPrefix(r.URL.Path, "/favicon.ico") ||
					strings.HasPrefix(r.URL.Path, "/swagger/") ||
					strings.HasPrefix(r.URL.Path, "/swagger-gen/") ||
					strings.HasPrefix(r.URL.Path, "/proto-json-schema/")) {
					// Condition matched: use alternative handler
					dwappHandler.ServeHTTP(w, r)
					return
				}
				// Else, continue with default handler
				next.ServeHTTP(w, r)
			})
		})
	}

	return nil
}
