package dwapp

import (
	"context"
	"errors"
	"fmt"
	mrand "math/rand"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"cosmossdk.io/log"
	libp2p "github.com/libp2p/go-libp2p"
	pubsub "github.com/libp2p/go-libp2p-pubsub"
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

const (
	defaultMaxEnvelopeBytes = 64 * 1024
	defaultMaxPayloadBytes  = 48 * 1024
	defaultReservationTTL   = time.Hour
)

// P2PConfig collects the knobs required to build an embedded libp2p host.
type P2PConfig struct {
	HomeDir        string
	ChainID        string
	ListenAddrs    []string
	BootstrapPeers []string
	MaxEnvelope    int
	MaxPayload     int
	RelayResources relayv2.Resources
	Logger         log.Logger
}

// P2PInfo exposes the pieces of host identity needed by HTTP handlers.
type P2PInfo struct {
	PeerID string
	Addrs  []string
}

// P2PService owns the embedded libp2p host and related GossipSub state.
type P2PService struct {
	cfg           P2PConfig
	host          libhost.Host
	ctx           context.Context
	cancel        context.CancelFunc
	pubsub        *pubsub.PubSub
	topicsMu      sync.Mutex
	topics        map[string]*topicState
	peerRejects   map[peer.ID]int
	peerRejectsMu sync.Mutex
	pubsubMu      sync.Mutex
	pubsubErr     error
	logger        log.Logger
}

// NewP2PService constructs a libp2p host, enables the relay server, and starts
// bootstrap management. Call Close to release background resources.
func NewP2PService(cfg P2PConfig) (*P2PService, error) {
	normalized, err := normalizeConfig(cfg)
	if err != nil {
		return nil, err
	}

	idPath := filepath.Join(normalized.HomeDir, "p2p", "identity.key")
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
		libp2p.ListenAddrStrings(normalized.ListenAddrs...),
		libp2p.Transport(webtransport.New),
		libp2p.Transport(quic.NewTransport),
		libp2p.Transport(tcp.NewTCPTransport),
		libp2p.Transport(webrtc.New),
		libp2p.ShareTCPListener(),
		libp2p.Transport(ws.New),
		libp2p.UserAgent("dysond/libp2p"),
	}

	if rm, err := newResourceManager(); err == nil {
		opts = append(opts, libp2p.ResourceManager(rm))
	}

	h, err := libp2p.New(opts...)
	if err != nil {
		return nil, fmt.Errorf("create libp2p host: %w", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	service := &P2PService{
		cfg:         normalized,
		host:        h,
		ctx:         ctx,
		cancel:      cancel,
		topics:      make(map[string]*topicState),
		peerRejects: make(map[peer.ID]int),
		logger:      normalized.Logger.With("component", "dwapp_p2p"),
	}

	if err := service.enableRelay(); err != nil {
		cancel()
		return nil, err
	}

	h.Network().Notify(&networkNotifiee{logger: service.logger})
	service.startBootstrapManager()

	service.logger.Info("libp2p host started", "peer_id", h.ID().String())
	return service, nil
}

// Close stops background routines and closes the underlying host.
func (s *P2PService) Close() error {
	if s == nil {
		return nil
	}
	s.cancel()
	return s.host.Close()
}

// HostInfo exposes the current peer ID and formatted addresses.
func (s *P2PService) HostInfo() *P2PInfo {
	if s == nil || s.host == nil {
		return nil
	}
	return &P2PInfo{PeerID: s.host.ID().String(), Addrs: formatAddrs(s.host)}
}

func (s *P2PService) enableRelay() error {
	resources := s.cfg.RelayResources
	if resources.MaxReservations == 0 {
		resources = relayv2.DefaultResources()
		resources.MaxReservations = 256
		resources.MaxCircuits = 16
		resources.BufferSize = 4096
		resources.ReservationTTL = defaultReservationTTL
	}

	if _, err := relayv2.New(s.host, relayv2.WithResources(resources)); err != nil {
		return fmt.Errorf("create relay: %w", err)
	}

	s.logger.Info("circuit relay enabled",
		"reservations", resources.MaxReservations,
		"circuits", resources.MaxCircuits,
		"chain_id", s.cfg.ChainID,
	)
	return nil
}

func (s *P2PService) startBootstrapManager() {
	peers := s.cfg.BootstrapPeers
	if len(peers) == 0 {
		s.logger.Info("no bootstrap peers configured")
		return
	}

	s.logger.Info("connecting to bootstrap peers", "count", len(peers))
	go func() {
		managed := 0
		for _, addr := range peers {
			info, err := parseBootstrapPeer(addr)
			if err != nil {
				s.logger.Error("invalid bootstrap peer", "addr", addr, "err", err)
				continue
			}
			s.host.Peerstore().AddAddrs(info.ID, info.Addrs, peerstore.PermanentAddrTTL)
			go s.manageBootstrapPeer(*info)
			managed++
		}
		s.logger.Info("bootstrap peer reconnect manager active", "count", managed)
	}()
}

func (s *P2PService) manageBootstrapPeer(peerInfo peer.AddrInfo) {
	const (
		minBackoff       = 10 * time.Second
		maxBackoff       = 30 * time.Second
		dialTimeout      = 10 * time.Second
		protectTagPrefix = "bootstrap"
	)

	protectTag := fmt.Sprintf("%s:%s", protectTagPrefix, peerInfo.ID.String())
	sub, err := s.host.EventBus().Subscribe(new(event.EvtPeerConnectednessChanged))
	if err != nil {
		s.logger.Error("bootstrap event subscribe failed", "peer", peerInfo.ID.String(), "err", err)
		return
	}
	defer sub.Close()

	rng := mrand.New(mrand.NewSource(time.Now().UnixNano()))
	backoff := minBackoff

	attempt := func(reason string) {
		state := s.host.Network().Connectedness(peerInfo.ID)
		if state == network.Connected || state == network.Limited {
			if cm := s.host.ConnManager(); cm != nil {
				cm.Protect(peerInfo.ID, protectTag)
			}
			backoff = minBackoff
			return
		}

		ctx, cancel := context.WithTimeout(s.ctx, dialTimeout)
		err := s.host.Connect(ctx, peerInfo)
		cancel()
		if err == nil {
			s.logger.Info("connected to bootstrap peer", "peer", peerInfo.ID.String(), "reason", reason)
			if cm := s.host.ConnManager(); cm != nil {
				cm.Protect(peerInfo.ID, protectTag)
			}
			backoff = minBackoff
			return
		}

		s.logger.Error("bootstrap dial failed", "peer", peerInfo.ID.String(), "reason", reason, "err", err)
		if backoff < maxBackoff {
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
		}
	}

	attempt("initial")
	timer := time.NewTimer(backoff + jitterDuration(backoff, rng))
	defer timer.Stop()

	for {
		select {
		case <-s.ctx.Done():
			return
		case <-timer.C:
			attempt("timer")
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
				if cm := s.host.ConnManager(); cm != nil {
					cm.Protect(peerInfo.ID, protectTag)
				}
				backoff = minBackoff
				resetTimer(timer, backoff+jitterDuration(backoff, rng))
			case network.NotConnected, network.CanConnect, network.CannotConnect:
				s.logger.Info("bootstrap peer connectedness changed", "peer", peerInfo.ID.String(), "state", change.Connectedness.String())
				attempt("event")
				resetTimer(timer, backoff+jitterDuration(backoff, rng))
			}
		}
	}
}

func normalizeConfig(cfg P2PConfig) (P2PConfig, error) {
	result := cfg
	result.ChainID = strings.TrimSpace(cfg.ChainID)
	result.HomeDir = strings.TrimSpace(cfg.HomeDir)
	if result.HomeDir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return P2PConfig{}, fmt.Errorf("determine home dir: %w", err)
		}
		result.HomeDir = filepath.Join(home, ".dysond")
	}
	if len(result.ListenAddrs) == 0 {
		return P2PConfig{}, errors.New("listen addrs required")
	}
	if result.MaxEnvelope == 0 {
		result.MaxEnvelope = defaultMaxEnvelopeBytes
	}
	if result.MaxPayload == 0 {
		result.MaxPayload = defaultMaxPayloadBytes
	}
	if result.Logger == nil {
		result.Logger = log.NewNopLogger()
	}
	return result, nil
}

