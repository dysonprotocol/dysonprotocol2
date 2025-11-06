 # DWapp libp2p Mesh
 
 This guide consolidates the libp2p browser mesh documentation for the Dyson DWapp server. It explains the Go host implementation, the HTTP surface area that browsers consume, and the operational knobs needed to run multi-node meshes.
 
 ## Architecture Overview
 
 - **Embedded host:** `P2PService` owns a go-libp2p host with QUIC, WebRTC, WebTransport, TCP, and WebSocket transports plus a circuit-relay v2 server.
 - **Discovery plane:** GossipSub topics propagate discovery messages across Dyson API nodes; browsers rely on `@libp2p/pubsub-peer-discovery` to publish/consume those messages.
 - **Data plane:** Browsers negotiate relay reservations, exchange SDP offers through the relay, and establish direct WebRTC data channels for application traffic.
 - **Identity & auth:** ADR-36 signed envelopes gate every non-discovery topic so only on-chain identities can publish.
 
High-level flow:

1. Browser calls `/libp2p/bootstrap` on its origin node.
2. It dials the returned multiaddrs, waits for a relay reservation, and subscribes to `/{chainID}/v1/discovery`.
3. GossipSub spreads discovery beacons across all participating nodes.
4. Browsers dial the advertised relay/WebRTC addresses and promote to direct WebRTC links.

## Message & Data Flow

| Stage | Actor | Payload | Purpose |
| --- | --- | --- | --- |
| Bootstrap | Browser ➜ `/libp2p/bootstrap` | JSON containing `peerId`, `addrs`, `relayListenAddrs`, `chainId`, `bootstrapPeers`, `ice`, `topicPrefix`, `version` | Seed the browser with the server identity, dial targets, ICE servers, and GossipSub namespace. |
| Presence heartbeat | Browser ➜ GossipSub `/{chainID}/v1/discovery` | JSON `{ peer, addrs, reason, ts }` | Advertise that a browser peer is online and which relay/WebRTC addresses others should dial. |
| Discovery gossip | Dyson nodes ↔ Dyson nodes | Same heartbeat payload | Forward heartbeats between API nodes so browsers on different domains still find each other. |
| Publish | Browser ➜ GossipSub `/{chainID}/v1/<root>[/suffix]` | ADR-36 envelope (see below) with signed payload | Deliver authenticated application data. Non-discovery topics are rejected without valid ADR-36 signatures. |
| Delivery | Dyson node ➜ Browser subscribers | Raw GossipSub message (payload = ADR-36 envelope bytes) | Browsers decode the envelope, extract signer + payload JSON, and dispatch handlers. The demo also journals every envelope into IndexedDB for replay. |

### MsgArbitraryData Envelope Anatomy

`ValidatePubSubPayload` enforces that non-discovery publishes carry a signed transaction envelope. In TypeScript that shape is:

```32:60:/Users/user/dysonprotocol2/examples/js-libp2p/src/sdk/types.ts
export interface MsgArbitraryData {
  body: {
    messages: Array<{
      '@type': string
      signer: string
      data: string
      app_domain: string
    }>
    memo: string
    timeout_height: string
  }
  auth_info: {
    signer_infos: Array<{...}>
    fee: {...}
  }
  signatures: string[]
}
```

The envelope is fully unnested with transaction fields at the top level. The browser SDK's `decodeMessage()` helper extracts:

- `signer`: bech32 address that signed the frame (authoritative identity) from `envelope.body.messages[0].signer`
- `payloadJson`: the JSON application payload with helper fields (e.g. `peerId`) stripped out for handlers
- `payloadPeerId`: the peer ID embedded in the payload (if supplied by the publisher)
- `from`: the libp2p peer that transported the frame (helps differentiate relay hops)

Versioning is handled by the topic path (`/{chainID}/v1/...`), not the envelope. When you need a second opinion, POST the envelope to `/libp2p/verify`; the server returns `{ signer, payload }`. Trust the signer for ACL decisions and treat `from` as a transport hint.

 Cross-domain propagation relies solely on GossipSub—no rendezvous service is used or required.
 
 ## Server Implementation
 
 ### Configuration surface
 
`P2PConfig` captures the tunables for the embedded host: home directory, listen addresses, bootstrap peers, envelope limits, relay resources, and logger.
 
