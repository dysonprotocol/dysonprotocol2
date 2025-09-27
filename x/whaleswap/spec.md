## Whaleswap module (x/whaleswap) – Specification

### 1. Scope and goals

- Port Whaleswap from dyslang scripts (`whaleswap/amm.py`, `orderbook.py`, `auction.py`) to a native Cosmos SDK module.
- Preserve semantics and event shapes where practical; simplify where possible for safety and maintainability.
- Integrate with existing modules: `nameservice`, `nft`, `bank`, `params`.

Non-goals (initial cut): on-chain scripting hooks, cross-chain.

### Migration delta (scripts → module)

- No attachments: module handlers move funds via bank keeper. Script-style attached MsgSend is not used.
- Mint fee semantics: nameservice skips fees when destination is the module account; module mints to itself then forwards. Direct user mints (if any) still owe fees.
- Liquid denom format: `whaleswap.dys/coins/<solid>` (no base64). Shares: `whaleswap.dys/pools/{pool_id}`.
- Single-pool swaps only. Multi-hop is achieved by multiple messages in one tx.
- Per-leg XOR rule: each SwapLeg must specify exactly one of swap_in or swap_out (not both). Use message-level max_input (vector caps) and min_output (vector guarantees) to assert end-of-tx constraints across legs.
- Authority: module account must control `whaleswap.dys` root for mint/burn/class ops.
- Orderbook settlement uses TAKE_ALL-only with a single aggregated multi-send via an internal whaleswap helper (`wsMoveCoins`); liquid inputs collected at the module are burned post-settlement.


### 2. External dependencies and authorities

- Bank keeper: move funds between user accounts and the module account.
- Nameservice keeper: mint/burn custom denoms, set NFT class policies, set metadata.
- NFT keeper: mint/send/burn NFTs.
- Params keeper: module params.
- Module account: `whaleswap` (escrow, fee accrual, mint/burn authority via nameservice).
- Authority over `whaleswap.dys` root: the module account must be the destination/owner so it can mint/burn/move custom denoms and set class policies.


### 3. Denoms and notation

- Solid denom S: a base on-ledger denom like `DYS_ROOT/foo`.
- Liquid denom L(S): wrapper minted by Whaleswap for S, defined as `whaleswap.dys/coins/<S>` (no encoding).
- Shares denom for pools: `whaleswap.dys/pools/{pool_id}`.
- Price convention (AMM): P = reserve2 / reserve1 ("price of coin2 in coin1 units").


### 4. Module parameters

- pfand_per_offer: sdk.Coin. Locked when creating a liquid offer; released on close/cancel per rules.
- auction knobs (strings matching nameservice types/validation):
  - valuation_fee_pct (Dec in [0,1])
  - valuation_period (duration string)
  - bid_timeout (duration string)
  - min_bid_percent_increase (Dec in [0,1])

Notes:
- Nameservice `mint_fee_per_coin` remains the source of truth for mint fees; however, when minting to a module account, the nameservice skips fee collection. Whaleswap mints shares and liquid wrappers to the `whaleswap` module account and then forwards them to users, so no mint fee is charged along this path. Direct mints to non-module destinations still require the fee.


### 5. State model (keys and indexes)

- Counters (uint64):
  - `counter|pools`, `counter|offers`, `counter|trades`, `counter|auctions`.

- AMM Pools: `pools/{id}` → Pool
  - id (uint64)
  - coin1_denom, coin2_denom (string; coin1 < coin2 lexicographically)
  - reserve1, reserve2 (sdk.Int)
  - total_shares (sdk.Int)
  - shares_denom (string)
  - fee_pct (math.Dec, 0 ≤ fee < 1)
  - min_price, max_price (math.Dec; inclusive bounds on P = R2/R1)
  - block_height (int64), created (time), updated (time), num_trades (uint64)

- Orderbook Offers: `oid|{id}` → OfferData
  - Maker, status {open|closed|cancelled}, have/want coins, remaining, unit ints, remaining_units, pfand_locked
  - Indexes:
    - `maker|{maker}|status|{status}|id|{id}` → `oid|{id}`
    - Price trees (lexicographic):
      - `w|{want}|h|{have}|{price_key}|oid|{id}`
      - `h|{have}|w|{want}|{price_key}|oid|{id}`

- Trades: `tid|{id}` → Trade; indexes:
  - `taker_trade|{taker}|tid|{id}` → `tid|{id}`
  - `offer_trade|oid|{offer_id}|tid|{id}` → `tid|{id}`

- Auctions:
  - Primary: `AuctionsMap[id]` → AuctionRecord {class_id, nft_id, sell (coin), bid_denom, seller}
  - Reverse indexes (collections-based):
    - `(sell_denom, bid_denom, auction_id)` → `auction_id`
    - `(bid_denom, sell_denom, auction_id)` → `auction_id`
  - NFT class: `whaleswap.dys/auction/{bid_denom}` (one class per bid denom)


### 6. AMM – owner-only LP with price band and fee

Design updates (required):
- Mode A (no price range): classic constant product (Uniswap v2) with fee
  - If the owner does not specify a price range, the pool operates with invariant x·y = k.
  - Liquidity is diffuse across all prices; fee is applied to input.
- Mode B (price range set): concentrated liquidity (Uniswap v3-style) with a single band per pool
  - The owner specifies an inclusive price band [min_price, max_price] over P = R2/R1.
  - Within the band the pool uses concentrated liquidity math; outside the band swaps halt and liquidity sits fully in one asset.
- Each pool has a fee percentage `fee_pct` applied to swaps (0 ≤ fee < 1).
- Owner definition: the pool "owner" at any time is the address that holds strictly more than 50% of the outstanding pool shares.
  - Enforcement: before any owner-privileged action (Add/Remove liquidity, UpdatePoolConfig), the module computes majority-of-shares for the pool's `shares_denom` by iterating balances (or using a cached value with verification) and requires the signer to be the current majority holder.
  - The module may cache `owner_majority_cached` on mints/burns/known transfers but must re-validate during privileged ops to avoid stale state.
- Anyone can swap as long as the resulting price stays within the configured range.
- The pool owner can change pool config (fee_pct, min_price, max_price) at any time.
- No one can join someone else's pool (owner-only liquidity). Others may hold/receive shares via transfers, but only the current majority holder may add/remove liquidity.

Pool creation
- Msg: CreatePool(coinA, coinB, min_price, max_price, fee_pct)
  - Caller becomes owner.
  - Canonicalize: coin1_denom < coin2_denom; reorder amounts accordingly.
  - Move both coin amounts caller → module; initialize reserves.
  - total_shares = initial_shares minted to owner; shares denom `whaleswap.dys/pools/{pool_id}`.
    - v2 (no band): initial_shares = floor(sqrt(R1*R2)).
    - v3 (band set): initial_shares = floor(L) from liquidity within [sa,sb].
  - Validate 0 ≤ fee_pct < 1 and 0 ≤ min_price ≤ max_price; initial P within [min,max].

Owner adds/removes liquidity (only owner)

Owner is defined as the address that holds strictly more than 50% of the outstanding pool shares. Only owner can add liquidity. Anyone can remove liquidity as long as the resulting price stays within the configured range.

Mode A (v2, no price range)
- Msg: AddLiquidity(pool_id, amount1, amount2)
  - Proportional join to current reserves.
  - Refund any excess to owner.
  - Mint shares: shares = min(floor(added1 * total_shares / R1), floor(added2 * total_shares / R2)).
  - Update reserves, total_shares.
  

- Msg: RemoveLiquidity(pool_id, shares)
  - Proportional exit: out1 = floor(shares * R1 / total_shares), out2 analogously.
  - Burn shares; send outs; update reserves.
  - Full exit special-case: if shares == total_shares, pay out entire reserves (R1,R2), burn all shares, and delete the pool. Skip post-op price/band checks.
  - Partial exits must leave both reserves > 0; otherwise reject with an error instructing to use full exit.