func parseBootstrapPeer(addr string) (*peer.AddrInfo, error) {
	if strings.TrimSpace(addr) == "" {
		return nil, fmt.Errorf("empty peer address")
	}
	maddr, err := multiaddr.NewMultiaddr(addr)
	if err != nil {
		return nil, fmt.Errorf("invalid multiaddr format: %w", err)
	}
	info, err := peer.AddrInfoFromP2pAddr(maddr)
	if err != nil {
		return nil, fmt.Errorf("invalid peer info: %w", err)
	}
	return info, nil
}

type networkNotifiee struct {
	logger log.Logger
}

func (n *networkNotifiee) Listen(network.Network, multiaddr.Multiaddr)      {}
func (n *networkNotifiee) ListenClose(network.Network, multiaddr.Multiaddr) {}
func (n *networkNotifiee) Connected(net network.Network, conn network.Conn) {
	if n.logger == nil {
		return
	}
	n.logger.Debug("network connected",
		"peer", conn.RemotePeer().String(),
		"local", conn.LocalMultiaddr().String(),
		"remote", conn.RemoteMultiaddr().String(),
	)
}
func (n *networkNotifiee) Disconnected(net network.Network, conn network.Conn) {
	if n.logger == nil {
		return
	}
	n.logger.Debug("network disconnected", "peer", conn.RemotePeer().String())
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
	id := h.ID().String()
	addrs := make([]string, 0, len(h.Addrs()))
	for _, a := range h.Addrs() {
		addrs = append(addrs, fmt.Sprintf("%s/p2p/%s", a.String(), id))
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
		Memory:          1 << 30,
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
