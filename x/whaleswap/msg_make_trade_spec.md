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