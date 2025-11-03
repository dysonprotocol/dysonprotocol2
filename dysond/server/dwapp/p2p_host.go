package dwapp

// P2PHost is a minimal abstraction for a future libp2p host.
// It allows the HTTP layer to return peerId and addrs without importing libp2p.
type P2PHost struct {
	peerID string
	addrs  []string
}

func NewP2PHost(peerID string, addrs []string) *P2PHost {
	return &P2PHost{peerID: peerID, addrs: addrs}
}

func (h *P2PHost) PeerID() string  { return h.peerID }
func (h *P2PHost) Addrs() []string { return h.addrs }
