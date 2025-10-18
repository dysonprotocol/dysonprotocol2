## TEW Oracle: Ephemeral L2 with Permissionless Providers

### Overview
An Oracle built on TEW creates a short‑lived (ephemeral) L2 instance per job to convert non‑deterministic off‑chain work into a single deterministic result. Providers are permissionless. The L2 runs a commit → reveal → reduce process entirely off‑chain, producing a consensus result that is posted back to L1 as a single response. L1 stores and serves the final result; it does not execute map/reduce nor verify commit‑reveal.

### Goals
- **Permissionless providers**: any address can participate in a job.
- **Deterministic finality**: reduce is executed off‑chain, result chosen by simple majority among reveals, and published once to L1.
- **Ephemeral instances**: each job spins up a fresh L2 instance that terminates after finalization.
- **Minimal on‑chain footprint**: L1 persists job metadata and the final result only.

### Roles & Components
- **User (job creator)**: submits a job with `map_js` and `reduce_js` for provenance (never executed on L1).
- **Providers**: compute maps off‑chain; submit `commit` then `reveal` on L2; may propose a reduced result.
- **L2 Instance (per job)**: owns job state, windows, commit/reveal/proposal sets, majority logic, and emits the final L2→L1 result message.
- **L1 Script**: creates jobs, receives the L2 final result once, and exposes read APIs.

### High‑Level Flow
1. **Job creation (L1)**: user calls `oracle_create_job(map_js, reduce_js, commit_rounds, reveal_rounds)`; script records job metadata and spawns an ephemeral L2 instance configured with commit/reveal windows.
2. **Commit phase (L2)**: providers submit `commit = sha256(canonical_json(map_output) + salt)`.
3. **Reveal phase (L2)**: providers reveal `{map_output, salt}`; L2 validates against commit.
4. **Reduce proposal & selection (L2)**:
   - Any participant proposes a `proposed_result` = reduce(revealed_outputs), computed off‑chain.
   - L2 counts votes for identical JSON results; selects the result with **simple majority** of the currently valid reveals; ties broken deterministically.
   - On selection, L2 finalizes.
5. **Publish result (L2→L1)**: L2 enqueues a single `oracle_result` message to L1 containing `{job_id, result, included_providers, l2_block_meta}`.
6. **Finalize on L1**: L1 marks job DONE and stores the result snapshot.

### Data Model
#### L1 Storage (per job, under `oracle/jobs/{job_id}`)
- **meta**
  - `creator`: bech32 address
  - `l2_instance_id`: string
  - `status`: `PENDING | DONE | CANCELED`
  - `created_height`: int
  - `created_time`: RFC3339 or unix seconds
  - `commit_rounds`: int (relative to L2 genesis round)
  - `reveal_rounds`: int (relative to commit end)
  - `finalization_rule`: string ("simple_majority")
- **code**
  - `map_js`: string (not executed on‑chain)
  - `reduce_js`: string (not executed on‑chain)
- **result** (present only after finalize)
  - `value`: arbitrary JSON result
  - `included_providers`: sorted array of provider addresses that contributed reveals used by reduction
  - `l2_block`: `{height: int, hash: string}`

#### L2 State (per ephemeral instance)
- **job**
  - `job_id`: string
  - `finalization_rule`: "simple_majority"
  - `commit_end_round`: int
  - `reveal_end_round`: int
- **commits**: map `{ provider_addr → commit_hash }`
- **reveals**: map `{ provider_addr → { payload: JSON, salt: string, payload_hash: string } }`
- **reveal_providers**: sorted list of providers with valid reveals
- **proposals**: map `{ provider_addr → proposed_result_json }`
- **consensus**
  - `result`: JSON (set on finalize)
  - `selected_at_round`: int
  - `included_providers`: sorted array

### Interfaces
#### L1 API (transactions)
- `oracle_create_job(map_js: str, reduce_js: str, commit_rounds: int, reveal_rounds: int) -> { job_id, l2_instance_id }`
  - Creates job + ephemeral L2 instance; sets windows.
- `oracle_get_job(job_id: str) -> { meta, code, result? }`
- `oracle_list_jobs(limit?: int, cursor?: string) -> { jobs: [...], next_cursor? }` (optional)
- Optional: `oracle_cancel_job(job_id: str)` if no result yet.

