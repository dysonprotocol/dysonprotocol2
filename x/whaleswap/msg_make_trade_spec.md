### Plan: Unified TradeOperation (mix pool swaps and offer takes with single settlement)

- Proto
  - Add new message and RPC:
    - TradeOperation: oneof of existing shapes
      - oneof op:
        - SwapLeg swap = 1    // reuse current `SwapLeg { pool_id, swap_in?, swap_out? }`
        - TakeItem take = 2   // reuse current `TakeItem { offer_id, take_units }`
    - MsgMakeTrade:
      - trader: string
      - repeated Coin max_input  // end-of-tx debit caps for trader (vector)
      - repeated TradeOperation operations
      - repeated Coin min_output // end-of-tx trader credit guarantees (vector)
    - MsgMakeTradeResponse:
      - repeated Coin amount_out // trader’s final net credits by denom
  - Service:
    - rpc MakeTrade(MsgMakeTrade) returns (MsgMakeTradeResponse)
  - After editing, run: make proto-gen install

- Keeper architecture
  - Extract reusable, side-effectful executors:
    - executeSwapLeg(ctx, trader, leg, pool) → returns:
      - out: actual in/out coins, updated pool, per-leg events, saved Trade
      - accumulators: moduleDelta[denom] += in - out
    - executeTakeItem(ctx, taker, item, offer) → mutates offer/trades and fills aggregator entries:
      - outputsByAddr[maker] += want
      - outputsByAddr[taker] += have or base(have) if liquid
      - inputsByAddr[maker] += liquidHave (for burn)
      - later netting + module cover handled at end (see below)
  - Shared settlement aggregator (unifies PoolSwap and TakeOffer paths):
    - inputsByAddr: map[address]Coins (non-negative only)
    - outputsByAddr: map[address]Coins (non-negative only)
    - helpers:
      - addInput(addr, coin), addOutput(addr, coin)
      - toBankIO() → []banktypes.Input, []banktypes.Output
  - Implement MsgMakeTrade:
    - Parse caps (max_input → cap[denom])
    - For each operation, in order:
      - if swap: validate leg; call executeSwapLeg; update moduleDelta map
      - if take: validate item; call executeTakeItem; offers update and trades recorded immediately
    - Post-ops: finalize pooled swaps into aggregator
      - From moduleDelta: for denom with +X (module receives), add:
        - inputsByAddr[trader] += X
        - outputsByAddr[module] += X
      - For denom with −Y (module pays), add:
        - inputsByAddr[module] += Y
        - outputsByAddr[trader] += Y
    - Post-ops: finalize orderbook netting (reuse TakeOffer logic on current agg)
      - Net taker credits vs maker wants per solid denom
      - Add taker base inputs to cover remaining maker wants
      - Add taker liquid inputs (to be burned) if still needed
      - Add module solid inputs to cover any final remainder to makers
      - Add liquid-to-module outputs for burn (as in TakeOffer)
    - Enforce end-of-tx constraints
      - Trader debit caps: sum inputsByAddr[trader] per denom ≤ cap[denom]
      - Trader min outputs: sum outputsByAddr[trader] per denom ≥ min_output[denom]
    - Settlement (single multisend):
      - wsMoveCoins(ctx, inputsByAddr→[]Input, outputsByAddr→[]Output)
    - Invariants: call AMM and orderbook invariants (reuse existing checks)
    - Response: amount_out = outputsByAddr[trader]
  - Refactor MsgPoolSwap and MsgTakeOffer to use the same executors and aggregator:
    - PoolSwap: run swap legs, convert moduleDelta to aggregator entries for module/trader, enforce caps + min_output, then wsMoveCoins
    - TakeOffer: build maker/taker outputs/inputs as today via executors and aggregator, then wsMoveCoins
  - Events
    - Keep per-leg EventPoolSwap and EventTradeRecorded
    - Offers keep EventOfferTaken, PFAND events as today

