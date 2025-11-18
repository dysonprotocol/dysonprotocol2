## Whaleswap test plan (CLI, Swagger API, Dyslang)

### Migration delta (scripts → module)

- Tests must stop attaching MsgSend for fees; module minting to itself skips nameservice fees in wrapping/LP flows.
- Use single-pool `swap --pool-id` everywhere; multi-hop = multiple msgs.
- Wrappers removed: no liquid denom usage in tests. Use SettlementMode (ESCROW/LIQUID) with base denoms.
- Module account owns `whaleswap.dys` root; tests can assert authority by querying nameservice owner to be the module address.
- Orderbook takes use MsgMakeTrade with TakeItem operations (TAKE_ALL semantics only). All legs are planned, netted, and settled via one aggregated multi-send from the whaleswap module helper, followed by burning any liquid inputs at the module. Liquid wants are disallowed at MakeOffer.

### Scope

- Validate x/whaleswap end-to-end for four feature areas:
  - AMM: pools (create/update), LP (add/remove), swap, owner gating, bands, fees
  - Orderbook: make/take/cancel, liquid mode Pfand, indexes and queries
  - Auctions: open/redeem, NFT class policy, allowed denoms, reverse indexes
  - Address metrics: per-address lifetime counters/coins, including leverage `profit` and `losses` arrays
- Exercise three surfaces for each area:
  - CLI (autocli): dysond tx/query whaleswap
  - Swagger API (gRPC-Gateway): HTTP GET/POST against REST endpoints
  - Dyslang scripts: call whaleswap Msg/Query via _msg/_query

### Test harness and conventions

- Use existing pytest infrastructure and fixtures from tests/conftest.py:
  - chainnet: bootstraps network; returns dysond command runner per-chain
  - generate_account, faucet: account creation and funding
  - api_address: REST host:port for Swagger tests
- Do not use time.sleep(); rely on dysond query wait-tx and poll_until_condition
- Let errors bubble up; use plain asserts and pytest.raises where needed
- Prefer small, focused tests that assert one behavior at a time
- For event-derived IDs, parse tx result events with type:
  - dysonprotocol.whaleswap.v1.EventPoolCreated → pool_id
  - dysonprotocol.whaleswap.v1.EventOfferCreated → offer_id
  - dysonprotocol.whaleswap.v1.EventAuctionCreated → auction_id

### File layout

- tests/whaleswap/
  - amm/test_amm_cli.py
  - amm/test_amm_api.py
  - amm/test_amm_script.py
  - orderbook/test_orderbook_cli.py
  - orderbook/test_orderbook_api.py
  - orderbook/test_orderbook_script.py
  - auction/test_auction_cli.py
  - auction/test_auction_api.py
  - auction/test_auction_script.py

### Shared helpers (patterns)

- Funding and keys:
```python
dysond = chainnet[0]
[name, addr] = generate_account("user")
faucet(addr, amount=1_000_000)
```

- Wait for tx success:
```python
tx = dysond("tx", "whaleswap", "create-pool", "--coin-a", "1000udys",
            "--coin-b", "500ufoo", "--from", name)
assert tx.get("code", 1) == 0, tx
```

- Extract ID from events:
```python
pool_evs = [e for e in tx.get("events", []) if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"]
pool_id = int([a for e in pool_evs for a in e.get("attributes", []) if a.get("key") == "pool_id"][0]["value"])
```

- REST base URL in tests:
```python
base = f"http://{api_address['host']}:{api_address['port']}"
```

---

## Address metrics

- CLI smoke (`tests/whaleswap/test_address_metrics.py`):
  - Query `whaleswap address-metrics --address <addr>` for a fresh address and assert zero/empty values, including the `profit` and `losses` arrays.
- REST coverage:
  - GET `/dysonprotocol/whaleswap/v1/metrics/address/{addr}` and ensure the JSON mirrors CLI output for both empty and active addresses.
- Future leverage scenarios:
  - Drive a profitable close followed by a loss-making close; confirm `profit` increases only on gains, `losses` increases only on realized losses, and dashboards can derive net P&L as `profit - losses` per denom.

---

## AMM

### CLI tests (amm/test_amm_cli.py)

- CreatePool (v2 constant product):
- create with --coin-a, --coin-b, optional --fee-rate
  - assert event pool_id and query pool returns canonical denom order (denomA < denomB)
  - shares minted to creator: bank balance of shares_denom > 0

- CreatePool with band (v3 concentrated):
  - add --min-price and --max-price bands
  - reject if initial price outside band

- UpdatePoolConfig (owner-only):
  - non-owner update fails; majority owner (>50% shares) update succeeds
  - fee and band changes validated; current price must remain within new band

- AddLiquidity (owner-only):
  - v2: ratio-preserving join; excess refund present; minted shares > 0
  - v3: refunds one side to match ΔL; post-op price within band

