# TEWL UI

Minimal frontend for the TEWL (Tool for External World Lookups) protocol.

## Setup

```bash
npm install
```

## Configuration

Copy `.env.example` to `.env` and set:

- `DYSONPROTOCOL_API` - Dyson node REST endpoint (default: `http://localhost:1317`)
- `VITE_TEWL_SCRIPT` - Deployed TEWL script address

## Development

```bash
npm run dev
```

Opens at http://localhost:5179

Vite proxies all `/cosmos`, `/dysonprotocol`, `/ibc`, `/rpc` paths to the configured API.

## Build

```bash
npm run build
```

Output in `dist/`. In production, deploy to same host as API (no proxy needed).

## Stack

- Vue 3 + TypeScript
- Tailwind CSS (shadcn-style tokens)
- Pinia for state
- CosmJS for wallet/signing
- Vite

## Views

- **Dashboard** - Protocol stats, request list
- **Provider** - Bond management, commit/reveal
- **Create Request** - New request form
- **Request Detail** - Status, result, scores, finalize
