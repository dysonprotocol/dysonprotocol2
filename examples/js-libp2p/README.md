# Dyson JS libp2p Demo

This example shows how a browser client can connect to the Dyson REST server, fetch `/libp2p/bootstrap`, and publish
ADR-36 signed messages that pass the node's pubsub validator. It adapts the
[`universal-connectivity/js-peer`](../../universal-connectivity/js-peer) workflow to the Dyson topic model
(`/{chainId}/v1/{address_or_name}/{anything}`).

## Features

- **Browser-to-Browser Mesh Networking:** Uses libp2p WebRTC for direct peer-to-peer connections between browsers
- **Circuit Relay v2:** Creates relay reservations on Dyson nodes for WebRTC signaling
- **GossipSub Discovery:** Cross-domain peer discovery via GossipSub mesh propagation
- **PubSub Peer Discovery:** Automatic peer discovery and dialing via discovery topics
- **Multiple Transports:** WebSockets, WebTransport, WebRTC, WebRTC-direct, and circuit-relay v2
- **STUN/ICE:** NAT traversal using Google STUN servers (configurable)
- **ADR-36 Signing:** Two signing flows:
  - **CosmJS seed wallet** (mnemonic stored in-page via `DirectSecp256k1HdWallet`)
  - **Keplr** (SIGN_MODE_DIRECT, fee/gas zero, account/sequence zero)
- **Real-time Messaging:** Subscribes locally so incoming messages appear in the UI for quick testing
- **Client-side ADR-36 Validation:** The browser enforces envelope schema, `app_domain == topic`, `metadata.peerId == from`, size limits, and verifies the secp256k1 signature before persisting or dispatching.
- **Per-topic Subscription Panels:** Each subscribed topic renders its own input (send), an unsubscribe control, and an isolated gossip log for that topic.

## Prerequisites

- A Dyson REST server running with the embedded libp2p host (or another node exposing `/libp2p/bootstrap`)
- Optional: Keplr browser extension connected to the same chain ID as the REST server
- Node.js ≥ 18 (for Vite) and npm

## Getting started

```bash
cd examples/js-libp2p
npm install
npm run dev
```

Open <http://localhost:5173>. The API will be proxied so that it simulates the same-origin condition for CORS-free
access to `/libp2p/bootstrap`.

1. Click **Connect**. The app fetches bootstrap info and starts libp2p. If Keplr is available the address is shown and
the Keplr button is enabled; otherwise the Keplr button remains disabled.
2. (Optional) Enter an existing mnemonic or click **Generate Seed** to create a CosmJS wallet. The derived address is
   displayed and the CosmJS button becomes active.
3. Choose a topic suffix (appended to `/{chainId}/v1/{address}/`). The UI shows the fully-qualified topic that will be
   signed.
4. Edit the JSON payload, then click either **Sign & Publish (CosmJS)** or **Sign & Publish (Keplr)**.

Each publish wraps the payload in an ADR-36 `MsgArbitraryData` with `app_domain == topic`, signs it (either via the
mnemonic wallet or Keplr), and publishes the envelope through libp2p GossipSub. The browser validates and verifies the
envelope locally (schema, topic, metadata.peerId, size limits, signature) before storing to GossipLog; invalid frames
are dropped client-side and will not appear. Nodes also validate envelopes on the mesh.

## Inspecting Mesh & Topics

The demo now surfaces the data plane explicitly so you can debug without digging through logs:

1. **Connection** fieldset shows bootstrap JSON, relay addresses, and the most recent discovery heartbeat emitted by your
   browser.
2. **Peers** section lists the known libp2p peers, their last-seen timestamp, and the addresses learned from discovery.
3. **Subscriptions** now renders per-topic sections with: an input to send to that topic, an Unsubscribe button, and a
   scoped message list for that topic.
4. **Messages** splits global traffic into sent vs. received with signer bech32, transport peer ID, payload length, and
   a JSON preview. After publishing from each wallet, confirm a matching RX entry arrives with your signer.

## Security & Validation