- RemoveLiquidity:
  - v2: proportional exit; v3: band-aware outputs; post-op price within band

  - MakeTrade with SwapLeg operations (single or multiple pools):
  - v2 and v3 paths; amount out > 0; post-op price within band; out denom matches
  - Supports exact-in, exact-out, or rate-constrained swaps per leg
  - To route across multiple pools, include multiple SwapLeg operations in one MakeTrade

Example CLI:
```bash
dysond tx whaleswap create-pool --coin-a=1000udys --coin-b=500ufoo --fee-rate=0.003udys --from alice
dysond tx whaleswap create-pool --coin-a=1000udys --coin-b=500ufoo \
  --min-price=1udys,2ufoo --max-price=1udys,3ufoo --from alice
dysond tx whaleswap add-liquidity --pool-id=1 --amount1=200udys --amount2=100ufoo --from alice
dysond tx whaleswap remove-liquidity --pool-id=1 --shares=50 --from alice
dysond tx whaleswap make-trade --op='{"swap":{"pool_id":1,"swap_in":{"denom":"udys","amount":"100"}}}' --min-output=50ufoo --from bob
```

### Swagger API tests (amm/test_amm_api.py)

- GET pool by id:
```bash
curl "$BASE/dysonprotocol/whaleswap/v1/pools/1"
```

- GET pools with pagination:
```bash
curl "$BASE/dysonprotocol/whaleswap/v1/pools?pagination.limit=50"
```

- Assert JSON fields: coinA/coinB, shares_denom, fee_rate, min_price/max_price, num_trades

### Dyslang script tests (amm/test_amm_script.py)

- Upload a small script that wraps whaleswap Msgs via _msg:
```python
code = '''
from dys import _msg

def amm_create(denom_a, amt_a, denom_b, amt_b):
    return _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": "${SIGNER}",
        "coin_a": {"denom": denom_a, "amount": str(amt_a)},
        "coin_b": {"denom": denom_b, "amount": str(amt_b)}
    })
'''
```
- Execute amm_create via tx script exec; assert tx success and pool exists via query
- Add/remove liquidity and swap using similar wrappers; assert events and pool state deltas

---

## Orderbook

### CLI tests (orderbook/test_orderbook_cli.py)

- MakeOffer (normal):
  - have=solid, want=solid; escrow in module; EventOfferCreated; OffersByOwner shows status=open

- MakeOffer (liquid):
  - have is liquid L(S); optionally update params.pfand_per_offer > 0 via UpdateParams (authority)
  - locks pfand; EventPfandLocked emitted

- MakeTrade with TakeItem operations (atomic batch netting):
  - Only TAKE_ALL semantics; no `--take` flag. If any leg is infeasible, the entire batch fails and no state changes persist.
  - The keeper aggregates all inputs/outputs across legs and performs a single multi-send via whaleswap’s internal helper. Events are emitted per leg during planning and are rolled back on failure.
  - Same-denom netting: if the taker both pays and receives the same solid denom across legs, reduce the taker’s output by the nettable amount before computing deficits.
  - Taker funding priority: base balance first, then liquid L(denom) for the remainder (which is burned after settlement).
  - Maker-have liquid: makers supply L(have), which is routed to the module and burned; the taker receives the solid base-have.
  - Maker-have normal: taker receives solid have from module escrow/backing.
  - Pfand: locked on liquid-have offers at make; released to the taker on close and included in outputs.
  - Offer status transitions to closed when `remaining_units == 0`; reverse indexes are removed on close/cancel.

- CancelOffer:
  - maker can cancel open; third-party can cancel liquid offer if maker lacks ≥1 unit liquid have; pfand released to closer

Example CLI:
```bash
dysond tx whaleswap make-offer --have=100udys --want=50ufoo --from alice
dysond tx whaleswap make-offer --have=100udys --want=50ufoo --settlement-mode settlement-liquid --from alice
dysond tx whaleswap make-trade --op='{"take":{"offer_id":1,"take_units":"10"}}' --op='{"take":{"offer_id":2}}' --from bob
dysond tx whaleswap cancel-offer --offer-id=2 --from bob
```

### Swagger API tests (orderbook/test_orderbook_api.py)

- GET offer by id:
```bash
curl "$BASE/dysonprotocol/whaleswap/v1/offers/1"
```

- List offers with optional filters:
```bash
curl "$BASE/dysonprotocol/whaleswap/v1/offers?have_denom=udys&want_denom=ufoo&pagination.limit=100"
```

- OffersByOwner with optional status:
```bash
curl "$BASE/dysonprotocol/whaleswap/v1/offers/by-owner?owner=$ADDR&status=open"
```

