package server

import (
	"fmt"
	"io/fs"
	"net/http"
	"strings"

	"github.com/gorilla/mux"

	docs "dysonprotocol.com/client/docs"
	"dysonprotocol.com/dysond/server/dwapp"
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/server/config"
)

// RegisterDysonServer provides a common function which registers APIs with API Server
// This includes both Swagger API (if enabled) and the dwapp handler for DysonScript web applications
func RegisterDysonServer(clientCtx client.Context, rtr *mux.Router, config config.APIConfig, scriptPattern string, publicHostTemplate string, libp2pPort int, libp2pListenAddrs []string) error {

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

		// Start embedded P2P host once before middleware
		var p2pHost *dwapp.P2PHost
		if embedded, err := dwapp.StartEmbeddedP2PHost(clientCtx.HomeDir, clientCtx.ChainID, listenAddrs); err == nil && embedded != nil {
			p2pHost = embedded
		}

		// Middleware to check path condition explicitly
		rtr.Use(func(next http.Handler) http.Handler {
			dwappHandler := dwapp.NewDefaultHandler(clientCtx, patternString, publicHostTemplate)
			if h, ok := dwappHandler.(*dwapp.DefaultHandler); ok && p2pHost != nil {
				h.SetP2PHost(p2pHost)
			}
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if !(strings.HasPrefix(r.URL.Path, "/dysonprotocol/") ||
					strings.HasPrefix(r.URL.Path, "/cosmos/") ||
					strings.HasPrefix(r.URL.Path, "/ibc/") ||
					strings.HasPrefix(r.URL.Path, "/favicon.ico") ||
					strings.HasPrefix(r.URL.Path, "/swagger/") ||
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
