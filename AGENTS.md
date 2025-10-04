## Dyson Protocol Agents Guide

This file orients coding agents to Dyson Protocol: an application-specific blockchain for on-chain Python scripts, decentralized web apps (DWapps), scheduled transactions, names-as-assets, NFTs, AMM trading, and arbitrary on-chain storage. It complements `README.md` and module notebooks, focusing on capabilities, how modules interact, and common pitfalls for automation.

### How to use this guide
- Read installation and testnet instructions in `README.md`.
- Deep dives live in `docs/*.md`. This file links to them rather than embedding code.
- Do not execute code from here; use the notebooks or `README.md` for commands.

## Repository orientation
- Build/install, run, test: see `README.md`.
- Examples: `examples/`.
- Python/Dyslang docs: `docs/scripting_guide.md`, `docs/dyslang_guide.md`.
- Storage: `docs/storage_guide.md`.
- Crontask: `docs/crontask_guide.md`.
- Nameservice: `docs/nameservice_guide.md`.
- Missing guides to create (referenced below): `docs/bank_guide.md`, `docs/staking_guide.md`, `docs/nft_guide.md`, `docs/whaleswap_guide.md`, `docs/authz_guide.md`.

## Core modules and interactions

### Bank
- Purpose: fungible token transfers and balances.
- Interactions:
  - Used by Scripts and Crontasks to send coins.
  - Nameservice can mint custom denoms (see Nameservice) which then appear in Bank balances and can be transferred/traded.
- Docs: create `docs/bank_guide.md` (overview, common Msg types, pitfalls).

### Staking
- Purpose: validator staking, delegations, rewards, slashing (standard Cosmos SDK semantics).
- Interactions:
  - Bank provides the stake denomination balances.
  - Scripts and Crontasks can submit staking messages if authorized.
- Docs: create `docs/staking_guide.md` (delegation lifecycle, reward withdrawal, authz patterns).

### Script and Dyslang
- Purpose: host and execute on-chain Python functions, and serve DWapps via WSGI.
- Docs: `docs/scripting_guide.md`, `docs/dyslang_guide.md`.
- Execution model:
  - Scripts are versioned code blobs stored against an address. You execute a named function with JSON args/kwargs.
  - DWapp requests call a WSGI entrypoint for read-only queries. DWapps cannot mutate state.
  - Script execution consumes gas with limits; failures bubble up with detailed error info.
- Sandbox constraints and syntax/workarounds:
  - No filesystem, network, or arbitrary imports beyond what Dyslang exposes.
  - Pass arguments as JSON arrays/objects; avoid shell quoting pitfalls by pre-encoding JSON.
  - Prefer small, composable functions. Let errors bubble up; do not swallow exceptions.
- Virtual `dys` module functions (partial list):
  - Messaging: `_msg`, `_query`.
  - Context: `get_script_address`, `get_executor_address`, `get_block_info`.
  - Gas/limits/metrics: `get_gas_limit`, `get_gas_consumed`, `get_nodes_called`, `get_cumulative_size`.
  - Attached messages: `get_attached_messages`, `get_attached_msg_results`.
  - Events: `emit_event`.
  - Dynamic evaluation: `dys_eval`.
- DWapp specifics:
  - WSGI endpoint reads chain state only. Use Storage queries to render dynamic content.
  - Public URL scheme resolves via Nameservice destination (see Nameservice section).

### Storage
- Purpose: arbitrary key/value storage scoped by owner address with user-defined `index` keys and JSON string `data`.
- Docs: `docs/storage_guide.md`.
- Query features:
  - `index_prefix`: iterate entries by prefix.
  - `filter`: GJSON-style predicate over entry JSON (supports ==, !=, <, <=, >, >=, pattern operators like % and !%).
  - `extract`: GJSON path to project subfields (e.g., `user.name`).
  - Pagination supports key/offset/limit; reverse iteration available.
- Parameters and limits (read current values via module params):
  - `max_storage_size`: upper bound for data payload sizes; large writes require appropriate gas.
  - `storage_stake_multiple`: per-byte stake requirement; default may be 0 on some networks, but can be set >0. Ensure sufficient stake when storing large data.
- Best practices and pitfalls:
  - Always pre-validate JSON and size before `_msg` writes.
  - Use `index_prefix` to design efficient listing patterns; avoid scanning broad prefixes.
  - For large data, prefer chunking or references; when transacting via CLI, enable automatic gas estimation.

### Nameservice
- Purpose: register names via commit–reveal, manage valuations (Harberger-style), and use names as roots for assets.
- Docs: `docs/nameservice_guide.md`.
- Names as NFTs:
  - Each name is an NFT in class `nameservice.dys` (ID is the name string).
  - Ownership transfers follow bidding rules and valuations.