- Validation and semantics
  - Operations processed strictly in provided order; state (pools/offers) updates between ops
  - SwapLeg supports exact-in, exact-out, or both (rate constraint) as implemented
  - TakeItem uses existing take semantics, including PFAND and liquid-have handling
  - max_input caps apply only to trader debits (no effect on maker/module)
  - min_output applies only to trader credits
  - Pools remain solid-only; liquid denoms rejected implicitly by pool reserves

- CLI
  - New tx command make-trade:
    - Flags:
      - --max-input <coin> (repeatable)
      - --op '<json>' (repeatable), where op is either:
        - {"swap":{"pool_id":1,"swap_in":{"denom":"udys","amount":"100"}}}
        - {"swap":{"pool_id":1,"swap_out":{"denom":"ufoo","amount":"10"}}}
        - {"take":{"offer_id":42,"take_units":"5"}}
      - --min-output <coin> (repeatable)

- Tests
  - Mix: take-first-then-swap and swap-first-then-take; verify same end result
  - Netting: two complementary takes result in credits-only for taker (no debits)
  - Coverage (pass): if taker lacks solid B but holds sufficient liquid B, taker-liquid covers wants; taker receives unit have; maker receives unit want; module burns taker-liquid
  - Caps/min-output across mixed ops enforced at end
  - Circular-profit legs plus offer netting (no trader debits)
  - Exact-out leg + order take nets within min_output constraints
  - Multi-maker payouts and liquid-have burn path within single settlement

- Migration and rollout
  - Keep existing MsgPoolSwap and MsgTakeOffer; add MsgMakeTrade
  - Refactor internals to shared executors/aggregator without breaking existing behavior
  - Regenerate protos: make proto-gen install
  - Update docs and CLI help with mixed examples

  ### Edge cases and undefined behavior (with fixes)

- Empty operations
  - Solution: require operations ≥ 1.

- Invalid TradeOperation shape
  - Solution: oneof must have exactly one: reject if neither/both set; validate positive amounts and non-empty denoms.

- SwapLeg orientation errors
  - Problem: `swap_in.denom` or `swap_out.denom` not in pool; both present but mismatched direction.
  - Solution: validate denoms in pool; if both set, enforce computed out denom equals `swap_out.denom` and amount ≥ required.

- Exact-out infeasible
  - Problem: out ≥ reserve; band limit (v3) exceeded; rounding after fee produces < target.
  - Solution: closed-form input with fee/trunc recheck (+1 step); fail if still < target or band/reserve hit.

- Zero/negative outputs
  - Solution: reject out ≤ 0 for any leg.

- Liquid denoms in pools
  - Solution: forbid liquid denoms in SwapLegs; validate.

- Nonexistent pool/offer or closed/insufficient units
  - Solution: fail fast; include offer status/remaining units in error.

- Duplicate take of same offer within a tx
  - Problem: multiple TakeItems exceeding remaining units.
  - Solution: track seen/taken units in-memory; reject overflow.

- Mixed op ordering and state updates
  - Problem: correctness if a later op fails.
  - Solution: rely on tx atomicity; update pool/offer state per-op; any error aborts and rolls back.

- Aggregation correctness across AMM + orderbook
  - Problem: miscounting trader debits/credits across both domains.
  - Solution: single aggregator:
    - moduleDelta for swaps: +in −out → convert to inputs/outputs between trader and module.
    - orderbook executors populate outputs/inputs for maker/taker/module (including pfand release, liquid-have to module).
    - Never construct negative coins; map-accumulate per denom.

- Debit caps semantics
  - Problem: what caps apply to orderbook vs swaps?
  - Solution: caps apply only to trader end-of-tx debits (sum of inputsByAddr[trader] per denom) after all netting; enforce ≤ cap[denom]; unspecified denom ⇒ 0.

- Min-output semantics
  - Problem: mixing sources; duplicates denoms.
  - Solution: enforce credits to trader (sum per denom) ≥ min_output[denom]; sum duplicate constraints per denom.

- Maker wants and taker credits netting
  - Problem: vector netting across many makers and taker credits.
  - Solution: same as TakeOffer:
    - Net taker same-denom credits against maker wants.
    - Cover remaining maker wants with taker base, then taker liquid L(denom).
    - If still deficit, cover from module’s solid balances; fail if module lacks backing.

