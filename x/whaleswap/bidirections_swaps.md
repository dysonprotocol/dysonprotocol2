### Implementation Status: COMPLETED

MsgPoolSwap has been removed and replaced with MsgMakeTrade, which provides all the functionality described in this document.

### Goals (ACHIEVED)
- Support per-leg constraints: exact-in (`swap_in`), exact-out (`swap_out`), or both (rate constraint). ✓
- Support Tx-level caps and guarantees: `max_input[]` and `min_output[]` (both repeated). ✓

### Proto changes (COMPLETED)
- MsgMakeTrade (replaces MsgPoolSwap)
  - Keep `input[]` as deprecated alias of caps (back-compat). Add `max_input[]` (new).
  - Enforce caps as the per-denom minimum of `input[]` and `max_input[]` when both provided.
  - Keep `min_output[]` (vector slippage guarantee).
  - Field numbers:
    - trader = 1 (unchanged)
    - input = 2 (deprecated: “use max_input”)
    - legs = 3 (unchanged)
    - min_output = 4 (unchanged)
    - max_input = 5 (new)
- SwapLeg
  - Add `swap_out` as optional coin (denom+amount).
  - At least one of `swap_in` or `swap_out` must be set; both allowed.

### Semantics per leg
- swap_in only (today’s behavior):
  - Use current formulas to compute `out`.
  - Reject if output reserve would hit zero or band violated.
- swap_out only (exact-out):
  - Deduce input denom as “the other pool reserve denom not equal to `swap_out.denom`”.
  - Compute minimal integer input such that, after fee/rounding, computed output ≥ `swap_out.amount`.
    - v2 constant-product (closed form):
      - effInRequired = rIn*(rOut/(rOut − out) − 1)
      - inputCandidate = ceil(effInRequired / (1 − fee))
      - Recompute with truncation; if output < target, inputCandidate++ once.
      - Fail if out ≥ rOut or inputCandidate ≤ 0.
    - v3 banded (approx in-band):
      - token0-in (out = L⋅(sp − sp′)): sp′ = sp − out/L; effIn = L⋅(1/sp′ − 1/sp).
      - token1-in (out = L⋅(1/sp − 1/sp′)): sp′ solves sp′ = 1/(1/sp − out/L); effIn = L⋅(sp′ − sp).
      - Round up to satisfy fee/trunc; clamp sp′ within [sa,sb]; if out exceeds band capacity, fail.
      - Reject if updating reserves would zero a side.
- Both swap_in and swap_out present:
  - Treat as a rate constraint consistent with direction implied by the provided denoms:
    - If `swap_in` provided, compute `out`, require computedOut ≥ swap_out.amount and out.denom == swap_out.denom; else fail.
    - If `swap_out` provided but also `swap_in` provided with different denom orientation, fail.
  - Alternative (future): allow “exact-out with max-in cap”: compute exact-out path, then require computedIn ≤ swap_in.amount.

### Msg-level caps/guarantees
- max_input[]:
  - End-of-tx cap per denom: required debit for denom d must be ≤ cap[d].
  - If both `input[]` and `max_input[]` present, cap[d] = min(input[d], max_input[d]) when both exist; else the one that exists.
  - Missing denom ⇒ cap=0.
- min_output[]:
  - End-of-tx guarantee vector: credits[d] ≥ min_output[d] for all denom entries.
  - Missing denom has no guarantee.

### Keeper implementation (msg_make_trade.go and trade_helpers.go)
- Parse caps: build combined caps map from `input[]` and `max_input[]` (min-merge).
- For each leg:
  - Validate leg (at least one of `swap_in`/`swap_out` set; denoms match pool reserves; amounts > 0).
  - Determine direction:
    - If swap_in set: input denom = swap_in.denom; output denom is the other.
    - If only swap_out set: output denom = swap_out.denom; input denom = the other.
  - Compute (in,out) amounts:
    - Exact-in path: use existing v2/v3 math.
    - Exact-out path: invert as above; apply fee/trunc correction; reject if liquidity/band/reserve constraints fail.
  - If both provided: enforce min-rate constraint as defined above; reject if violated.
  - Update reserves; emit pool update/swap events; record Trade.
  - Accumulate module delta safely per denom (map<string, Int>): +in, −out.
- After legs:
  - Build requiredDebits (trader → module) = all positive module deltas.
  - Build credits (module → trader) = all negative module deltas, abs value.
  - Enforce caps: requiredDebits[d] ≤ cap[d]; else fail.
  - Enforce min_output: credits[d] ≥ min_output[d]; else fail.
  - Execute one multisend (same as today): inputs = {trader: requiredDebits, module: credits}, outputs = {module: requiredDebits, trader: credits}. No negative coins ever constructed.
  - Invariants: assert AMM invariants only once at end; per-leg do light checks (reserves > 0; band in-range).

### Edge cases and solutions
- Ambiguous orientation (swap_out only): Resolve input denom as the other pool reserve denom; reject if pool does not contain swap_out.denom.
- Both swap_in and swap_out with inconsistent denoms (e.g., swap_in.denom equals swap_out.denom): reject as invalid.
- Exact-out too large:
  - v2: out ≥ rOut or computed input causes newOut ≤ 0: reject “insufficient liquidity”.
  - v3: required sp′ outside band: reject; no partial band crossings (document).
- Fee/truncation under-satisfaction:
  - After closed-form inversion, recompute output with fee/trunc; if < target, increment input by 1 and re-evaluate; if still < target (band/reserve limit), reject.
- Per-tx vector caps and guarantees:
  - Caps default to 0 for unspecified denoms (so no accidental debits).
  - It’s valid to provide only `min_output[]` and no caps; route must be self-funding from pool reserves (circular/ring) or fail.
- Liquid denoms:
  - Keep AMM pools solid-only; reject if leg uses liquid denom (consistent with current design).
- Reused pools and cycles:
  - State is updated in-order; repeated legs on same pool are supported; end-of-tx caps/guarantees still enforced.
- Proto back-compat:
  - Mark `input[]` as deprecated; continue to accept it; prefer `max_input[]` in docs/CLI; server picks min with `max_input[]`.

### CLI and tests
- CLI
  - Add `--max-input` (repeatable, coin format).
  - Allow leg JSON to include either/both `swap_in` and `swap_out`.
- Tests
  - Exact-out v2: assert required input increases with min-out; fail if too large vs reserves.
  - Both constraints path: `swap_in=Xd1` and `swap_out≥Yd2`: verify out ≥ Y.
  - Caps: fail when exact-out requires debit > cap.
  - End-of-tx `min_output`: vector satisfied when route yields profits.
  - Circular-profit, no inputs: already covered; ensure no trader debits and positive credits.
  - v3 exact-out: within band, moderate sizes; assert no panic and constraints enforced.

### Rollout (COMPLETED)
- ✓ Proto updated with MsgMakeTrade; "make proto-gen install" run.
- ✓ Leg exact-out path and "both fields" constraint checks implemented in trade_helpers.go.
- ✓ Autocli updated with MakeTrade commands; docs and examples added.
- ✓ Tests added and passing; full suite runs successfully.