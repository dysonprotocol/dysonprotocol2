<!--
Guiding Principles:

Changelogs are for humans, not machines.
There should be an entry for every single version.
The same types of changes should be grouped.
Versions and sections should be linkable.
The latest version comes first.
The release date of each version is displayed.
Mention whether you follow Semantic Versioning.

Usage:

Change log entries are to be added to the Unreleased section under the
appropriate stanza (see below). Each entry is required to include a tag and
the Github issue reference in the following format:

* (<tag>) \#<issue-number> message

The tag should consist of where the change is being made ex. (x/staking), (store)
The issue numbers will later be link-ified during the release process so you do
not have to worry about including a link manually, but you can if you wish.

Types of changes (Stanzas):

"Features" for new features.
"Improvements" for changes in existing functionality.
"Deprecated" for soon-to-be removed features.
"Bug Fixes" for any bug fixes.
"Client Breaking" for breaking Protobuf, gRPC and REST routes used by end-users.
"CLI Breaking" for breaking CLI commands.
"API Breaking" for breaking exported APIs used by developers building on SDK.
"State Machine Breaking" for any changes that result in a different AppState given same genesisState and txList.
Ref: https://keepachangelog.com/en/1.0.0/
-->

# Changelog

## [Unreleased]

## [v2.1.0] - 2026-01-26

### Features

* (x/nameservice) Add MsgMoveNft to enable name owners to transfer NFTs between non-module accounts. Includes keeper logic, `EventNftMoved` event emission, CLI command `dysond tx nameservice move-nft`, and integration tests.
* (x/storage) Add StorageList `sort_by` support with deterministic pagination.
* (x/script) Add attached message authz for script exec.
* (p2p) Add GossipSub topic validators for message authentication with ADR-36 signature verification.
* (p2p) Bootstrap libp2p connection automatically when joining network.
* (demo-dwapp) Add /names route and Nameservice placeholder UI, including navigation link and Playwright test.

### Improvements

* (x/script) Simplified query handling to always execute at current block; removed BeginBlock historical-retention validation and logs. Tests and examples updated to use index-based lookups where needed.
* (crontask) Deterministic JSON marshaling helper added to keeper for normalized event processing and minified args/kwargs.
* (docs) Update README documentation and examples sections.

### Client Breaking

* (x/script) Removed `query_height` support from script queries and RPC: `_query(params)` no longer accepts `query_height`. Historical queries are not supported.
* (proto/script) `dysonprotocol.protocol.v1.Params` is now empty. Removed fields `max_relative_historical_blocks` and `absolute_historical_block_cutoff`. Generated files updated.

### CLI Breaking

* (dysond) Any proposals using `/dysonprotocol.script.v1.MsgUpdateParams` must provide an empty `params` object `{}`.

### API Breaking

* (x/script) Removed historical context creation; `QueryRequest` dropped `query_height` field in internal RPC. Public dyslang `_query` signature remains but ignores `query_height` in scripts; passing it has no effect.

### Bug Fixes

* (x/crontask) Query responses now encode empty task lists as [] instead of null, fixing CLI pagination and API consistency. Removed deprecated proto messages and endpoints for scheduled/pending/done tasks.
* (dysvm) Align DYSLANG_SERVER=1 script error JSON with baseline (DYSLANG_SERVER=0) to prevent consensus mismatch. Python FastAPI now returns the full eval response on error, and the Go server client surfaces the full error JSON string, matching baseline logs.
* (dysvm) Add missing `random.sample` to sandbox module mapping in `dysvm_server.py`.
* (dwapp) Server now returns 404 for unresolved name or address.
* (x/nameservice) Fix regex group for DefaultDwAppPattern.