- Liquid-have burn path
  - Problem: ensure liquid sent to module is actually burned.
  - Solution: after wsMoveCoins, call nameservice burn for module-held liquid amounts; bubble errors.

- Event ordering/consistency
  - Problem: mixed ops interleave events.
  - Solution: emit per-op events in execution order:
    - EventPoolSwap, EventTradeRecorded (AMM)
    - EventOfferTaken (+ EventPfandReleased if closing) (orderbook)

- Trades indexing
  - Problem: duplicates and mixed sources.
  - Solution: record every op as a Trade with pool_id set (AMM) or offer_id set (orderbook); index in TradesByPool/TradesByTaker.

- Gas/DoS
  - Problem: very large operations list.
  - Solution: soft cap length (e.g., 100 ops) or rely on gas; document gas growth O(ops).

- Rounding drift across many legs
  - Problem: integer truncation accumulates.
  - Solution: use Dec math internally; truncate only at coin boundaries; invariants at end.

- Reused pools/cycles
  - Problem: price drift across ops.
  - Solution: update pool reserves per-op; band checks each time.

- Conflicting min_output vs caps
  - Problem: both cannot be satisfied.
  - Solution: fail with precise error: min_output not met or debit exceeds cap; check caps before min_output to surface cause.

- Duplicate denoms in flags
  - Problem: repeated coins.
  - Solution: normalize with sdk.Coins (sums duplicates) for `max_input` and `min_output`.

- Authorization
  - Problem: who is taker for TakeItem?
  - Solution: set taker = msg.trader for all TakeItem ops; reject if attempt to set different taker.

- Cross-module invariant checks
  - Problem: AMM/orderbook divergence.
  - Solution: run AMM invariants and orderbook invariants after settlement; bubble errors.

- CLI/JSON op parsing
  - Problem: malformed `--op` entries.
  - Solution: strong validation with helpful errors; allow multiple `--op` flags or a JSON array.

### Test Parsing Discipline and Event Normalization (added)

- Event normalization utility
  - Implemented `tests/whaleswap/amm/normalize_events.py` with deep JSON parsing for event values, recursively handling nested JSON.
  - Provides `normalize_events(events)` that returns a map of event type → list of normalized attribute dicts.

- Assert-first parsing rule in tests
  - Replace `.get()` fallbacks with stepwise assertions on structure and types to catch failures precisely.
  - Example (EventOfferCreated):
    - `assert 'events' in tx`
    - `evdict = normalize_events(tx['events'])`
    - `assert 'dysonprotocol.whaleswap.v1.EventOfferCreated' in evdict`
    - `rows = evdict['dysonprotocol.whaleswap.v1.EventOfferCreated']; assert len(rows) == 1`
    - `offer_id = rows[0]['offer_id']; assert isinstance(offer_id, int)`

- Transfer parsing
  - `sum_transfers_for_addr(tx, addr)` now uses `normalize_events` for stable extraction of `transfer` events.
  - Tests assert exact event-derived counts against wallet deltas to avoid false positives.

- Impact
  - The parity test `test_cli_parity_swap_then_take_vs_take_then_swap.py` was refactored to use these utilities and assertions; it passes.


# New spec

Here’s a precise, implementation-ready spec to (re)build MakeTrade cleanly, using the existing PoolSwap and TakeOffer logic as the source of truth, with a path to unify all three.

### Goals
- Implement MsgMakeTrade that can mix pool swap legs and orderbook take items in any order.
- Aggregate all effects and do one settlement via wsMoveCoins at the end.
- Enforce per-denom max_input (caps) over aggregated debits; enforce min_output over aggregated credits.
- Keep PoolSwap and TakeOffer as-is for now (reference), but structure MakeTrade using extracted helpers so all three can converge onto the same core functions next.

