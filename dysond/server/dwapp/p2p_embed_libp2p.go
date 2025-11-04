package dwapp

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	libp2p "github.com/libp2p/go-libp2p"
	crypto "github.com/libp2p/go-libp2p/core/crypto"
	libhost "github.com/libp2p/go-libp2p/core/host"
	network "github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	rcmgr "github.com/libp2p/go-libp2p/p2p/host/resource-manager"
	relayv2 "github.com/libp2p/go-libp2p/p2p/protocol/circuitv2/relay"
	quic "github.com/libp2p/go-libp2p/p2p/transport/quic"
	tcp "github.com/libp2p/go-libp2p/p2p/transport/tcp"
	webrtc "github.com/libp2p/go-libp2p/p2p/transport/webrtc"
	ws "github.com/libp2p/go-libp2p/p2p/transport/websocket"
	webtransport "github.com/libp2p/go-libp2p/p2p/transport/webtransport"
	multiaddr "github.com/multiformats/go-multiaddr"
)

var (
	embeddedHost libhost.Host
)

// StartEmbeddedP2PHost initialises the libp2p host using the provided homeDir, chainID, listen addresses, and bootstrap peers.
// If homeDir is empty it defaults to ~/.dysond. The host identity is persisted
// in <homeDir>/p2p/identity.key. Enables circuit relay v2 for browser mesh networking and connects to bootstrap peers.
func StartEmbeddedP2PHost(homeDir, chainID string, listenAddrs []string, bootstrapPeers []string) (*P2PHost, error) {
	if embeddedHost != nil {
		return NewP2PHost(embeddedHost.ID().String(), formatAddrs(embeddedHost)), nil
	}

	baseDir := strings.TrimSpace(homeDir)
	if baseDir == "" {
		userHome, err := os.UserHomeDir()
		if err != nil {
			return nil, fmt.Errorf("determine home dir: %w", err)
		}
		baseDir = filepath.Join(userHome, ".dysond")
	}

	idPath := filepath.Join(baseDir, "p2p", "identity.key")
	if err := os.MkdirAll(filepath.Dir(idPath), 0o700); err != nil {
		return nil, fmt.Errorf("create identity dir: %w", err)
	}
	priv, err := loadOrCreateIdentity(idPath)
	if err != nil {
		return nil, fmt.Errorf("load identity: %w", err)
	}

	opts := []libp2p.Option{
		libp2p.Identity(priv),
		libp2p.NATPortMap(),
		libp2p.ListenAddrStrings(listenAddrs...),
		libp2p.Transport(webtransport.New),
		libp2p.Transport(quic.NewTransport),
		libp2p.Transport(tcp.NewTCPTransport),
		libp2p.Transport(webrtc.New),
		libp2p.ShareTCPListener(),
	}

	rm, err := newResourceManager()
	if err == nil {
		opts = append(opts, libp2p.ResourceManager(rm))
	}

	opts = append(opts,
		libp2p.Transport(ws.New),
		libp2p.UserAgent("dysond/libp2p"),
	)

	h, err := libp2p.New(opts...)
	if err != nil {
		return nil, fmt.Errorf("create libp2p host: %w", err)
	}
	embeddedHost = h

	// Enable circuit relay v2 server for browser-to-browser WebRTC signaling
	resources := relayv2.DefaultResources()
	resources.MaxReservations = 256      // Support 256 browser relay reservations
	resources.MaxCircuits = 16           // Max 16 concurrent relayed connections
	resources.BufferSize = 4096          // 4KB buffer for signaling
	resources.ReservationTTL = time.Hour // Reservations last 1 hour

	_, err = relayv2.New(h, relayv2.WithResources(resources))
	if err != nil {
		return nil, fmt.Errorf("create relay: %w", err)
	}
	fmt.Printf("[DWApp] Circuit relay v2 server enabled (reservations=%d, circuits=%d)\n",
		resources.MaxReservations, resources.MaxCircuits)
	fmt.Printf("[DWApp] Browser mesh discovery via pubsubPeerDiscovery + circuit relay (chainID=%s)\n", chainID)

	// Connect to bootstrap peers for peer mesh
	if len(bootstrapPeers) > 0 {
		fmt.Printf("[DWApp] Connecting to %d bootstrap peers...\n", len(bootstrapPeers))
		go connectToBootstrapPeers(h, bootstrapPeers)
	} else {
		fmt.Printf("[DWApp] No bootstrap peers configured\n")
	}

	// Log peer connections
	h.Network().Notify(&networkNotifiee{})

	fmt.Printf("[DWApp] libp2p host started: peerId=%s\n", h.ID().String())
	return NewP2PHost(h.ID().String(), formatAddrs(h)), nil
}

type networkNotifiee struct{}

func (n *networkNotifiee) Listen(network.Network, multiaddr.Multiaddr)      {}
func (n *networkNotifiee) ListenClose(network.Network, multiaddr.Multiaddr) {}
func (n *networkNotifiee) Connected(net network.Network, conn network.Conn) {
	fmt.Printf("[DWApp] network Connected: peer=%s local=%s remote=%s\n",
		conn.RemotePeer().String(), conn.LocalMultiaddr().String(), conn.RemoteMultiaddr().String())
}
func (n *networkNotifiee) Disconnected(net network.Network, conn network.Conn) {
	fmt.Printf("[DWApp] network Disconnected: peer=%s\n", conn.RemotePeer().String())
}