- Harberger fees and valuations:
  - Owners set a valuation; they pay fees based on this valuation and are subject to bids at or above it.
  - Class parameters may define allowed valuation denoms, fee rates, and valuation periods.
- Minting denoms with names:
  - A name can mint a main denom like `example.dys` and hierarchical subdenoms like `example.dys/foo/bar`.
  - A mint fee applies; minted denoms integrate with Bank for balances and transfers.
- Minting NFTs under a name:
  - You can create NFT classes with ID equal to the name (e.g., `example.dys`) or sub-classes under it.
  - Class params control bidding/valuation rules for NFTs minted under that class.
- DWapp resolution:
  - Names can set a destination address; DWapp hostnames resolve as `<name>.<dwapp-host>` internally to that script’s WSGI handler.

### NFT
- Purpose: mint, query, transfer, and manage NFT classes and tokens.
- Interactions:
  - Nameservice mints the main name NFT (`nameservice.dys/<name>`) and can define new classes under a name root.
  - Whaleswap Auctions model escrowed assets as NFTs (see Whaleswap).
- Docs: create `docs/nft_guide.md` (class lifecycle, token mint/burn/transfer, metadata, ownership queries).

### Whaleswap
- Purpose: decentralized trading primitives.
- Concepts:
  - Auctions: NFTs representing escrowed coins for auction settlement.
  - Pools: AMM pools with optional concentrated liquidity.
  - Offers: limit-order-like intents.
  - Trade: can chain swaps and offers across pools and orders to route best execution.
- Interactions:
  - Bank provides coin balances for deposits/settlement.
  - Nameservice-minted denoms are tradable.
  - Scripts/Crontasks can automate strategies or manage auctions.
- Docs: create `docs/whaleswap_guide.md` (auction lifecycle, pool creation, offer/trade flows, safety notes).

### Crontasks
- Purpose: schedule arbitrary messages for execution at a future timestamp; support event-driven task creation.
- Docs: `docs/crontask_guide.md`.
- Capabilities:
  - Schedule messages (including Script execution) with gas limits/fees, expiry, and pagination/query support.
  - Subscriptions: on-chain event filters that create new crontasks to execute a Script function when events match.
- Interactions:
  - Common to chain Script executions (self-scheduling loops, timed auctions, payouts).
  - Combine with Storage for durable state and idempotency keys.

### Authz
- Purpose: delegated authorization to execute messages on behalf of another account.
- Interactions:
  - Scripts or Crontasks that need to send `bank` or module-specific messages on behalf of a user require appropriate grants.
  - Grants can be time/limit-scoped; design narrowly-scoped permissions.
- Docs: create `docs/authz_guide.md` (grant types, common message grants for bank/staking/script/crontask, safety patterns).

## Cross‑module recipes
- DWapp backed by Storage:
  - Use Script WSGI to render HTML, query Storage with `index_prefix`, `filter`, and `extract`. Nameservice destination makes the DWapp accessible by name.
- Self-perpetuating Script jobs:
  - A Script function posts a Crontask to call itself later with updated args for countdowns, recurring payouts, or auctions.
- Names → assets → trading:
  - Register a name, mint a denom under it, distribute tokens via Bank, then trade them in Whaleswap pools or create Auctions.
- Event-driven automation:
  - Create Crontask subscriptions that watch module events (e.g., bids placed) and invoke a Script to react (e.g., rebalance, notify, or schedule follow-up actions).

## FAQs and common pitfalls
- Argument passing:
  - Scripts accept JSON-encoded args/kwargs; ensure proper encoding and escaping.
- DWapp is read-only:
  - WSGI handlers must not attempt state changes; mutations require transactions via `_msg` in Script execution, not DWapp.
- Storage filtering/extract:
  - `Filter` and `extract` use GJSON paths; keep paths under modest length. Design indices for indexprefix filtering.
- Large storage writes and gas:
  - Big payloads consume significant gas; check `max_storage_size` and use automatic gas estimation when transacting.
- Nameservice timing and valuations:
  - Ensure valuation denom is allowed by class params; bids must meet or exceed current valuation per rules.
- Error handling:
  - Do not swallow errors in Scripts; let them bubble up for observability. Prefer explicit validation with informative exceptions.
- Testing focus:
  - Prefer targeted tests; avoid arbitrary sleeps and non-determinism. Use the project’s recommended test commands from `README.md`.

## References
- Project overview and setup: `README.md`.
- Dyslang and Script: `docs/scripting_guide.md`, `docs/dyslang_guide.md`.
- Storage: `docs/storage_guide.md`.
- Crontasks: `docs/crontask_guide.md`.
- Nameservice: `docs/nameservice_guide.md`.
- To create: `docs/bank_guide.md`, `docs/staking_guide.md`, `docs/nft_guide.md`, `docs/whaleswap_guide.md`, `docs/authz_guide.md`.

 