### Message and CLI
- Protobuf: already defined; keep as is.
  - MsgMakeTrade: trader, repeated max_input, repeated operations (oneof swap or take), repeated min_output.
  - TradeOperation: oneof swap (SwapLeg) or take (TakeItem).
  - SwapLeg: pool_id, optional swap_in, optional swap_out (support in-only, out-only, or both with equality constraint).
- Autocli: already in place. No change required.

### Data Flow and Aggregators
- Aggregators:
  - deltaByDenom map[string]Int for AMM module deltas only (positive: module receives; negative: module pays).
  - inputsByAddr map[string]Coins and outputsByAddr map[string]Coins for orderbook-style settlement.
- At the end:
  - Convert AMM deltas into inputs/outputs under trader and module accounts.
  - Net orderbook flows and cover deficits as needed.
  - Enforce caps and min_output.
  - Execute single wsMoveCoins(inputs, outputs).
  - Burn module-held liquid.
  - Check AMM invariants.

### Validation Rules
- Common:
  - operations must be non-empty.
  - trader must decode as a valid bech32 address.
- SwapLeg:
  - pool_id > 0 and pool exists with exactly two reserves.
  - Must specify swap_in or swap_out (or both).
  - If swap_in provided: denom must be one of pool coins; exact-in math applies.
  - If swap_out provided: denom must be one of pool coins; exact-out math applies.
  - If both provided: swap_out denom must match computed output denom AND computed out amount must equal exactly swap_out.amount.
  - V2 math: constant product + per-leg fee, exact-in/out as implemented in PoolSwap.
  - V3 math: band checks and fee; respect min/max price band; ensure liquidity > 0; exact-in/out as implemented in PoolSwap.
- TakeItem:
  - offer_id must exist and be open; remaining_units positive.
  - take_units parsed; must be positive and ≤ remaining_units.
  - Update offer remaining units, have/want amounts; close if units go to zero; release pfand only once on close.
- Caps and min_output:
  - Caps apply only to trader’s final debits (inputsByAddr[trader]).
  - min_output applies only to trader’s final credits (outputsByAddr[trader]).

### Algorithm for MakeTrade (Keeper.MakeTrade)
1. Validate msg (trader, operations non-empty).
2. Build caps = Coins(msg.MaxInput...).
3. Initialize aggregators:
   - deltaByDenom := map[string]Int{}
   - inputsByAddr := map[string]Coins{}
   - outputsByAddr := map[string]Coins{}
4. For each operation in msg.Operations in order:
   - If swap:
     - Call tradeApplySwapLeg(ctx, msg.Trader, leg) -> (inCoin, outCoin, err)
       - This function must:
         - Load pool, apply v2 or v3 math with fee.
         - Enforce exact equality when both swap_in and swap_out provided (already fixed).
         - Update pool reserves and fees.
         - Emit EventPoolSwap.
         - Record Trade and emit EventTradeRecorded.
         - Return the actual in/out coins.
     - Accumulate AMM delta:
       - deltaByDenom[inCoin.Denom] += inCoin.Amount
       - deltaByDenom[outCoin.Denom] -= outCoin.Amount
   - If take:
     - Call tradeApplyTakeItem(ctx, msg.Trader, item) -> (maker, makerWant, takerRecv, makerLiqIn, pfandReleased, err)
       - This function must:
         - Validate and update the offer; handle unit arithmetic and pfand release on close.
         - Persist trade and emit EventTradeRecorded and EventOfferTaken.
         - Return contributions:
           - makerWant: credit owed to maker (solid denom)
           - takerRecv: credit owed to trader (solid denom or decoded base if maker’s have is liquid)
           - makerLiqIn: liquid denom the maker must pay into the module (for burn)
           - pfandReleased: solid credit to the trader on full close
     - Accumulate orderbook flows:
       - addOut(maker, makerWant)
       - addOut(trader, takerRecv)
       - if makerLiqIn.Amount > 0: addIn(maker, makerLiqIn) (module will burn; see below)
       - if pfandReleased.Amount > 0: addOut(trader, pfandReleased)