- Trades:
```bash
curl "$BASE/dysonprotocol/whaleswap/v1/trades/by-offer?offer_id=1&pagination.limit=50"
curl "$BASE/dysonprotocol/whaleswap/v1/trades/by-taker?taker=$ADDR&pagination.limit=50"
```

Assertions:
- Correct filtering, stable pagination, and presence/absence in reverse indexes after close/cancel

### Dyslang script tests (orderbook/test_orderbook_script.py)

- Script wrappers:
```python
code = '''
from dys import _msg

def mk_offer(have_denom, have_amt, want_denom, want_amt):
    return _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": "${SIGNER}",
        "have": {"denom": have_denom, "amount": str(have_amt)},
        "want": {"denom": want_denom, "amount": str(want_amt)}
    })
'''
```
- Execute mk_offer; query offer; then take/cancel via wrappers and assert status, trades, and pfand events

---

## Auctions

### CLI tests (auction/test_auction_cli.py)

- OpenAuction:
  - provide --sell=<amountdenom> and --bid-denom
  - assert NFT minted class whaleswap.dys/auction/{bid_denom} to seller; record stored; reverse indexes set

- RedeemAuction:
  - when no bidder: burns NFT, releases sell escrow to caller, deletes record and reverse indexes
  - when bidder exists: redeem must fail with ErrInvalidRequest

Example CLI:
```bash
dysond tx whaleswap open-auction --seller=$(dysond keys show alice -a) --bid-denom=ufoo --sell=100udys --from alice
dysond tx whaleswap redeem-auction --auction-id=1 --from alice
```

### Swagger API tests (auction/test_auction_api.py)

- GET single auction:
```bash
curl "$BASE/dysonprotocol/whaleswap/v1/auctions/1"
```

- List auctions with filters:
```bash
curl "$BASE/dysonprotocol/whaleswap/v1/auctions?sell_denom=udys&bid_denom=ufoo&pagination.limit=50"
```

Assertions:
- After redeem, GET returns not found; filtered listings exclude redeemed id in both reverse indexes

### Dyslang script tests (auction/test_auction_script.py)

- Script wrappers to open and redeem auctions:
```python
code = '''
from dys import _msg

def open_auc(seller, bid_denom, sell_denom, sell_amt):
    return _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": seller,
        "bid_denom": bid_denom,
        "sell": {"denom": sell_denom, "amount": str(sell_amt)}
    })
'''
```
- Execute open_auc; assert class policy/allowed denoms via nameservice queries where applicable; then test redeem path with/without bidder

---

## Negative and edge cases (spread across suites)

- AMM: attempt non-owner LP; band violations on add/remove/swap; invalid fee_rate
- Orderbook: invalid denoms; want must be solid; insufficient funds; liquid close index cleanup
- Auctions: sell==bid denom rejected; redeem with active bidder rejected

---

## Pagination and sorting checks

- Use pagination.limit/offset and page_reverse to verify stable orderings for:
  - Pools, Offers (with/without filters), TradesByOffer/Taker, Auctions (with/without filters)
  - Ensure non-overlapping pages and ascending/descending as requested

---

## Execution notes

- CLI commands use the chainnet run_command wrapper; it appends --yes and a generous --gas by default
- Prefer dysond query wait-tx to gate on transaction finality before querying state
- For REST, use api_address fixture to form base URL; prefer requests over external tools

---

## Out-of-scope for MVP

- ComposeOperations is removed; no tests planned
- Cross-chain behaviors are out of scope

## NOTES
### Plan: e2e tests for whaleswap
- **Directories**: create suites under `tests/whaleswap/{amm,orderbook,auction}/`
- **Surfaces covered**: CLI primary; add a few REST and Dyslang script cases mirroring CLI
- **Harness**: reuse `chainnet`, `generate_account`, `faucet`, `api_address`, `register_name` from `tests/conftest.py`; gate on tx finality via `dysond("query","wait-tx",...)`; avoid time.sleep

### Shared patterns
- **ID extraction**: parse from tx events (e.g., `EventPoolCreated`, `EventOfferCreated`, `EventAuctionCreated`)
- **Module address**: `dysond("query","auth","module-account","whaleswap")` → use for escrow/pfand balance checks
- **Assertions**: one behavior per test; prefer direct state queries after each tx