```39:54:dysond/server/dwapp/p2p_embed_libp2p.go
 type P2PConfig struct {
 	HomeDir        string
 	ChainID        string
 	ListenAddrs    []string
 	BootstrapPeers []string
 	MaxEnvelope    int
 	RelayResources relayv2.Resources
 	Logger         log.Logger
 }
 ```
 
 `NewP2PService` normalizes the config, persists or loads an Ed25519 identity, enables the transports, installs a resource manager, starts the circuit-relay server, wires bootstrap management, and logs the resulting peer ID.
 
 ```75:133:dysond/server/dwapp/p2p_embed_libp2p.go
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
 ```
 
 The relay defaults support 256 reservations, 16 simultaneous circuits, a 4 KiB buffer, and a one-hour reservation TTL. Override `RelayResources` when the node needs different quotas.
 
 ### Bootstrap peer management
 
 `startBootstrapManager` parses operator-supplied peers and spins a reconnect loop per peer with exponential backoff and `ConnManager` protection to keep them pinned.
 
 ```174:279:dysond/server/dwapp/p2p_embed_libp2p.go
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
 ```
 
 ### GossipSub control plane
 
 `EnsurePubSub` boots GossipSub once and installs an auto-join tracer. `SubscribeTopic` registers per-topic validators, enforces a maximum of 512 active topics, and starts a ten-minute idle timer that cleans up unused topics.
 
 ```28:147:dysond/server/dwapp/p2p_control_libp2p.go
 if !strings.HasSuffix(topic, "/discovery") {
 	validator := func(ctx context.Context, p peer.ID, m *pubsub.Message) pubsub.ValidationResult {
 		if _, _, err := s.ValidatePubSubPayload(ctx, clientCtx, topic, m.Data, p.String()); err != nil {
 			telemetry.IncrCounter(1, "libp2p", "validator", "reject")
 			s.recordPeerFailure(p)
 			return pubsub.ValidationReject
 		}
 		telemetry.IncrCounter(1, "libp2p", "validator", "accept")
 		s.resetPeerFailures(p)
 		return pubsub.ValidationAccept
 	}
 	if err := ps.RegisterTopicValidator(topic, validator); err != nil {
 		...
 	}
 }
 ...
 st.timer = time.AfterFunc(topicIdleTTL, func() {
 	if s.pubsub == nil {
 		return
 	}
 	if len(s.pubsub.ListPeers(topic)) == 0 {
 		_ = s.UnsubscribeTopic(topic)
 	} else {
 		s.scheduleTopicCheck(topic)
 	}
 })
 ```
 
 Peered validators track rejection counts and blacklist abusive peers after five failed envelopes.
 
### Payload verification

