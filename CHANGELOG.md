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

### Features

* (x/nameservice) #6-3 Add MsgMoveNft to enable name owners to transfer NFTs between non-module accounts. Includes keeper logic, `EventNftMoved` event emission, CLI command `dysond tx nameservice move-nft`, and integration tests.
* (demo-dwapp) #6-5 Add /names route and Nameservice placeholder UI, including navigation link and Playwright test.

### Bug Fixes

* (x/crontask) #6-4 Query responses now encode empty task lists as [] instead of null, fixing CLI pagination and API consistency. Removed deprecated proto messages and endpoints for scheduled/pending/done tasks.
* (dysvm) #6-6 Align DYSLANG_SERVER=1 script error JSON with baseline (DYSLANG_SERVER=0) to prevent consensus mismatch. Python FastAPI now returns the full eval response on error, and the Go server client surfaces the full error JSON string, matching baseline logs.