func loadOrCreateIdentity(path string) (crypto.PrivKey, error) {
	if b, err := os.ReadFile(path); err == nil {
		return crypto.UnmarshalPrivateKey(b)
	}
	priv, _, err := crypto.GenerateKeyPair(crypto.Ed25519, 0)
	if err != nil {
		return nil, err
	}
	b, err := crypto.MarshalPrivateKey(priv)
	if err != nil {
		return nil, err
	}
	if err := os.WriteFile(path, b, 0o400); err != nil {
		return nil, err
	}
	return priv, nil
}

func formatAddrs(h libhost.Host) []string {
	pid := h.ID().String()
	addrs := make([]string, 0, len(h.Addrs()))
	for _, a := range h.Addrs() {
		addrs = append(addrs, fmt.Sprintf("%s/p2p/%s", a.String(), pid))
	}
	return addrs
}

func newResourceManager() (network.ResourceManager, error) {
	base := rcmgr.BaseLimit{
		Streams:         4096,
		StreamsInbound:  2048,
		StreamsOutbound: 2048,
		Conns:           1024,
		ConnsInbound:    512,
		ConnsOutbound:   512,
		FD:              2048,
		Memory:          1 << 30, // 1GiB budget per process
	}

	scaling := rcmgr.ScalingLimitConfig{
		SystemBaseLimit:       base,
		TransientBaseLimit:    base,
		ServiceBaseLimit:      base,
		ServicePeerBaseLimit:  base,
		ProtocolBaseLimit:     base,
		ProtocolPeerBaseLimit: base,
		PeerBaseLimit:         base,
		ConnBaseLimit:         base,
		StreamBaseLimit:       base,
	}

	limits := scaling.Scale(0, 0)
	return rcmgr.NewResourceManager(rcmgr.NewFixedLimiter(limits))
}

// GetEmbeddedHost returns the embedded libp2p host
func GetEmbeddedHost() libhost.Host {
	return embeddedHost
}

// validateBootstrapPeer validates a bootstrap peer multiaddr
func validateBootstrapPeer(peerAddr string) error {
	if peerAddr == "" {
		return fmt.Errorf("empty peer address")
	}

	// Parse the multiaddr
	maddr, err := multiaddr.NewMultiaddr(peerAddr)
	if err != nil {
		return fmt.Errorf("invalid multiaddr format: %w", err)
	}

	// Extract peer ID and addresses
	_, err = peer.AddrInfoFromP2pAddr(maddr)
	if err != nil {
		return fmt.Errorf("invalid peer info: %w", err)
	}

	return nil
}

// connectToBootstrapPeers connects to the configured bootstrap peers with retry logic
func connectToBootstrapPeers(host libhost.Host, bootstrapPeers []string) {
	const (
		maxRetries       = 5
		baseRetryDelay   = 2 * time.Second
		maxRetryDelay    = 30 * time.Second
		connectionTimeout = 10 * time.Second
	)

	ctx := context.Background()
	validPeers := 0

	for _, peerAddr := range bootstrapPeers {
		if peerAddr == "" {
			continue
		}

		// Validate the peer address
		if err := validateBootstrapPeer(peerAddr); err != nil {
			fmt.Printf("[DWApp] Invalid bootstrap peer '%s': %v\n", peerAddr, err)
			continue
		}
		validPeers++

		go func(addr string) {
			var lastErr error
			for attempt := 0; attempt < maxRetries; attempt++ {
				// Parse the multiaddr
				maddr, err := multiaddr.NewMultiaddr(addr)
				if err != nil {
					fmt.Printf("[DWApp] Invalid bootstrap peer address '%s': %v\n", addr, err)
					return
				}

				// Extract peer ID and addresses
				peerInfo, err := peer.AddrInfoFromP2pAddr(maddr)
				if err != nil {
					fmt.Printf("[DWApp] Failed to parse peer info from '%s': %v\n", addr, err)
					return
				}

				// Check if already connected
				if host.Network().Connectedness(peerInfo.ID) == network.Connected {
					fmt.Printf("[DWApp] Already connected to bootstrap peer %s\n", peerInfo.ID.String())
					return
				}

				// Attempt connection with timeout
				connCtx, cancel := context.WithTimeout(ctx, connectionTimeout)
				err = host.Connect(connCtx, *peerInfo)
				cancel()

				if err == nil {
					fmt.Printf("[DWApp] Successfully connected to bootstrap peer %s\n", peerInfo.ID.String())
					return
				}

				lastErr = err
				fmt.Printf("[DWApp] Failed to connect to bootstrap peer %s (attempt %d/%d): %v\n",
					peerInfo.ID.String(), attempt+1, maxRetries, err)

				// Exponential backoff
				if attempt < maxRetries-1 {
					delay := time.Duration(attempt+1) * baseRetryDelay
					if delay > maxRetryDelay {
						delay = maxRetryDelay
					}
					fmt.Printf("[DWApp] Retrying connection to %s in %v...\n", peerInfo.ID.String(), delay)
					time.Sleep(delay)
				}
			}

			fmt.Printf("[DWApp] Failed to connect to bootstrap peer after %d attempts: %v\n", maxRetries, lastErr)
		}(peerAddr)
	}

	fmt.Printf("[DWApp] Bootstrap peer connection initiated for %d valid peers\n", validPeers)
}