### AMM e2e (tests/whaleswap/amm/)
- `test_create_pool_v2_success`: create pool with no band; verify canonical denom order, non-empty shares, shares denom pattern `whaleswap.dys/pools/{pool_id}`
- `test_create_pool_v3_with_band_success`: create with min/max; verify current price within band
- `test_create_pool_reject_zero_width_band`: min==max → ErrInvalidRequest
- `test_update_pool_config_owner_only`: non-owner fails; majority owner succeeds; verify updated fee/band
- `test_add_liquidity_owner_only`: owner add succeeds (refunds possible in v3); non-owner add fails
- `test_remove_liquidity_partial_keeps_reserves_positive`: proportional exit (v2) and band-aware exit (v3); rejects if would zero a reserve (partial)
- `test_remove_liquidity_full_exit_deletes_pool`: burn all shares → pays full reserves and removes pool
- `test_make_trade_swap_v2_single_pool`: in/out denoms enforced; out > 0; price stays valid; min_out honored
- `test_make_trade_swap_v3_single_pool`: band respected; Lcur guard; out > 0
- `test_fees_accrue_to_pool`: perform swaps; assert `pool.fees_earned` increases and denoms/amounts sane
- `test_amm_invariant_error_context_on_bad_update`: craft invalid UpdatePoolConfig to trigger invariant failure; assert raw_log includes contextual Wrapf message (e.g., “AMM invariant after UpdatePoolConfig: pool_id=…”)
- REST smoke:
  - `test_pools_list_pagination`: GET pools list with pagination; stable ordering
- Dyslang smoke:
  - `test_script_wrapped_create_pool`: small script calling `MsgCreatePool`; assert pool exists

### Orderbook e2e (tests/whaleswap/orderbook/)
- `test_make_offer_normal_escrows_have`: maker creates solid→solid; module escrow balance increases; OffersByOwner shows open
- `test_make_trade_take_settles_and_closes`: batch take fully via MakeTrade; Trade recorded; offer status=closed; reverse indexes removed
- `test_cancel_offer_refunds_normal_have`: cancel open normal offer → refund solid have to maker; EventOfferCancelled
- `test_make_offer_liquid_have_pfand_locked`: require pfand from params; liquid have accepted; pfand locked event; no have escrow
- `test_make_trade_take_liquid_have_path`: taker pays want (base+liquid mix) via MakeTrade; burns maker L(have); pfand released on close; Trade.Received uses base-have denom
- `test_third_party_cancel_liquid_offer_if_maker_lacks_liquid`: simulate maker lacks ≥1 unit L(have); third-party cancel succeeds; pfand to closer
- `test_validate_denoms_and_reject_liquid_want`: invalid denoms rejected; liquid want rejected, liquid have allowed
- `test_offers_by_owner_status_validation`: unknown status → error; valid statuses paginate correctly
- `test_module_balance_check_for_want_before_maker_payout`: taking offer with insufficient module want balance yields clear InsufficientFunds (rare path; assert message)
- `test_orderbook_invariants_observed`: create few offers (normal and liquid), assert module balances match sum of escrow/pfand (query module account + Offers list)

### Auctions e2e (tests/whaleswap/auction/)
- `test_open_auction_success_and_class_policy`: solid sell escrowed; class `whaleswap.dys/auction/{bid}` ensured; policy setters effective; reverse indexes populated
- `test_redeem_auction_by_current_owner_no_bidder`: fetch current NFT owner via nft query; redeem succeeds; burns NFT; releases escrow; reverse indexes removed
- `test_redeem_fails_with_active_bidder`: simulate nameservice current_bid set; redeem rejected with clear error
- `test_redeem_fails_on_escrow_deficit`: artificially drain module escrow denom (via controlled tx in test) and assert ErrInsufficientFunds with context
- `test_open_auction_denoms_validation`: invalid or liquid sell/bid denoms rejected; sell!=bid enforced
- REST smoke:
  - `test_auctions_list_filters`: GET with sell/bid filters, paginate; redeemed auctions absent
- Dyslang smoke:
  - `test_script_wrapped_open_redeem`: script calling MsgOpenAuction/MsgRedeemAuction; assert behavior

### File layout and names
- `tests/whaleswap/amm/test_amm_cli.py`
- `tests/whaleswap/amm/test_amm_api.py`
- `tests/whaleswap/amm/test_amm_script.py`
- `tests/whaleswap/orderbook/test_orderbook_cli.py`
- `tests/whaleswap/orderbook/test_orderbook_api.py`
- `tests/whaleswap/orderbook/test_orderbook_script.py`
- `tests/whaleswap/auction/test_auction_cli.py`
- `tests/whaleswap/auction/test_auction_api.py`
- `tests/whaleswap/auction/test_auction_script.py`

### Run examples
- CLI-focused single test: make test PYTEST_ARGS="tests/whaleswap/amm/test_amm_cli.py::test_pool_swap_v2_single_pool"
- Full AMM suite: make test PYTEST_ARGS="tests/whaleswap/amm"
- Auction smoke: make test PYTEST_ARGS="tests/whaleswap/auction/test_auction_cli.py"

- I’ll start by scaffolding the CLI tests for AMM, then orderbook, then auctions, following `test_nameservice_e2e.py` patterns and using the `conftest.py` helpers.