`ValidatePubSubPayload` limits envelopes to 64 KiB, requires `body`, `auth_info`, and `signatures` fields, reconstructs the transaction JSON for verification, and delegates to the ADR-36 verifier. The verifier returns the signer address and payload JSON, which gives higher layers access to authenticated payloads.
 
 ```14:39:dysond/server/dwapp/p2p_validate_payload.go
 if len(payload) > s.cfg.MaxEnvelope {
 	return "", "", fmt.Errorf("envelope too large: %d bytes", len(payload))
 }
 
 var envelope struct {
 	ADR36TxJSON string `json:"adr36_tx_json"`
 	V           int    `json:"v"`
 }
 
 if err := json.Unmarshal(payload, &envelope); err != nil {
 	return "", "", fmt.Errorf("invalid payload json: %w", err)
 }
 if envelope.ADR36TxJSON == "" {
 	return "", "", fmt.Errorf("missing adr36_tx_json")
 }
 ```
 
 ## HTTP Surface
 
 `/libp2p/bootstrap` exposes host identity, dialable addresses, relay listen addresses, bootstrap peers, STUN configuration, topic prefix, and the negotiated protocol version. The handler creates `p2p-circuit` suffixed addresses so browsers can reserve relays immediately.
 
 ```104:143:dysond/server/dwapp/handler.go
 resp := map[string]any{
 	"peerId":           peerID,
 	"addrs":            addrs,
 	"relayListenAddrs": relayListenAddrs,
 	"chainId":          chainID,
 	"bootstrapPeers":   h.bootstrapPeers,
 	"ice": map[string]any{
 		"servers": []map[string]any{
 			{"urls": []string{"stun:stun.l.google.com:19302"}},
 			{"urls": []string{"stun:stun1.l.google.com:19302"}},
 		},
 	},
 	"topicPrefix": "/" + chainID + "/v1/",
 	"version":     "1",
 }
 ```
 
 `/libp2p/verify` is a utility endpoint for clients that want to preflight ADR-36 payloads before publishing them on GossipSub.
 
 Both endpoints require same-origin requests; there is no generic subscribe/unsubscribe HTTP API because GossipSub auto-join handles membership adjustments.
 
 ## Browser Expectations
 
 The TypeScript SDK under `examples/js-libp2p` demonstrates the intended client behavior:
 
 1. Fetch bootstrap JSON and construct a libp2p node with WebRTC, WebRTC Direct, WebTransport, WebSockets, and circuit-relay transports.
 2. Use `@libp2p/pubsub-peer-discovery` to broadcast discovery records on `/{chainID}/v1/discovery` every 10 seconds.
 3. Wait for a circuit-relay reservation before dialing peers; prefer `p2p-circuit/webrtc` addresses when available.
 4. Promote successful relayed connections to direct WebRTC data channels and then release the relay circuit.
 
 Discovery propagation across domains depends on Dyson nodes being mutually connected through GossipSub. If cross-domain discovery feels slow (10–20 seconds is typical), verify that operator bootstrap peer lists are correct.
 
 ## Operator Configuration
 
 Add mesh settings to `config/app.toml` (or flag equivalents):
 
 ```toml
 [dwapp]
 enable = true
 libp2p-port = 9095
 libp2p-bootstrap-peers = [
   "/dns4/node2.dyson.network/tcp/9095/p2p/12D3KooWNode2...",
   "/dns4/node3.dyson.network/tcp/9095/p2p/12D3KooWNode3..."
 ]
 ```
 
 CLI override:
 
 ```bash
 dysond start --dwapp.libp2p-bootstrap-peers="/ip4/192.168.1.101/tcp/9095/p2p/12D3KooWNodeB...,/ip4/192.168.1.102/tcp/9095/p2p/12D3KooWNodeC..."
 ```
 
 Multiaddrs may use IPv4, IPv6, DNS, WebSocket, QUIC, or WebTransport schemes; ensure peer IDs are appended.
 
 ## Discovery Topics & Limits
 
 - Topic namespace: `/{chainID}/v1/*`; `discovery` suffix stays unvalidated, all other topics require ADR-36 envelopes.
 - Topic cap: 512 concurrent topics; idle topics are pruned after 10 minutes without mesh peers.
- Envelope cap: 64 KiB.
 - Peer blacklist: five rejected payloads triggers a temporary blacklist.
 
 GossipSub metrics are emitted via Cosmos SDK telemetry counters (`libp2p.validator.{accept,reject}` and `libp2p.topics.active`).
 
 ## Performance Notes
 
 Observations from manual testing:
 
 - Same-node discovery: < 1 second.
 - Cross-domain discovery: ~10–20 seconds depending on mesh fanout.
 - WebRTC session setup: 2–5 seconds after discovery.
 - Default relay budget: 256 concurrent reservations, 16 simultaneous relay circuits, one-hour TTL.
 
 Monitor reservation usage and adjust `RelayResources` if nodes routinely near cap.
 
 ## Testing Playbook
 
 1. Launch one or more Dyson nodes (`make install` then `dysond start ...`).
 2. In `examples/js-libp2p`, run `npm install` then `npm run dev`.
 3. Open the demo in two tabs (or two domains with different `VITE_DYSONPROTOCOL_API` values).
 4. Confirm discovery, relay reservation creation, and direct WebRTC messaging.
 
 Testing should rely on application observations and Cosmos telemetry; no sleeps or rendezvous mocks are needed because the mesh auto-heals.
 
 ## Simplification Opportunities
 
 - If deployments never need WebTransport or WebRTC Direct, consider removing those transports to shrink dependency surface and cut AST nodes in the JS client.
 - Operationally, prefer a small, well-curated bootstrap list rather than many peers—fewer entries accelerate reconnect loops and reduce log noise.
 

