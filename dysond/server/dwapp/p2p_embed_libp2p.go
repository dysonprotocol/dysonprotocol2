package dwapp

import (
	"context"
	"fmt"
	mrand "math/rand"
	"os"
	"path/filepath"
	"strings"
	"time"

	libp2p "github.com/libp2p/go-libp2p"
	crypto "github.com/libp2p/go-libp2p/core/crypto"
	"github.com/libp2p/go-libp2p/core/event"
	libhost "github.com/libp2p/go-libp2p/core/host"
	network "github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	peerstore "github.com/libp2p/go-libp2p/core/peerstore"
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
	ctx := context.Background()
	managedPeers := 0

	for _, peerAddr := range bootstrapPeers {
		if peerAddr == "" {
			continue
		}

		if err := validateBootstrapPeer(peerAddr); err != nil {
			fmt.Printf("[DWApp] Invalid bootstrap peer '%s': %v\n", peerAddr, err)
			continue
		}

		maddr, err := multiaddr.NewMultiaddr(peerAddr)
		if err != nil {
			fmt.Printf("[DWApp] Invalid bootstrap peer address '%s': %v\n", peerAddr, err)
			continue
		}

		peerInfo, err := peer.AddrInfoFromP2pAddr(maddr)
		if err != nil {
			fmt.Printf("[DWApp] Failed to parse peer info from '%s': %v\n", peerAddr, err)
			continue
		}

		host.Peerstore().AddAddrs(peerInfo.ID, peerInfo.Addrs, peerstore.PermanentAddrTTL)

		go manageBootstrapPeer(ctx, host, *peerInfo)
		managedPeers++
	}

	fmt.Printf("[DWApp] Bootstrap peer reconnect manager active for %d peers\n", managedPeers)
}

func manageBootstrapPeer(ctx context.Context, host libhost.Host, peerInfo peer.AddrInfo) {
	const (
		minBackoff       = 5 * time.Second
		maxBackoff       = 5 * time.Minute
		dialTimeout      = 10 * time.Second
		protectTagPrefix = "bootstrap"
	)

	protectTag := fmt.Sprintf("%s:%s", protectTagPrefix, peerInfo.ID.String())

	sub, err := host.EventBus().Subscribe(new(event.EvtPeerConnectednessChanged))
	if err != nil {
		fmt.Printf("[DWApp] Failed to subscribe for bootstrap peer events %s: %v\n", peerInfo.ID.String(), err)
		return
	}
	defer sub.Close()

	rng := mrand.New(mrand.NewSource(time.Now().UnixNano()))
	backoff := minBackoff

	attemptConnect := func(reason string) {
		state := host.Network().Connectedness(peerInfo.ID)
		if state == network.Connected || state == network.Limited {
			if cm := host.ConnManager(); cm != nil {
				cm.Protect(peerInfo.ID, protectTag)
			}
			backoff = minBackoff
			return
		}

		connCtx, cancel := context.WithTimeout(ctx, dialTimeout)
		err := host.Connect(connCtx, peerInfo)
		cancel()

		if err == nil {
			fmt.Printf("[DWApp] Connected to bootstrap peer %s (%s)\n", peerInfo.ID.String(), reason)
			if cm := host.ConnManager(); cm != nil {
				cm.Protect(peerInfo.ID, protectTag)
			}
			backoff = minBackoff
			return
		}

		fmt.Printf("[DWApp] Bootstrap peer %s dial failed (%s): %v\n", peerInfo.ID.String(), reason, err)
		if backoff < maxBackoff {
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
		}
	}

	attemptConnect("initial")

	timer := time.NewTimer(backoff + jitterDuration(backoff, rng))
	defer timer.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-timer.C:
			attemptConnect("timer")
			resetTimer(timer, backoff+jitterDuration(backoff, rng))
		case evt, ok := <-sub.Out():
			if !ok {
				return
			}

			change, ok := evt.(event.EvtPeerConnectednessChanged)
			if !ok || change.Peer != peerInfo.ID {
				continue
			}

			switch change.Connectedness {
			case network.Connected, network.Limited:
				if cm := host.ConnManager(); cm != nil {
					cm.Protect(peerInfo.ID, protectTag)
				}
				backoff = minBackoff
				resetTimer(timer, backoff+jitterDuration(backoff, rng))
			case network.NotConnected, network.CanConnect, network.CannotConnect:
				fmt.Printf("[DWApp] Bootstrap peer %s changed connectedness to %s\n", peerInfo.ID.String(), change.Connectedness)
				attemptConnect("event")
				resetTimer(timer, backoff+jitterDuration(backoff, rng))
			}
		}
	}
}

func resetTimer(t *time.Timer, d time.Duration) {
	if !t.Stop() {
		select {
		case <-t.C:
		default:
		}
	}
	t.Reset(d)
}

func jitterDuration(base time.Duration, rng *mrand.Rand) time.Duration {
	if base <= 0 {
		return 0
	}
	maxJitter := base / 2
	if maxJitter < time.Second {
		maxJitter = time.Second
	}
	return time.Duration(rng.Int63n(int64(maxJitter)))
}