The browser mirrors the server’s validator for non-discovery topics and rejects invalid frames before persistence:

- Envelope size ≤ 64 KiB; payload (decoded from base64) ≤ 48 KiB
- Requires `body`, `auth_info`, and at least one `signature`
- Exactly one message of type `/dysonprotocol.script.v1.MsgArbitraryData`
- `app_domain` must equal the subscribed topic
- `metadata` must be valid JSON with a non-empty `peerId` that matches the libp2p sender
- Signature verification: ADR‑36 DIRECT flow over secp256k1 using the included public key

Discovery topic is excluded from validation.

## Server-side validation and transport

The Dyson REST server embeds a libp2p host that:

- Validates non-discovery topics before forwarding on the mesh:
  - Ensures the ADR‑36 envelope is structurally valid (body, auth_info, signatures)
  - Checks `app_domain` equals the pubsub topic
  - Resolves the `{address_or_name}` part of the topic and verifies the recovered signer equals that address
  - Verifies `metadata.peerId` matches the libp2p sender peer ID
  - Enforces envelope and payload size limits
- Auto-joins application topics under `/{chainId}/v1/…` and forwards only validated frames
- Exposes `/libp2p/bootstrap` (peerId, relay listen addrs, chainId, topicPrefix)
- Runs Circuit Relay v2 to support WebRTC signaling for browser-to-browser connections
- Participates in the discovery topic for cross-domain peer discovery

This keeps the mesh healthy while letting browsers form direct links over WebRTC.

## Client responsibilities

Clients are expected to enforce business logic on top of signature checks. The demo SDK already mirrors the server’s validator client‑side (schema, topic, peerId, sizes, signature) and drops invalid frames before persistence, but your application should still:

- Filter by the topics and signers that your app trusts
- Authorize actions based on your own rules (recipient allowlists, capability scopes, etc.)
- Treat the discovery topic as untrusted metadata and never as an authority

## Customising

- Use different topic suffixes for multiple chat rooms.
- The SDK surface lives in `src/sdk` and is aliased as `@dyson/libp2p`; reuse `createDysonClient`,
  `createKeplrSigner`, or `createOfflineSignerSigner` in your own apps.
- `DysonClient.publishJson` automatically wraps payloads; switch to `publish` for binary data or custom encoding.
  
Validator defaults (internal): max envelope 64 KiB, max payload 48 KiB.

## Browser Mesh Architecture

This implementation enables browsers to form a decentralized mesh network:

1. **Browser connects to Dyson node** (any domain)
   - Fetches bootstrap info from `/libp2p/bootstrap`
   - Connects to server's multiaddr
   - Creates circuit relay reservation
   - Subscribes to discovery topic

2. **Discovery across domains**
   - **pubsubPeerDiscovery**: Announces presence on `/{chainId}/v1/discovery`
   - **GossipSub mesh**: Discovery messages propagate across all nodes
   - Browsers discover each other even on different servers
   - No centralized rendezvous server needed

3. **Direct WebRTC connections**
   - Initial signaling through circuit relay
   - ICE candidates exchanged via STUN servers
   - Direct P2P data channel established
   - Relay connection closed

4. **Mesh resilience**
   - Browser mesh survives server failures
   - Messages propagate via GossipSub
   - Multiple relay servers for redundancy

## Notes

- If Keplr is unavailable, its publish button stays disabled; the CosmJS flow still works with the in-page seed wallet.
- The demo verifies signatures locally; for parity checks, you can also call `/libp2p/verify` on the Dyson REST server
  with the generated envelope.
- Pubsub peer discovery announces presence every 10 seconds on `/{chainId}/v1/discovery`.
- Discovery messages propagate via GossipSub mesh - browsers on different servers discover each other through the mesh.
- Relay reservations last 1 hour and are automatically renewed.
- For production, consider adding retries for bootstrap dialing and persisting mnemonics securely (the demo keeps them in-memory only).
- Multiple Dyson nodes can run on different domains; browsers form a single unified mesh across all nodes.