Mode B (v3-style, price range set)
- Notation: P = R2/R1, s = sqrt(P). Let sa = sqrt(min_price), sb = sqrt(max_price), sp = sqrt(current_price). Liquidity L is constant within [sa, sb].
- Given a desired add (amount1 for denom1, amount2 for denom2), the effective L added is:
  - If sp ≤ sa (below range): amount1 contributes, amount2 ignored → L = amount1 * (sa * sb) / (sb - sa)
  - If sp ≥ sb (above range): amount2 contributes, amount1 ignored → L = amount2 / (sb - sa)
  - If sa < sp < sb (within range):
    - L0 = amount1 * (sp * sb) / (sb - sp)
    - L1 = amount2 / (sp - sa)
    - L = min(L0, L1), refund any excess component to owner.
- Reserves implied by (L, sp) inside the band evolve with swaps; we store R1/R2 directly and ensure they remain consistent with L.
- Removing liquidity by ΔL returns amounts using:
  - If sp within [sa, sb]:
    - out1 = floor(ΔL * (sb - sp) / (sp * sb))
    - out2 = floor(ΔL * (sp - sa))
  - If sp ≤ sa: out1 = floor(ΔL * (sb - sa) / (sa * sb)), out2 = 0
  - If sp ≥ sb: out1 = 0, out2 = floor(ΔL * (sb - sa))
- In all cases, enforce post-condition price remains within [min,max].