5. Convert AMM deltaByDenom to inputs/outputs:
   - For each denom, modAmt:
     - If modAmt > 0: addIn(trader, modAmt denom), addOut(module, modAmt denom).
     - If modAmt < 0: addIn(module, |modAmt| denom), addOut(trader, |modAmt| denom).
6. Net and cover orderbook flows:
   - tradeNetAndCover(ctx, traderBech, inputsByAddr, outputsByAddr):
     - Net trader’s solid credits against maker wants by denom.
     - Cover remaining wants from trader solid, then trader liquid (whaleswap.dys/coins/<solid>).
     - If trader still short, cover with module’s solid (validate sufficiency or error).
     - Ensure any liquid inputs to module are mirrored to module outputs for burn.
7. Enforce caps: For inputsByAddr[trader], require amount ≤ caps for each denom. On violation, error “debit exceeds cap for <denom>: need <amount> <= cap <cap>”.
8. Enforce min_output: For outputsByAddr[trader], require amount ≥ requested for each denom in min_output. On violation, error “min_output not met for <denom>: got <got> < <need>”.
9. Build single settlement:
   - inputs := []banktypes.Input from inputsByAddr (skip empty)
   - outputs := []banktypes.Output from outputsByAddr (skip empty)
   - Require both non-empty (“no inputs or outputs for make-trade move”).
   - Call wsMoveCoins(ctx, inputs, outputs).
10. Burn module liquid:
    - tradeBurnModuleLiquid(ctx, outputsByAddr) to burn any whaleswap.dys/coins/<solid> delivered to module.
11. Invariants:
    - AssertAMMInvariants(ctx) to ensure AMM consistency post-aggregation.
12. Response:
    - Return MsgMakeTradeResponse{AmountOut: outputsByAddr[trader]}.

### Helper Functions (Unification Targets)
- Already present and should be the only place with business logic:
  - `tradeApplySwapLeg(ctx, trader, leg) (in sdk.Coin, out sdk.Coin, err error)`:
    - Must be identical in math and validations to PoolSwap (v2 & v3), including exact-equality rate constraint when both provided.
    - Emits EventPoolSwap, records Trade, emits EventTradeRecorded.
  - `tradeApplyTakeItem(ctx, taker, item) (maker string, makerWant sdk.Coin, takerRecv sdk.Coin, makerLiqIn sdk.Coin, pfandReleased sdk.Coin, err error)`:
    - Must be identical to TakeOffer logic: units math, closing, pfand.
    - Emits EventTradeRecorded, EventOfferTaken; updates offer and indexes.
  - `tradeNetAndCover(ctx, traderBech, inputsByAddr, outputsByAddr) error`:
    - Must implement solid credits netting, coverage from trader solid → trader liquid → module solid; enforce module sufficiency.
  - `tradeBurnModuleLiquid(ctx, outputsByAddr) error`:
    - Must burn liquid that arrives to module (nameservice burn).
  - `wsMoveCoins(ctx, inputs, outputs) error`:
    - Validations: non-empty, totals match; send Inputs to module then module to Outputs.

### Metrics & Invariants (clarified)

- TradeMetrics: Introduced a telemetry model and query to make invariants observable and debuggable.
  - `TradeMetrics` (in `whaleswap.proto`) includes:
    - `num_trades`
    - `escrowed_pool_coins` (sum of pool reserves)
    - `escrowed_offer_coins` (sum of remaining_have for non-liquid offers)
    - `escrowed_auction_coins` (sum of auction sell escrows)
    - `escrowed_pfand` (sum of pfand_locked across open liquid-have offers)
    - `fees_earned` (sum across pools; informational)
    - `escrowed_liquid_coins` (solid liquid-backing remainder; see below)
  - Query:
    - `rpc Metrics(QueryMetricsRequest) returns (QueryMetricsResponse)`
    - Autocli: `dysond query whaleswap metrics`

- Liquid-backing semantics:
  - `escrowed_liquid_coins` reports the solid-denom backing required for minted liquid balances after accounting for other components.
  - Computation: `backing = actual_module_solids − (escrowed_pool_coins + escrowed_offer_coins + escrowed_auction_coins + escrowed_pfand)` per denom.
  - Rationale: When pfand and AMM use denoms like `udys`, backing must be derived as a partition of module solids rather than via raw liquid counts.

