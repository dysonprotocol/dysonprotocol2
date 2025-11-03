# Dyson JS libp2p Demo

This example shows how a browser client can connect to the Dyson REST server, fetch `/libp2p/bootstrap`, and publish
ADR-36 signed messages that pass the node's pubsub validator. It adapts the
[`universal-connectivity/js-peer`](../../universal-connectivity/js-peer) workflow to the Dyson topic model
(`/{chainId}/v1/{address_or_name}/{anything}`).

## Features

- Uses `libp2p@2` with WebSockets, WebTransport, WebRTC, and circuit-relay v2 transports (browser friendly)
- Auto-dials the bootstrap multiaddrs returned by `/libp2p/bootstrap` and uses a pubsub discovery topic to find peers (`/{chainId}/v1/discovery`)
- Publishes `{ "adr36_tx_json": "…", "v": 1 }` envelopes to the chosen topic
- Two signing flows:
  - **CosmJS seed wallet** (mnemonic stored in-page via `DirectSecp256k1HdWallet`)
  - **Keplr** (SIGN_MODE_DIRECT, fee/gas zero, account/sequence zero)
- Subscribes locally so incoming messages appear in the UI for quick testing

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

Open <http://localhost:5173>. The page must be served from the same origin as the Dyson REST endpoint for CORS-free
access to `/libp2p/bootstrap`.

1. Click **Connect**. The app fetches bootstrap info and starts libp2p. If Keplr is available the address is shown and
the Keplr button is enabled; otherwise the Keplr button remains disabled.
2. (Optional) Enter an existing mnemonic or click **Generate Seed** to create a CosmJS wallet. The derived address is
   displayed and the CosmJS button becomes active.
3. Choose a topic suffix (appended to `/{chainId}/v1/{address}/`).
4. Edit the JSON payload, then click either **Sign & Publish (CosmJS)** or **Sign & Publish (Keplr)**.

Each publish wraps the payload in an ADR-36 `MsgArbitraryData` with `app_domain == topic`, signs it (either via the
mnemonic wallet or Keplr), and publishes the envelope through libp2p GossipSub. Incoming frames are logged in the
**Received messages** panel. Messages failing ADR-36 validation are dropped by the node and will not appear.

## Customising

- Use different topic suffixes for multiple chat rooms.
- The SDK surface lives in `src/sdk` and is aliased as `@dyson/libp2p`; reuse `createDysonClient`,
  `createKeplrSigner`, or `createOfflineSignerSigner` in your own apps.
- `DysonClient.publishJson` automatically wraps payloads; switch to `publish` for binary data or custom encoding.

## Notes

- If Keplr is unavailable, its publish button stays disabled; the CosmJS flow still works with the in-page seed wallet.
- To verify signatures without publishing, call `/libp2p/verify` on the Dyson REST server with the generated envelope.
- Pubsub peer discovery is enabled by default; the client listens on `/{chainId}/v1/discovery` and dials peers announced by the node or other browsers. For custom logic, consume the `peer:discovery` event emitted by the SDK.
- For production, consider adding retries for bootstrap dialing and persisting mnemonics securely (the demo keeps them in-memory only).