Swaps (any user)
- Msg: PoolSwap(pool_id, input_coin, minimum_out_amount, out_denom)
  - Single-pool swap only. To route across multiple pools, include multiple PoolSwap messages in the same transaction or call the module multiple times from a script.
  - Apply math based on pool mode:
    - Mode A (v2): constant product with fee on input.
      - k = R1*R2; effective_in = dx * (1 - fee_pct).
      - out = R2 - ceil(k / (R1 + effective_in)) (or symmetric for coin2 input).
      - Update reserves; enforce price band if configured.
    - Mode B (v3-style): concentrated liquidity within [sa, sb].
      - Use sqrt-price integration with constant liquidity L.
      - For token1→token2 swap (input denom1, output denom2), price moves up: with fee on input, let dxe = dx*(1-fee_pct).
        - Move from sp to sp' within [sa, sb] such that dxe = L * (1/sp - 1/sp').
        - out = floor(L * (sp' - sp)). If input exhausts before hitting band edge, stop at boundary.
      - For token2→token1, symmetric with price moving down: dye = dy*(1-fee_pct), dxe = floor(L * (1/sp' - 1/sp)).
      - Reject if resulting price exits band.
  - Require out_denom match and amount ≥ minimum_out_amount; send to caller.
  - Per-leg XOR rule: SwapLegs accept exact-in (swap_in) or exact-out (swap_out), but not both together; combine with message-level max_input/min_output for symmetric guarantees.

Pool configuration updates (only owner)
- Msg: UpdatePoolConfig(pool_id, fee_pct?, min_price?, max_price?)
  - Optional fields; validate 0 ≤ fee_pct < 1 and 0 ≤ min_price ≤ max_price.
  - Ensure current mid-price remains within new band.

Ownership
- Ownership is implicit from share distribution. There is no explicit SetPoolOwner message.
- Ownership may change when share transfers or liquidity mint/burn cause a different address to cross the 50% threshold. 

Events
- pool_created, poolupdate, pool_liquidity_added, pool_liquidity_removed, pool_swap.

Invariants
- total_shares supply (bank) equals stored total_shares.
- Reserves non-negative; price band respected after each state change.
- Shares_denom unique per pool.
- Majority owner checks: privileged ops must verify signer holds >50% of `shares_denom` at execution time.

Notes
- Mode selection is implicit: if min_price/max_price are unset (or represent [0, +∞)), behavior is Mode A; otherwise Mode B.


### 7. Liquid conversions (wrapping)

Msgs
- ConvertToLiquid(denom, amount)
  - Move `amount` of solid denom caller → module (escrow backing).
  - Mint L(denom) to the module account (fee skipped due to module destination) and forward to caller.

- ConvertToSolid(liquid_denom, amount)
  - Move liquid from caller → module; burn; send solid to caller; require module escrow ≥ amount.

Notes
- Due to module authority and nameservice behavior, mint fees are skipped for module-destination mints and thus are not required for ConvertToLiquid. Backing is always enforced and must equal or exceed burned liquid on ConvertToSolid.


### 8. Orderbook DEX

Msgs
- MakeOffer(have, want)
  - Normal: have is solid; escrow have in module (bank send user→module). No pfand.
  - Liquid: have is liquid L(S); require maker holds ≥ pfand_per_offer; move pfand maker→module; no have attachments.

- TakeOffer(trades[])
  - Atomic TAKE_ALL-only settlement. Any infeasible leg aborts the entire batch.
  - Planning: iterate legs, compute `take_units`, aggregate maker wants (solid), taker credits (solid base-have; liquid-have decoded to base), and include pfand to taker on close. Emit `offer_taken` and `pfand_released` during planning; events roll back on failure.
  - Netting: reduce the taker’s output for each solid denom by min(credits, maker wants) before computing the taker’s deficit. Fund deficits from taker base first, then taker liquid L(denom) (to be burned).
  - Aggregation: build bank inputs/outputs across all participants. The whaleswap module contributes solid backing and receives liquid inflows to burn.
  - Settlement: call internal `wsMoveCoins` once to pull all inputs into the module and fan out outputs; then burn all liquid denoms now held by the module. Persist trades, update offers, and remove reverse indexes on close.
  - Constraints: want must be solid; liquid wants are rejected at MakeOffer.

- CancelOffer(offer_id)
  - Maker can cancel open; third-party may cancel liquid offers if maker lacks ≥ 1 unit of L(have); pfand sent to closer.

Indexes and queries
- Offers primary: `OffersMap[id]` → OfferData
- Reverse indexes:
  - `(have_denom, id)` → `id`
  - `(want_denom, id)` → `id`
  - Normalized pair+price (single direction only): `(low|high, price_dec, id)` → `id`, where `low = min(have, want)`, `high = max(have, want)`, and `price_dec = amount(high) / amount(low)` as a cosmos.Dec string; this yields stable lexical ordering and avoids duplicate entries.
- Trades primary/indexes: by `offer_id`, by `taker`


### 9. Auctions

Msgs
- OpenAuction(sell, bid_denom)
  - Move explicit solid `sell` coin from seller → module (escrow).
  - Create/upsert NFT class `whaleswap.dys/auction/{bid_denom}`.
  - Set class policy from whaleswap params: always_listed=true; valuation_fee_pct; valuation_period; bid_timeout; minimum_bid_percent_increase. All setter errors are propagated (tx fails if any policy update fails).
  - Set allowed_denoms to only `bid_denom` (error if setter fails).
  - Mint NFT with id equal to the allocated `auction_id` (zero-padded) to seller.
  - Store `AuctionRecord` keyed by `auction_id`.
  - Populate reverse indexes:
    - (sell_denom, bid_denom, auction_id) → auction_id
    - (bid_denom, sell_denom, auction_id) → auction_id

- RedeemAuction(auction_id)
  - Authority: current NFT owner only (not necessarily original seller). Owner is fetched at execution time from NFT keeper.
  - Guard: only if no current bidder (checked via nameservice NFT data `current_bidder == ""`).
  - Escrow check: pre-validate module has ≥ the escrowed `sell` coin; otherwise fail with ErrInsufficientFunds.
  - Settlement: send escrowed `sell` to owner; burn the NFT.
  - Indexing: remove reverse index entries first, then delete the primary `AuctionRecord`; any index removal error aborts the tx.


### 10. Advanced composed execution (atomic multi-op match-and-settle)

This section was removed. The module will not implement composed execution in the MVP.


### 11. Queries (gRPC + CLI)

- Pools: Get(pool_id), List(pagination). Return reserves, fee_pct, band, owner, timestamps, num_trades.
- Offers: Get(id), ByOwner(owner,status), Offers(have_denom?, want_denom?) with pagination.
  - ByOwner requires `owner`; when `status` provided, the `(owner,status,id)` index is used; otherwise a filtered scan is used.
  - Offers list prefers reverse indexes when filters are provided:
    - both have and want: use normalized `(low|high, price, id)` index and verify exact direction
    - only have: use `(have, id)` index and optionally filter `want`
    - only want: use `(want, id)` index and optionally filter `have`
    - neither: full scan of primary map
- Trades: ByOffer(offer_id), ByTaker(addr).
- Auctions: Get(id), List with optional filters (sell_denom?, bid_denom?) and pagination.
  - If both filters: use (sell,bid,auction_id) index.
  - If only sell_denom: use (sell,*,auction_id) index.
  - If only bid_denom: use (bid,*,auction_id) index.
  - If neither: paginate primary map.
- Params: Get.


### 12. Genesis

- Contents: params, counters, pools, offers, trades, auctions.
- Validate: denoms format, params ranges, unique shares denom per pool, no duplicate indexes, counters ≥ max id in state.
- Additional check: sum of `AuctionRecord.sell` per denom must be ≤ the module account's on-chain balance for that denom; otherwise genesis is invalid.
- Export/import symmetric.


### 13. Errors and validation (high level)

- Denoms must be valid; coin amounts must be > 0 (except zero in specific system fields).
- AMM swap: reject output ≤ 0, reserve depletion, price band violations.
- Add/remove liquidity: owner-only; must keep price within band; shares > 0.
- Orderbook: forbid liquid attachments at make; want must be solid; all computed amounts integral.
- Liquid conversions: enforce fee sufficiency; escrow backing checks.
- Auctions: enforce valid denoms (`sdk.ValidateDenom`); reject liquid `sell`/`bid` denoms; propagate errors from all class policy setters; owner-based redeem; explicit escrow insufficiency errors; reverse indexes must be removed on redeem.


### 14. Math and rounding policy

- Prefer sdk.Int storage for amounts; use math.Dec for fee_pct and price bounds.
- AMM swap: `out = R_out - ceil(k / (R_in + effective_in))` with `effective_in = in * (1 - fee_pct)`.
- Shares mint/burn: floor for proportional calculations; reject if both outs floor to 0.


### 15. Events (selected)

- pool_created(pool_id), poolupdate(pool_id), pool_swap(pool_id), pool_liquidity_added(pool_id), pool_liquidity_removed(pool_id), pool_owner_changed(pool_id)
- offer_created(offer_id), offer_taken(offer_id, trade_id), offer_cancelled(offer_id), pfand_locked(amount), pfand_released(amount)
  - Note: orderbook take emits events during planning; Cosmos SDK rolls them back if the tx fails.
- auction_created(auction_id), auction_redeemed(auction_id)


### 16. Testing plan (outline)

- Unit tests: AMM math (ceil/floor, price band enforcement, fee application), orderbook settlement paths, auctions, conversions.
- E2E tests (pytest):
  - Liquid convert in/out with mint fees.
  - AMM owner-only add/remove; swap inside band; reject outside band; fee accrual observed.
  - Orderbook: normal vs liquid offers; take (base+liquid mix); cancel eligibility; pfand release paths.
  - Auctions open/redeem with class policy setup.


### 17. Migration notes from scripts

- No "attachments"; module explicitly moves funds via bank keeper.
- Preserve major event names for minimal test diffs.
- Price band and fee are new vs. script AMM; tests must reflect updated constraints.

Module authority differences vs scripts (important):
- Fee semantics: scripts required attached `udys` to pay nameservice mint fees. The module mints to its own account and then forwards coins, so nameservice skips fees in these paths. Direct user-facing mints (if any) would still require fees.
- Liquid denom format: the module uses a direct prefix `whaleswap.dys/coins/<solid>` instead of base64url encoding.
- Shares minting: initial and incremental share mints occur to the module account first (no fee), then are sent to LPs.


### 18. Future extensions (non-blocking)

- Concentrated liquidity per tick ranges; multi-fee tiers.
- Pool pause/guardians; TWAP oracles.
- Batch auctions integrated with AMM inventory.


# TODO
### What’s left per spec (prioritized)

- AMM (files: `x/whaleswap/keeper/msg_liquidity.go`, `msg_pool_swap.go`, `keeper.go`, `spec.md`)
  - Enforce price band post-AddLiquidity and post-RemoveLiquidity. (done)
  - Concentrated-liquidity math (sqrt-price, L-based) when a price range is set; current implementation is v2 with band checks only.
  - Emit consistent poolupdate events on all reserve mutations (we already do most).
  - Keep integer-first math; ensure single ctx/time read per handler (mostly done).

- Orderbook DEX (files: `x/whaleswap/keeper/msg_orderbook.go`, `query_offers.go`, `query_trades.go`, `keeper.go`)
  - Emit missing events: pfand_locked on MakeOffer (liquid), pfand_released on close/cancel, offer_cancelled. (done)
  - Implement queries with pagination:
    - OffersByOwner(owner,status?) (done)
    - OffersByHave(have_denom) (done)
    - OffersByWant(want_denom) (done)
    - TradesByOffer(offer_id) (done)
    - TradesByTaker(taker) (done)
  - Indexing: add secondary indexes (owner+status, have/want) via `collections` for performance; optionally start with filtered scan for MVP.

- Liquid conversions (files: `x/whaleswap/keeper/msg_convert.go`, `keeper.go`)
  - Fee semantics updated: module mints to module account (fee skipped) then forwards. Documented above. (done)

- Auctions (files: `x/whaleswap/keeper/msg_auction.go`, `query_auctions.go`, `keeper.go`)
  - Implement MsgOpenAuction (escrow exactly one solid denom; set class/policy via nameservice; mint NFT to seller; record).
  - Implement MsgRedeemAuction (only NFT owner; only if no current bidder; burn NFT; release escrow).
  - Queries: Auction(id), AuctionByPair(sell,bid).
  - Events: auction_created, auction_redeemed.
  - Keeper state: add `AuctionSeq`, `AuctionsMap` (and pair index) via `collections`.

- Queries split/localization (files: `x/whaleswap/keeper/query_*.go`)
  - Move all query handlers into per-query files (we split Pools; finish Offers/Trades/Auctions).

- Genesis (files: `x/whaleswap/genesis.go`, `x/whaleswap/keeper/genesis.go`)
  - Export/import params, counters (pool/offer/trade/auction seq), pools, offers, trades, auctions.
  - Validate denoms, unique shares, counters ≥ max ids.
  - Add invariants where applicable.

- Params and defaults (files: `x/whaleswap/types/params.go`, `spec.md`)
  - Ensure sane defaults for `pfand_per_offer` (denom `whaleswap.dys/pfand`, amount 0), auction knobs.
  - Validation already present; ensure doc parity.

- CLI/REST (files: `x/whaleswap/module/module.go`, `client/` commands)
  - Tx and query commands for all msgs/queries (AMM, orderbook, auctions, conversions, params).

- Authority and safety (files: `app_config.go`, `genesis`, docs)
  - Ensure module controls `whaleswap.dys` root at genesis for mint/burn/class ops.
  - Invariants: share supply == bank supply; escrow/pfand correctness.

- Tests/docs (files: `tests/whaleswap/*`, `x/whaleswap/spec.md`, README)
  - Port and adapt existing whaleswap tests to module txs/queries.
  - Add e2e for AMM range checks, orderbook liquid paths, auctions, conversions.
  - Update `spec.md` with final behaviors and parameter notes.

I'll add orderbook events, implement offers/trades queries with basic pagination, enforce price-band checks in AddLiquidity/RemoveLiquidity, and remove the unimplemented stub methods so each query is defined once. Then I'll run lints on the touched files.


- Added orderbook events:
  - Emit EventPfandLocked on MakeOffer (liquid).
  - Emit EventOfferCancelled and EventPfandReleased on CancelOffer; kept existing EventOfferCreated/Taken.

- Enforced price band on LP ops:
  - AddLiquidity and RemoveLiquidity now reject if resulting price leaves [min,max].

- Implemented queries with pagination scans:
  - OffersByOwner(owner,status), OffersByHave(have_denom), OffersByWant(want_denom).
  - TradesByOffer(offer_id), TradesByTaker(taker).
  - Split into query_offers.go, query_trades.go; kept Auction queries stubbed in query_auctions.go.

- Cleaned duplicates:
  - Removed overlapping methods from query_server.go; it now only has Offer and interface binding.

Next: implement auctions (Open/Redeem + queries) and start ComposeOperations.
==================================================
I’ll implement Auctions next: keeper collections for auctions, MsgOpenAuction/MsgRedeemAuction, and queries; then add ComposeOperations scaffolding.
Also, I’ll keep queries split into query_offers.go/query_trades.go and leave auction queries in query_auctions.go until we wire storage.
==================================================
Implemented: Offers/Trades queries now return paginate results; pfand release event on offer close; auction sequence scaffold added to keeper.
Next steps: implement MsgOpenAuction/MsgRedeemAuction + Auction queries; scaffold ComposeOperations.
Spec updated behavior is already met for:
Orderbook events (offer_created/taken/cancelled, pfand_locked/released).
AMM band enforcement on add/remove.
==================================================
Added concentrated-liquidity helpers in keeper.go:
sqrt price, band sqrt, current sqrt price
liquidityForReserves to compute L within [sa,sb]
Implemented v3 math paths:
AddLiquidity: when band set, compute ΔL contribution from dx/dy using sqrt-price formulas; refund excess; approximate shares mint via proportional fallback; enforce band after update (kept existing check).
PoolSwap: when band set, approximate sqrt-price integration to derive out amount using L, sp, [sa,sb]; clamp to band; update reserves; fee applied to input.
==================================================
Here’s what remains to implement to meet the spec.

### AMM (pools)
- Implement concentrated remove-liquidity math
  - Use the L-based formulas for out1/out2 when bands are set (sa/sb/sp), not proportional share exits. Files: `x/whaleswap/keeper/msg_liquidity.go`.
- Map ΔL to shares minted/burned
  - Shares should be derived from ΔL (not proportional fallback); define consistent policy and apply in add/remove. Files: `msg_liquidity.go`.
- Refine concentrated swap integration and edge handling
  - Clamp precisely at band edges, preserve L consistency, and ensure fee treatment matches spec across hops. Files: `msg_pool_swap.go`.
- Emit EventPoolUpdate uniformly on every reserve mutation
  - Ensure one event per mutation path (add/remove/swap). Files: `keeper.go`, `msg_*`.
- Standardize errors
  - Replace remaining fmt.Errorf with `sdkerrors.Wrap/Wrapf`. Files: `msg_liquidity.go`, `msg_pool_swap.go`, others.

### ComposeOperations
- Implement `MsgComposeOperations`
  - Three-phase execution: collect inputs → apply ops internally (TakeOffer/PoolSwap with module escrow bookkeeping) → single final settlement. All-or-nothing. Files: `x/whaleswap/keeper/msg_compose.go` (new), reuse math from existing handlers, keep state updates atomic.

### Genesis
- Full InitGenesis/ExportGenesis
  - Persist/export params, counters (pool/offer/trade/auction seq), pools, offers, trades, auctions.
  - On InitGenesis, set counters ≥ max ID and rebuild reverse indexes:
    - Offers: `(have,id)`, `(want,id)`, `(low|high,price,id)`, `(owner,status,id)`
    - Auctions: `(sell,bid,id)`, `(bid,sell,id)`
  - Files: `x/whaleswap/genesis.go`, `x/whaleswap/keeper/genesis.go`.

### Orderbook DEX
- Mostly done: Make/Take/Cancel, pfand paths, reverse indexes, queries. Add any missing sdkerrors wrapping and ensure index cleanup on all terminal state transitions (already present but double-check). Files: `msg_orderbook.go`, `query_offers.go`, `query_trades.go`.

### Auctions
- Done: Open/Redeem, class policy, bidder check, reverse indexes, queries. Ensure sdkerrors consistency and event emissions. Files: `msg_auction.go`, `query_auctions.go`.

### Wrapping (liquid conversions)
- Align proto with behavior
  - Remove `mint_fee` from `MsgConvertToLiquid` proto (currently still present in `proto/dysonprotocol/whaleswap/v1/tx.proto`) to match keeper logic that mints to module with zero fee and forwards. Regenerate protos, adjust client docs.

### Invariants and authority
- Add invariants (optional but recommended)
  - Shares bank supply == stored; escrow/pfand accounting consistent; auction escrow matches records.
- Ensure `whaleswap.dys` root authority at genesis
  - Module account must control it for mint/burn/class ops.

### CLI/REST and docs/tests
- CLI/REST
  - tx and query commands mirroring msgs/queries (like other modules). Files: `x/whaleswap/module/module.go` and client cmd scaffolding.
- Tests
  - Port `tests/whaleswap/*` to module txs/queries; add e2e for AMM bands, orderbook liquid paths, auctions, conversions. Use `make test PYTEST_ARGS=" ... "` as usual.
- Docs
  - Update `x/whaleswap/spec.md` and README with finalized behaviors and parameters.

- I marked the helper work as complete; I’ll keep the concentrated AMM task open while we wire ΔL-based shares and v3 remove math.
==================================================
I'll implement concentrated AMM improvements now: add ΔL↔shares helpers, use ΔL-based shares in AddLiquidity, implement concentrated RemoveLiquidity outputs, and refactor PoolSwap to choose v2 vs v3 paths exclusively. Then I'll run lints.

[1 tool called]

I’m going to implement the concentrated AMM fully:
- Add ΔL-based shares mint/burn in Add/Remove.
- Implement v3 remove math using sqrt-price formulas.
- Refactor PoolSwap to choose v2 vs v3 path exclusively and emit uniform pool update events.
- Then lint the modified files.

[10 tools called]

- Implemented concentrated AMM fully on core paths:
  - AddLiquidity: computes ΔL from dx/dy per band; mints shares via Δshares = floor(ΔL * totalShares / Lcur); refunds excess; persists via updatePool; emits liquidity event.
  - RemoveLiquidity: concentrated exits use ΔL from shares and return amounts using sqrt-price formulas; v2 path unchanged.
  - PoolSwap: clean separation of v3 vs v2; v3 uses sqrt-price integration with clamped band movement; reserves updated directly on pool; uniform updatePool + EventPoolSwap.

- Lints clean on edited files.
==================================================
Replaced remaining fmt.Errorf with sdkerrors.Wrap/Wrapf:
Updated msg_liquidity.go and msg_pool_swap.go to use cosmossdkerrors + sdkerrors.
Added missing imports in msg_pool_swap.go.
All edited files lint clean.
==================================================
[1 tool called]

I'll update the code and spec now: remove the ComposeOperations RPC/messages from tx.proto, delete the keeper stub, and strip the composed-execution section from spec.md. Then I'll fix imports and lints.

[7 tools called]

I'll restore a temporary ComposeOperations stub to satisfy the current generated interface, regenerate protos to remove ComposeOperations, then delete the stub and re-run lints.

[2 tools called]

- Removed ComposeOperations:
  - Deleted RPC and all related messages from `proto/dysonprotocol/whaleswap/v1/tx.proto`.
  - Updated `x/whaleswap/spec.md`: removed composed-execution section, added note it’s not in MVP.
  - Kept a temporary stub in `x/whaleswap/keeper/msg_server.go` to satisfy the current generated interface until you run proto generation. After you run make proto-gen install, we can delete the stub.

- Next step: run proto-gen to drop ComposeOperations from the generated Go interfaces, then I’ll remove the temporary stub.
==================================================
I'll remove the ComposeOperations stub and clean the codec registrations to eliminate any references to removed types. Then I'll run lints.

[4 tools called]

- Removed all ComposeOperations references:
  - Deleted from `proto/dysonprotocol/whaleswap/v1/tx.proto`.
  - Dropped from `x/whaleswap/codec.go` registrations.
  - Removed method from `x/whaleswap/keeper/msg_server.go`.
  - Updated `x/whaleswap/spec.md` to note the feature is not in MVP.

- Build error fixed.
==================================================
- Mint fee field removed from proto; code regenerated and binary builds clean.
- Wrapping flow now matches keeper: mint to module with zero fee, then forward.
==================================================
[6 tools called]

- AMM polish done:
  - RemoveLiquidity now uses updatePool and emits poolupdate.
  - PoolSwap adds post-swap band check (v3); error wrapping standardized.
  - Insufficient shares now uses sdkerrors with details.

- Errors unified across keeper msgs:
  - Updated orderbook, auctions, convert, liquidity, swap to use sdkerrors/cosmossdkerrors with Wrap/Wrapf.

- Next major items remaining:
  - Implement full genesis (InitGenesis/ExportGenesis) to persist params, sequences, pools/offers/trades/auctions, and rebuild reverse indexes.
  - Add invariants (shares supply, escrow/pfand, auction escrow).
  - CLI/REST commands and tests.
  - Spec tidy: mark AMM items complete; remove leftover ComposeOperations TODOs.
==================================================
[6 tools called]

- Implemented keeper genesis:
  - InitGenesis: sets params; loads pools/offers/trades/auctions; sets sequences to max IDs; rebuilds reverse indexes (`OffersByHave/Want/OwnerStatus/PairPrice`, `AuctionsBySellBid/BidSell`).
  - ExportGenesis: exports params plus all pools/offers/trades/auctions.

- Fixed imports and Dec usage; lints clean for `keeper/genesis.go`.

- Remaining: invariants, CLI/REST, and tests; and spec tidying to reflect completed AMM and genesis.
==================================================
I'll review the whaleswap query message field names to ensure correct positional args and potential flags when expanding help text and examples. Then I'll reformat x/whaleswap/module/autocli.go with multiline keyed fields and add Short, Long, and Example for each command.

[4 tools called]

I'll expand the whaleswap AutoCLI options to be multiline and add Short, Long, and Example for every query and tx command. Then I'll lint the file.

[5 tools called]

- Reformatted x/whaleswap/module/autocli.go with multiline keyed fields and added Short, Long, and Example for every whaleswap query and tx RPC:
  - Query: Params, Pool, Pools, Offer, OffersByOwner, Offers, TradesByOffer, TradesByTaker, Auction, Auctions.
  - Tx: CreatePool, UpdatePoolConfig, AddLiquidity, RemoveLiquidity, PoolSwap, ConvertToLiquid, ConvertToSolid, MakeOffer, TakeOffer, CancelOffer, OpenAuction, RedeemAuction, UpdateParams.
  - Added positional arg descriptors where applicable.
  - Lints clean.

- You can now run:
  - dysond query whaleswap --help
  - dysond tx whaleswap --help
  - And each subcommand shows verbose descriptions and examples.

- No changes to options.pulsar.go were needed; we used its fields (Short, Long, Example) correctly.

- If you want even more detailed flag help (aliases, defaults), I can add FlagOptions per field next.
==================================================
I'll update the AMM section in x/whaleswap/spec.md to define PoolSwap as single-pool only, removing multi-hop language and clarifying how to chain swaps. Then I'll adjust x/whaleswap/test_spec.md to remove multi-hop references and update examples to use a single pool_id.

[4 tools called]

- Updated `x/whaleswap/spec.md` to make PoolSwap single-pool only, removed multi-hop routing text, clarified chaining via multiple msgs or script calls, and adjusted math section wording.
- Updated `x/whaleswap/test_spec.md` to reflect single-pool swaps and corrected CLI examples to use `--pool-id` instead of route IDs.

Let me know if you want me to also adjust the tx.proto and keeper to enforce single-pool inputs at the type level (and simplify AutoCLI help accordingly).

==================================================
I'll scan the tx.proto to confirm the current MsgPoolSwap fields and update them to single pool_id. Then I'll modify keeper/msg_pool_swap.go to accept a single pool_id and remove route logic, and adjust the AutoCLI command help accordingly.

[6 tools called]

I’m going to regenerate protobufs and rebuild since we changed tx.proto to make PoolSwap single-pool. Then I’ll fix any compile errors.

[5 tools called]

- Changed proto: `MsgPoolSwap` now single-pool with `uint64 pool_id` (removed `route_ids`). Updated `proto/dysonprotocol/whaleswap/v1/tx.proto`.
- Updated keeper: `msg_pool_swap.go` enforces `pool_id` and removed route parsing/multi-hop loop. Logic executes exactly one pool swap, then enforces min-out and sends output.
- Updated CLI help in `x/whaleswap/module/autocli.go` to use `--pool-id` and clarified multi-pool chaining via multiple messages.

You should run: make proto-gen install to regenerate types and rebuild.

==================================================
Here are the main edge cases and undefined/underspecified behaviors to firm up:

- AMM (v2/v3)
  - Price band edge equalities: sa == sb, min == max, or sp exactly at a boundary → several formulas divide by (sb−sp), (sp−sa), or (sb−sa). Define allowed zero-width bands or reject; guard all divisions.
  - Zero reserves after remove: p = R2/R1 divides by zero if R1→0. Decide whether zero reserve is allowed; if not, prevent exits that zero-out R1 (or define behavior).
  - Fee semantics: Fees are applied to input (effective_in). Clarify fee destination (accrue to pool reserves vs separate fee bucket). Right now they implicitly accrue to LPs via reserves.
  - Multi-hop with mixed modes: Define exact rounding/order for v2→v3→v2 hops. Ensure consistent truncation and failure if any hop yields out=0 while minimum_out unmet.
  - Majority-owner changes: Shares transfers can flip ownership between Add/Remove. Confirm we only check majority on Add/UpdateConfig (current code) and never on Remove (as spec states anyone can remove).
  - Shares↔ΔL mapping: For v3, Δshares = floor(ΔL * totalShares / Lcur). Define behavior when Lcur=0 (brand-new band or fully out-of-range).
  - Refund rules: In v3 AddLiquidity we refund the opposite side to match ΔL; specify overflow/precision policy and ensure consistent eventing when refunds are zero.

- Math/rounding
  - Canonical Dec string formatting in indexes (price strings): trailing zeros/precision can alter lexicographic order. Define fixed precision or canonical string representation.
  - Truncation floors: Many outputs are floor(). Specify that zero outputs cause rejection (current behavior), and ensure consistent error types.
  - LCM/GCD units for orderbook: Extremely large amounts can produce huge LCMs. Consider caps or earlier normalization to avoid pathological gas/overflow.

- Orderbook
  - Want must be solid: Ensure MakeOffer rejects liquid want; confirm error and event semantics.
  - Mixed settlement source for taker (base then liquid) with batch: Overpayment/refund semantics are not spelled out. Define exact payment priority and refund behavior if batched takes overshoot.
  - Liquid-have close/cancel by third-party: Eligibility check is “maker lacks ≥1 unit liquid have”. Define exact check (balance at execution height) and race with concurrent transfers.
  - Reverse index consistency: On partial takes (still open), indexes remain; on close/cancel, all related indexes must be removed. Ensure behavior under repeated close/cancel attempts (idempotent).
  - Price-tree direction: Unified pair index uses normalized low|high + price. Define how Offers query validates requested direction, especially when both have and want are provided.

- Auctions
  - Redeem authority: Spec says “NFT owner can redeem”; code currently restricts to original seller. Decide final rule; if owner-based, use current owner (and update code).
  - Active bidder check: We use nameservice NFT data current_bidder. Define what counts as “no bidder” (strict empty string) and behavior if metadata missing/unset.
  - NFT class reuse per bid_denom: If policy/allowed denoms change later, clarify effects on existing auctions; define idempotence of SaveClass/policy setters.
  - Reverse index deletion: Ensure idempotence and behavior if redeem is called twice or after out-of-band burn.

- Conversions (wrapping)
  - Backing underflow: ConvertToSolid aborts if backing < amount. Define whether partial redemption is allowed (currently no). Confirm no fee charged on module-destination mints and that direct user mints still require fee.
  - Liquid denom format: whaleswap.dys/coins/<solid>. Disallow nested wrapping and clarify errors if given already-liquid denom to ConvertToLiquid.

- Params/authority
  - UpdateParams authority: Clarify who is the authority (gov module address) and error code if mismatched. Document that pfand_per_offer denom/amount zero is valid (disables pfand).

- Queries/pagination
  - Stable ordering: Define order for offers/trades/auctions when using reverse indexes and when scanning primary maps (id ASC by default unless page_reverse).
  - OffersByOwner requires owner: we now error if missing; reflect in API docs. Behavior for unknown status value should error (not silent).

- Genesis/migrations
  - Band and fee defaults in existing pools on import; sequences ≥ max id. Confirm that reverse indexes rebuilt only for open offers and that price index precision matches runtime.

- Events
  - Event completeness: Ensure we emit consistent poolupdate on any reserve mutation. Spec mentions pool_owner_changed (doc still lists it) but events.proto omits it; reconcile doc vs code.

- Errors and types
  - Ensure all user-facing rejects use sdkerrors with consistent codes (ErrInvalidRequest, ErrUnauthorized, ErrInsufficientFunds, ErrNotFound). Replace remaining fmt.Errorf.

- Operational
  - Module account authority over whaleswap.dys root must exist at genesis. Without it, mints/burns/class ops will fail at runtime.
  - Gas scaling: Large orderbook batches, big LCMs, or large AMM hops can exceed default gas; CLI defaults help but document expectations.

If you want, I can open issues in-spec and add guardrails in code for the high-risk items: zero-width bands, zero reserve division, auction redeem authority, and canonical price string precision.
==================================================
- AMM (v2/v3)
  - Price band edge equalities
    - Decision: reject zero-width bands (min==max or sa==sb). Validation: in CreatePool/UpdatePoolConfig require min_price != max_price and (sb−sa) > 0; return ErrInvalidRequest.
    - Boundary math: if sp==sa use token2-only branch; if sp==sb use token1-only branch; never divide by (sp−sa) or (sb−sp) when zero. Guard denominators in AddLiquidity/RemoveLiquidity/PoolSwap and switch branches explicitly.
  - Zero reserves after remove
    - Decision: disallow exits that zero-out either reserve (would make P undefined or violate band). After compute, if new R1<=0 or R2<=0 → ErrInvalidRequest “would deplete reserve”.
    - Rationale: we store P=R2/R1 and enforce band; zero reserve breaks price checks.
  - Fee semantics
    - Decision: fee applied on input (effective_in = in*(1−fee_pct)), fees accrue to LPs via reserves; no separate fee bucket in MVP. Document in spec/events.
  - Multi-hop (removed)
    - Decision: single-pool swaps only. Routing = multiple PoolSwap msgs in one tx or multiple script calls. Spec/autocli/proto already aligned.
  - Majority-owner changes
    - Decision: check majority only on AddLiquidity and UpdatePoolConfig; RemoveLiquidity remains permissionless (current code). Note in spec.
  - Shares ↔ ΔL mapping (v3)
    - Decision: Δshares = floor(ΔL * totalShares / Lcur). If Lcur ≤ 0 (should not happen with valid band/reserves) → ErrInvalidRequest “invalid pool liquidity”. Zero minted shares → reject.
  - Refund rules (v3 Add)
    - Decision: compute ΔL, refund opposite side to exact match; emit refunds only if >0; safe Int arithmetics throughout. Keep current behavior.

- Math/rounding
  - Canonical Dec formatting for price indexes
    - Problem: Dec.String() is not order-stable lexicographically; can break price-tree ordering.
    - Decision: define a fixed-scale canonical price string, e.g., 18 decimals, no exponent, left-pad integer, right-pad fraction: FormatDec18(d) → “000000000000000123.450000000000000000”.
    - Implementation: add helper in keeper (or types util), use it in OffersByPairPrice keying (genesis rebuild, MakeOffer index builds). Keep existing pairKey low|high.
  - Truncation floors
    - Decision: zero outputs are errors. Explicitly enforce:
      - PoolSwap: out > 0 else ErrInvalidRequest “swap output too small”.
      - RemoveLiquidity: out1>0 or out2>0 else ErrInvalidRequest “shares too small to exit”.
      - AddLiquidity: minted > 0 else ErrInvalidRequest “shares must be > 0”.
  - LCM/GCD units for orderbook
    - Risk: huge LCMs → blow up gas/bit length.
    - Decision: rely on GCD reduction for unit sizes; avoid LCM for single-offer units. If any intermediate product bitlen > 256 (or a chosen cap), reject ErrInvalidRequest “unit size overflow”. Keep helpers but prefer gcd-based normalization.

If you want, I can:
- Add zero-width band checks to CreatePool/UpdatePoolConfig, and guard denominators in v3 branches.
- Add reserve-depletion guard after swaps/exits.
- Introduce FormatDec18 and migrate price index building + genesis rebuild.
- Add Int bitlen caps for orderbook unit math.
==================================================
Allow zero only on full exit.

- Rule
  - Partial removes must leave both reserves > 0.
  - Full exit is allowed when shares == totalShares. In that case:
    - Payout out1=R1, out2=R2.
    - Burn all shares.
    - Delete the pool (remove from `PoolsMap`), emit a terminal event (e.g., pool_removed), and skip post-op band/price checks.

- Rationale
  - Keeps price well-defined for any remaining pool.
  - Lets last LP (or any signer with all shares) exit cleanly.

- Rounding
  - With shares == totalShares, v2 yields exact R1/R2; v3 yields R1/R2 from L-based formulas (up to floor, which matches integer reserves).
  - If dust ever remains due to integer math, require shares == totalShares for deletion; otherwise reject attempts that would zero a reserve.

If you want, I can add this special-case path to `RemoveLiquidity` and update the spec/events accordingly. (done)
==================================================
- Why GCD over LCM for a single offer
  - One offer defines a fixed exchange ratio have:want. The minimal indivisible “unit” is just that ratio reduced to simplest terms.
  - Use gcd(have, want) to reduce:
    - unitHave = have / gcd(have, want)
    - unitWant = want / gcd(have, want)
    - remainingUnits = gcd(have, want)
  - This is exact, smallest possible, and cannot overflow. LCM is unnecessary unless you’re trying to align multiple distinct ratios (not our case).

- What goes wrong with LCM here
  - LCM explodes for large, co-prime numbers: lcm(a, b) = a/gcd(a, b) * b can grow ~a*b, causing huge integers, gas, and index keys.
  - For a single offer, LCM gives you no benefit and only risk.

- Algorithm (single offer)
  - Inputs: haveAmt, wantAmt (sdk.Int > 0)
  - g = gcd(haveAmt, wantAmt)
  - unitHave = haveAmt / g
  - unitWant = wantAmt / g
  - remainingUnits = g
  - Store unitHave, unitWant, remainingUnits in the offer; all subsequent takes operate in integer multiples of these units.

- Overflow/DoS guard (cap bit length)
  - Even with GCD, intermediate ops elsewhere (e.g., gross scaling) can blow up.
  - Add a simple cap:
    - If any intermediate product requires > 256 bits (or chosen cap), reject with ErrInvalidRequest("unit size overflow").
    - Practical check for LCM when it’s ever used: q = a / gcd; if bitlen(q) + bitlen(b) > 256 → overflow risk; reject.

- Examples
  - have=100, want=50 → gcd=50
    - unitHave=2, unitWant=1, remainingUnits=50
  - have=123456789000000000, want=36000000000 → gcd=9000000000
    - unitHave=13717421, unitWant=4, remainingUnits=9000000000

- Benefits
  - Minimal unit size → fewer units, simpler arithmetic
  - Stable, deterministic, lowest gas
  - Avoids pathological big integers and index keys

If you want, I can update MakeOffer/TakeOffer to explicitly use this GCD-first policy and add a 256-bit cap check with consistent sdkerrors.
==================================================
Here’s a tight pass on where we can simplify whaleswap code by leaning on sdk Coin/Coins/DecCoin/Denom utilities, with concrete swaps:

- keeper.normalizeBand (x/whaleswap/keeper/keeper.go)
  - Today: manual length/positivity checks and building coins.
  - Use:
    - sdk.ValidateDenom via sdk.NewCoin (panics on invalid denom) and Coins.Validate (positive, sorted, dedup).
    - Pattern:
      - Build band with sdk.NewCoins(sdk.NewCoin(denom1, a), sdk.NewCoin(denom2, b)) and then band.Validate()
  - Benefit: removes manual >0 and structure checks; one validation path.

- AMM add/remove/swap (x/whaleswap/keeper/msg_liquidity.go, msg_pool_swap.go)
  - Refund and payout handling:
    - Use Coins helpers:
      - coins := sdk.NewCoins(...)
      - coins.Empty() or coins.IsZero() for send/no-send decisions
      - Prefer sdk.Coin.String()/Coins.String() in error contexts
  - Denom validations:
    - If you add any user-supplied band/denom flags later, call types.ValidateDenom early (sdk.ValidateDenom)
  - Reserve math is Dec-based and fine; but for coin arith:
    - Use Coin.SafeSub or Coins.SafeSub when subtracting (prevents panics; returns ok flag)

- Orderbook (x/whaleswap/keeper/msg_orderbook.go)
  - Balance checks:
    - Replace manual GT on Int with coin compare:
      - bal := k.bank.GetBalance(ctx, maker, have.Denom)
      - if !bal.IsGTE(have) → ErrInsufficientFunds
    - For escrow/backing comparisons:
      - backing := k.bank.GetBalance(ctx, moduleAddr, baseDenom)
      - if !backing.IsGTE(sdk.NewCoin(baseDenom, deliverHave)) → ErrInsufficientFunds
  - Index price formatting (Dec):
    - Keep Dec arithmetic but standardize string with fixed precision helper (e.g. FormatDec18) for consistent lexicographic order; DecCoin is not strictly needed, but you can wrap with sdk.NewDecCoinFromDec to document intent.

- Conversions (x/whaleswap/keeper/msg_convert.go)
  - Denom validation:
    - types.ValidateDenom(msg.Denom) and types.ValidateDenom(msg.LiquidDenom) up-front for clearer errors.
  - Coin ops:
    - Use Coins helpers for grouping and .String() for better error context on send/mint/burn.

- Common send/burn/update paths
  - Everywhere you do send/burn/update:
    - Wrap errors with context including the Coins.String() and addresses (you’ve started doing this in AMM; apply uniformly).
  - When building coin sets:
    - Prefer sdk.NewCoins + .Validate() before any bank calls when inputs are user-controlled.

- Misc Int/Coins ops worth adopting
  - Coins.SafeSub/SafeQuoInt/SafeMulInt where present to avoid panics and signal invalid operations cleanly.
  - Coin.IsPositive/IsZero in place of amount.IsPositive() to keep intent tied to coin/denom.
  - coins.AmountOf(denom) instead of scanning/branching on denoms.

Example micro-edits to illustrate style:

- Balance check in MakeOffer:
```go
bal := k.bank.GetBalance(ctx, maker, have.Denom)
if !bal.IsGTE(have) {
  return nil, sdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "have exceeds maker balance: %s < %s", bal.String(), have.String())
}
```

- Payout/send context:
```go
outs := sdk.NewCoins(sdk.NewCoin(pool.CoinA.Denom, out1), sdk.NewCoin(pool.CoinB.Denom, out2))
outs = outs.Sort().Validate() // optional; panics on invalid
if err := k.bank.SendCoinsFromModuleToAccount(ctx, whaleswap.ModuleName, signer, outs); err != nil {
  return nil, cosmossdkerrors.Wrapf(err, "failed to send outputs %s to %s", outs.String(), msg.Signer)
}
```

- Band normalization:
```go
band := sdk.NewCoins(
  sdk.NewCoin(denom1, amt1),
  sdk.NewCoin(denom2, amt2),
)
if err := band.Validate(); err != nil {
  return nil, sdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid price band: %v", err)
}
```

If you want, I can implement these targeted refactors now in keeper.normalizeBand, msg_orderbook balance checks, and unify error wrapping on all bank/nameSvc calls.
==================================================
[5 tools called]

- Simplified and hardened helpers and handlers using SDK Coin/Coins utilities:
  - normalizeBand now constructs with sdk.NewCoins/sd k.NewCoin and calls Coins.Validate() instead of manual checks.
  - Orderbook MakeOffer uses Coin.IsGTE for balance/pfand checks and wraps all bank/index ops with contextual errors.
  - AMM Add/Remove/Swap now wrap bank and pool update calls with rich context; earlier edits already added Lcur>0 guards.

- Kept behavior, reduced custom logic, improved errors:
  - Prefer Coin/Coins methods (.IsGTE, .String, .Validate) over manual Int comparisons.
  - Consistent error wrapping on all state-mutating paths.

If you want, I can continue this pass across remaining files (convert/auction/query paths) to replace manual Int compares and bare errors with sdk Coin/Coins methods and contextual wraps.
==================================================
[7 tools called]

- Added L consistency checks to RemoveLiquidity (concentrated mode):
  - Capture Lbefore and expected dL = Lbefore * shares/total.
  - After applying out1/out2, recompute Lafter and ensure delta = Lbefore − Lafter is non-negative and ≤ dL*(1+1e−6).
  - Prevent reserve depletion on partial exits; keep full-exit path allowed.

- Corrected v3 swap math earlier; fees_earned tracking remains.

Everything lints clean.

==================================================
[3 tools called]

- Reviewed outstanding items and continued:
  - Added L-consistency checks in RemoveLiquidity (concentrated mode) with tolerance, and prevented partial exits that zero reserves; full-exit path transfers all and deletes the pool.
  - Corrected concentrated swap math in PoolSwap earlier; retained fees_earned tracking.
  - Fixed Pools pagination signature; lints clean.
  - Implemented a helper `formatDec18` in `keeper.go` for canonical 18-decimal string formatting (to use later for stable price string indexes).

Remaining high-value TODOs I can take next:
- Use formatDec18 for price index keys in orderbook (OffersByPairPrice) and in genesis rebuilds.
- Add unit tests for v3 formulas and L-consistency.
- Consider proportional initial shares minting based on L (instead of a fixed 100,000).

==================================================
[2 tools called]

- Initial shares are now proportional to initial liquidity:
  - v3 (band set): initialShares = floor(L) from liquidityForReserves.
  - v2 (no band): initialShares = floor(sqrt(R1*R2)).
  - Fallback to 1 if non-positive.
  - Minted to creator as before; pool persisted first.

All changes lint clean.
==================================================
### Plan to fix auction logic

- Authority: redeem by current NFT owner
  - Change `RedeemAuction` to require `caller == nftKeeper.GetOwner(classID, nftID)`.
  - Keep “no current bidder” check via nameservice `GetNFTData`.
  - Files: `x/whaleswap/keeper/msg_auction.go` (replace seller-only check), optionally `types/expected_keepers.go` (ensure `GetOwner` in interface).

- Strict validation on inputs
  - In `OpenAuction`:
    - Validate `msg.BidDenom` with `sdk.ValidateDenom`.
    - Reject if `k.isLiquidDenom(msg.BidDenom)` is true.
    - Keep `sell.Amount > 0`, `sell.Denom != msg.BidDenom`, `sell` solid.
  - Files: `msg_auction.go`.

- Propagate errors for all class policy setters
  - Stop ignoring errors from:
    - `SetNFTClassAlwaysListed`
    - `SetNFTClassValuationFeePct`
    - `SetNFTClassValuationPeriod`
    - `SetNFTClassBidTimeout`
    - `SetNFTClassMinimumBidPercentIncrease`
    - `SetNFTClassAllowedDenoms` (exactly `[bid_denom]`)
  - Wrap with context (classID, bid_denom).
  - Files: `msg_auction.go`.

- Escrow sanity before redeem
  - Before sending funds out, pre-check module balance >= `rec.Sell`.
  - Wrap insufficient escrow with helpful error including `rec.Sell` and module address.
  - Files: `msg_auction.go`.

- Index removal robustness
  - Check and wrap errors on:
    - `AuctionsBySellBid.Remove`
    - `AuctionsByBidSell.Remove`
  - Prefer all-or-nothing: if any removal fails, abort after primary deletion? Safer: remove indexes first, then primary.
  - Files: `msg_auction.go`.

- Query hardening and efficiency
  - Wrap all `Get`/pagination errors with request context (ids/filters).
  - If feasible, use prefix-range pagination on `(sell,bid,auction_id)` and `(bid,sell,auction_id)` indexes to avoid in-transform filtering.
  - Files: `x/whaleswap/keeper/query_auctions.go`.

- Genesis escrow validation (optional but recommended)
  - During `InitGenesis`, aggregate required escrow by denom from `Auctions` and ensure module balance covers totals; panic or log error with precise deficit.
  - Files: `x/whaleswap/keeper/genesis.go`.

- Invariants
  - Add module invariants:
    - Sum of `AuctionRecord.Sell` per denom ≤ module escrow balances.
    - Reverse indexes present for every auction; no dangling entries.
  - Files: `x/whaleswap/module/module.go` (register invariants), new `keeper/invariants.go`.

- Events (optional enhancement)
  - Enrich `EventAuctionCreated`/`EventAuctionRedeemed` to include `seller`, `sell`, `bid_denom` if proto supports; otherwise keep as-is.
  - Files: `proto/dysonprotocol/whaleswap/v1/events.proto`, regen, then emit richer events in `msg_auction.go`.

- Class ID hygiene
  - `classID = whaleswap.dys/auction/{bid_denom}`: ensure `bid_denom` is valid; if nameservice has stricter rules, add a clear error.
  - Files: `msg_auction.go`.

- Tests
  - Add pytest e2e:
    - OpenAuction happy path; class policy verification.
    - Redeem by current owner; fail if non-owner; fail if current_bidder set.
    - Escrow deficit simulated (state tweak) → redeem fails with clear error.
    - Reverse index presence and cleanup on redeem.
  - Files: `tests/whaleswap/test_auction.py` (expand), run with `make test PYTEST_ARGS="tests/whaleswap/test_auction.py`.

- Docs/spec
  - Update `x/whaleswap/spec.md`:
    - Clarify redeem authority = current NFT owner.
    - Note strict error propagation on policy setters.
    - Document escrow checks, invariants, query filtering behavior.

- CLI help
  - Ensure AutoCLI long help reflects owner-based redeem and failure causes (bidder active, escrow missing, non-owner).
  - Files: `x/whaleswap/module/autocli.go`.

Acceptance criteria:
- Redeem requires current NFT owner and no active bidder.
- All class policy setters are error-checked.
- Redeem fails early with explicit message if escrow insufficient.
- Reverse indexes are always removed on redeem; no stale entries.
- Queries wrap errors with context; filtered pagination works with indexes.
- Genesis optional check enforces escrow ≥ sum of sells.
- Tests cover happy and failure paths and pass locally.
==================================================

## New refactor: TAKE_ALL netting with one MoveCoins

I'll open the nameservice move coins helper to confirm how MoveCoins works and whether we can route the whaleswap batch settlement through a single MoveCoins call, and to see how burning integrates. Then I'll update the plan accordingly.

[2 tools called]

I looked at `nameservice` MoveCoins: it pulls all inputs into the nameservice module, then pays all outputs; totals must match per total sum and no negatives. That’s perfect for one-shot settlement with the module itself listed as an input and/or output.

### TAKE_ALL netting with one MoveCoins
- Remove TAKE_FIRST/TAKE_ANY; only TAKE_ALL path remains.
- Change per-leg to plan-only (no sends). It returns “deltas” the batch aggregator will merge.

### Leg planning (applyOnePlan)
For each `TakeItem`:
- Load offer, compute `takeUnits`, `requiredWant` (solid want denom), and `deliverHave` (solid base-have denom; if have is liquid, decode to base).
- Record:
  - outputs[maker] += requiredWant (solid)
  - outputs[taker] += deliverHave (solid)
  - if have is liquid: inputs[maker] += L(have)(deliverHave)
  - if this leg closes the offer: outputs[taker] += offer.PfandLocked (solid)
- Return also the updated offer state (remaining units, status) for batch persistence.

No address-to-module moves here; just who pays/receives what.

### Aggregate and net
- Sum all leg deltas into:
  - outputsByAddr: map[address]Coins
  - makerLiquidInByAddr: map[maker]Coins (only liquid L(have))
  - takerGrossPayByDenom: Σ requiredWant per denom
  - takerSolidRecvByDenom: Σ deliverHave per denom
  - pfandToTakerByDenom
- Compute taker net per solid denom d:
  - takerOutSolid[d] = takerSolidRecv[d] + pfandToTaker[d]
  - takerNet[d] = takerOutSolid[d] - takerGrossPay[d]
  - If takerNet[d] < 0 (deficit):
    - basePart[d] = min(-takerNet[d], taker base balance of d)
    - liquidPart[d] = -takerNet[d] - basePart[d] (in L(d))
  - Else zero.
- Add taker inputs:
  - inputs[taker] += basePart[d] (solid d) and, if needed, L(d) for liquidPart[d].
- Add maker liquid inputs:
  - for each maker: inputs[maker] += makerLiquidInByAddr[maker] (their L(have) totals).
- Compute whaleswap module base input needed per solid denom d so totals balance:
  - outputsSolid[d] = Σ outputsByAddr[*][d] (makers + taker)
  - inputsSolidFromTaker[d] = basePart[d]
  - inputs[whaleswapModule][d] = outputsSolid[d] - inputsSolidFromTaker[d]
- Add outputs to whaleswap module for liquid inflows (to be burned):
  - outputs[whaleswapModule] += Σ L(d) from taker + Σ L(have) from makers

Now totals match per denom:
- Solid d: inputs = basePart[d] + moduleIn[d] = outputsSolid[d]
- Liquid L(x): inputs = taker L(x) + makers L(x) = outputs to whaleswap module L(x)

### Validation
- Taker has balances ≥ basePart[d] and ≥ liquidPart[d] for all d.
- Each maker has balances ≥ their L(have) totals.
- Whaleswap module has solid balances ≥ moduleIn[d] for all d (escrow/backing/pfand combined).
- Offers’ unit math and close transitions are valid.

### One-shot settlement
- Build []banktypes.Input from inputs map and []banktypes.Output from outputs map.
- Call nameservice MoveCoins once:
  - nameSvc.MoveCoins(ctx, { name_destination: whaleswap module address, inputs, outputs })
- Burn aggregated liquid denoms now held by whaleswap module:
  - For each L(x) in outputs[whaleswapModule], call burnLiquid(ctx, L(x)).
- Persist all trades and offer updates, reindex status changes.
- Emit per-trade events and pfand events; assert invariants.

### Notes
- We treat liquid/solid uniformly as Coins; the only special action is burning whatever L(…) ends up at the whaleswap module.
- The whaleswap module appears in both inputs (solid d it contributes) and outputs (liquid it receives to burn).
- No leg-level cache contexts; the entire Msg handler remains atomic at the app level.

If you want, I’ll implement:
- `applyOnePlan` (pure planning)
- the batch aggregator (inputs/outputs maps)
- the single `MoveCoins` call and subsequent `burnLiquid`
- removal of TAKE_FIRST/TAKE_ANY and doc tweak for TAKE_ALL behavior.
======
[4 tools called]

- I refined validation and error messages and finished index maintenance, keeping style idiomatic for Go/Cosmos SDK.

What I changed:
- Validation (single-issue errors, specific messages)
  - `MsgCreateSubscription.ValidateBasic` now checks one field at a time with precise messages (e.g., “script_address is required”, “event_type exceeds 100 characters”).
  - `MsgDeleteSubscription.ValidateBasic` validates `creator` and `subscription_id` separately.
- Errors with context
  - Fee deductions now report creator and error cause both in create and per-trigger paths.
  - Storage errors include the subscription id.
  - Sequence allocation logs “allocate next subscription_id”.
- Indexing
  - Implemented two subscription indexes:
    - status+event_type+id → id
    - creator+status+id → id
  - `addSubIndexes/removeSubIndexes` update both.
  - Handlers call index updates on create/delete and whenever status changes during event processing.
- Event handling
  - Uses the status+event_type index to iterate only enabled subscriptions per type.
  - Applies `task_scheduled_timestamp`, `task_expiry_timestamp`, and optional `task_gas_price` overrides on task creation.
  - GJSON filter matching retained.

Ready to proceed:
- If you want, I’ll add creator+status query endpoints and a `SetSubscription` wrapper to centralize index maintenance on any keeper write, plus merging normalized event JSON into `kwargs.event`.