- Invariant redesign:
  - The module balance invariant now asserts exact equality:
    - `module_balances == escrowed_pool + escrowed_offers + escrowed_auctions + escrowed_pfand + escrowed_liquid_backing` (per denom)
  - Failure message includes a breakdown: `(amm, escrow, auction, pfand, liquid_backing)`.
  - Avoids false failures when pfand denom overlaps with AMM reserves by separating components explicitly.

- MakeTrade post-conditions:
  - After single-settlement and liquid burn, call unified invariants (`AssertInvariants`) to validate AMM and orderbook accounting.

- Tests added:
  - `test_cli_metrics_liquid_backing_smoke.py`: verifies `escrowed_liquid_coins == 900` per base denom after setup and module holds no liquid.
  - PFAND release on close (existing): now passes with invariant redesign.

These functions are shared across MakeTrade, and (in the second phase) will also be used by PoolSwap and TakeOffer by refactoring them to orchestrate the same helpers rather than re-implementing logic.

### Error Text Uniformity (do not change)
- “operations must be non-empty”
- “swap leg invalid”
- “input denom %s not in pool %d”
- “output denom %s not in pool %d”
- “swap_out must be > 0”
- “exact-out equals/exceeds reserve”
- “insufficient liquidity for exact-out”
- “resulting price below band after swap”
- “resulting price above band after swap”
- “computed out %s != required %s”
- “debit exceeds cap for %s: need %s <= cap %s”
- “min_output not met for %s: got %s < %s”
- “no inputs or outputs for make-trade move”

### Events
- For each swap leg:
  - EventPoolSwap, EventTradeRecorded
- For each take:
  - EventTradeRecorded, EventOfferTaken
- Settlement uses standard bank events (coin_spent/received/transfer) via wsMoveCoins.
- All event attribute values are JSON-encoded strings (tests must json.loads values).

### Settlement Semantics
- Exactly one multisend via wsMoveCoins per MakeTrade.
- No pre-escrow.
- If settlement fails, entire tx fails and all state updates rollback (SDK semantics).

### Tests to Add/Ensure (under `./tests/whaleswap/amm/`)
- make_trade_rate_constraint_pass_fail (already added; now passing)
- pool_swap_rate_constraint_pass_fail (added; passing)
- v2 exact-in/out happy and infeasible via MakeTrade
- v3 exact-in/out happy and capacity/band boundary via MakeTrade
- caps enforcement: single and multi-denom; exact error text
- min_output vector pass and fail; exact error text
- swap→take vs take→swap equivalence test (same final balances)
- netting reduces debits across two takes (show lower trader debit vs no netting)
- two makers with multi-take and single settlement
- liquid-have offer: ensure makerLiqIn is burned; PFAND release aggregates into trader outputs
- module coverage success and module insufficient fail (exact error)
- reused pools, 3-leg cycle profit (credits only, no trader debits)
- duplicate max-input/min-output flags normalized and enforced
- v3 exact-out rounding step and impossible fail text
- invariants hold after MakeTrade
- 50 small ops complete within a tx (large batch gas but not timing out)

### Phase 2 (refactor to unify all three)
- Update `MsgPoolSwap` handler to:
  - For each leg: call tradeApplySwapLeg for math and events
  - Use deltaByDenom → convert to inputs/outputs like MakeTrade
  - Enforce caps (msg.MaxInput) and min_output; single wsMoveCoins; invariants
- Update `MsgTakeOffer` handler to:
  - For each item: call tradeApplyTakeItem and accumulate into inputs/outputs
  - Net, cover, single wsMoveCoins, burn liquid, invariants
- Outcome: all three use the same helpers. PoolSwap/TakeOffer will then be thin orchestration wrappers (just like MakeTrade).

This spec preserves original functions as references, while delivering a clean MakeTrade and a clear path to unify PoolSwap/TakeOffer to the same core helpers.