#### L2 tx message types (permissionless providers)
- `oracle_commit`
  - `{ type: "oracle_commit", job_id, provider, commit_hash }`
- `oracle_reveal`
  - `{ type: "oracle_reveal", job_id, provider, payload, salt }`
- `oracle_propose`
  - `{ type: "oracle_propose", job_id, provider, proposed_result }`
  - `proposed_result` must equal the reduce outcome computed off‑chain over the canonical set of currently revealed outputs.
- `oracle_result_to_l1` (emitted by L2 only)
  - `{ type: "oracle_result", job_id, result, included_providers, l2_block }`

### Business Logic (L2)
#### Commit rules
- Accept at most one commit per provider before `commit_end_round`.
- Commit hash = `sha256(canonical_json(payload) + salt)`.

#### Reveal rules
- Accept at most one reveal per provider before `reveal_end_round`.
- Verify reveal matches prior commit.
- Maintain `reveals` map and sorted `reveal_providers`.

#### Reduce proposal and selection
- Let `M = |reveal_providers|` at evaluation time.
- Count votes for identical `proposed_result` JSON values.
- **Simple majority**: accept a result if votes `≥ floor(M/2) + 1`.
- **Tie‑break**: choose the smallest canonical JSON string among tied results.
- **Eagerness**: finalize immediately on majority within reveal window; otherwise decide at the end of the reveal window if a majority exists.

#### Finalization & emission
- On selection:
  - Fix `consensus.result` and `included_providers = sorted(reveal_providers)`.
  - Enqueue exactly one `oracle_result_to_l1` message including `{job_id, result, included_providers, l2_block}`.
  - Ignore proposals after finalization.

### Business Logic (L1)
- **Create job**: allocate `job_id`, persist `meta` and `code`, spawn L2 with configured windows.
- **On `oracle_result`**: set `status = DONE`; persist `result` and `included_providers` with L2 block metadata; emit `oracle_result_ready(job_id)` event.
- **Queries**: return current snapshot.
- **Trust model**: L1 does not execute JS nor verify commit‑reveal; it trusts the L2’s consensus result.

### Determinism Rules
- **Canonical JSON**: `json.dumps(obj, separators=(",",":"), sort_keys=True)` for hashing, equality, and tie‑breaks.
- **Provider ordering**: lexicographic by bech32 address.
- **Windows**: `commit_end_round = genesis_round + commit_rounds`; `reveal_end_round = commit_end_round + reveal_rounds`.

### Security & Integrity Notes
- **Permissionless**: sybil resistance is out of scope for v1 (can be added via staking/identity later).
- **Off‑chain JS**: `map_js` and `reduce_js` execute off‑chain; the chain never runs JS.
- **Majority‑based finality**: guards against minority manipulation; canonicalization prevents equivocation by representation.
- **DoS considerations**: cap per‑block accept rates and total message sizes in L2 tx validation to prevent growth attacks.

### Events & Observability
- On L1:
  - `oracle_request_created(job_id)` when job is created.
  - `oracle_result_ready(job_id)` when result stored.
- On L2:
  - Log counts per round: `commits`, `reveals`, `proposal_votes`, `finalized`.

### Testing Strategy
- **Happy path**: 3 providers commit→reveal; 2 propose same reduce; majority reached; result posted to L1; L1 status = DONE.
- **Edge cases**:
  - Duplicate commit/reveal rejected.
  - Reveal without commit rejected.
  - No majority at reveal end → no finalize.
  - Tie resolved by canonical JSON order.
  - Single emission: ensure only one L2→L1 result is enqueued.

### Future Extensions
- **Staking / identity** for provider selection and anti‑sybil.
- **Weighted majorities** and quorum definitions.
- **Commit‑reveal enhancements** (e.g., chunked payloads, proofs).
- **Audit trail**: store minimal reveal set hash alongside result.

### Glossary
- **Commit**: hash claim of a provider’s map output (with salt) submitted during commit window.
- **Reveal**: later disclosure of the map output and salt; verified against the commit.
- **Reduce**: deterministic aggregation over the set of valid reveals.
- **Simple majority**: more than half of currently valid reveals endorse identical result.


