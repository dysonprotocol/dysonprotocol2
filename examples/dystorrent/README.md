Blockchain-Coordinated Torrents for Dyson Protocol
=================================================

Goal
----

Enable onchain generation and HTTP seeding of BitTorrent v1 “.torrent” files that represent datasets stored under a Dyson storage index prefix. After a snapshot torrent is created, data may be removed onchain while offchain peers continue to mirror via P2P using the WebSeed backed by the onchain WSGI server.

Key Concepts
------------

- **Index prefix → files**: Every storage entry whose `index` begins with the provided prefix becomes a file in a multi-file torrent. The file path is the suffix after the prefix (normalized, no traversal). Empty suffix maps to `index.json`.
- **WebSeed**: The torrent embeds a WebSeed pointing to `/seed/{index}/`. Clients fetch files via HTTP from the onchain WSGI server and then seed over P2P.
- **Determinism**: Fixed piece length (1 MiB) and lexicographic file order ensure deterministic `infohash` for the same dataset.
- **Chaining**: Snapshots can include manifests and/or references to prior torrents to create a chain of historical snapshots. This allows pruning older onchain data once mirrored.

API (Script)
------------

- `def gen_torrent(index: str) -> bytes`:
  - Builds a valid BitTorrent v1 multi-file `.torrent` from storage under `index` owned by the current script.
  - Uses `bencoder.encode` and `hashlib.sha1` for `info["pieces"]`.
  - Sets WebSeed fields: `url-list` and `httpseeds` to `"/seed/{index}/"`.

WSGI Endpoints
--------------

- `GET /torrent/{index}`:
  - Returns the bencoded `.torrent` (Content-Type: `application/x-bittorrent`).
  - `index` is URL-decoded; it is used as the storage prefix.

- `GET /seed/{index}/{path...}`:
  - Serves raw bytes for a single storage entry at full index `"{index}/{path...}"` owned by this script.
  - Content-Type: `application/octet-stream` (simple default).

Implementation Notes
--------------------

- Listing uses page-key pagination via `_query` with `QueryStorageListRequest`.
- File bytes are UTF-8 encoded from `entry.data` (for binary, store base64-encoded data and decode in a future enhancement).
- Paths are validated to forbid traversal (no `..`, no empty segments). Empty maps to `index.json`.
- Torrent fields:
  - `info`: `name`, `piece length`, `files`, `pieces`, `private: 0`.
  - Top-level: `announce` (empty), `url-list`, `httpseeds`, `comment` (JSON with `index` and `owner`).

Retention and Chaining
----------------------

- Create periodic snapshot torrents, e.g. `posts/snapshots/{height}/`.
- Include a `manifest.json` file with block height and optional pointer to previous snapshot.
- After snapshot creation, schedule deletion of old live data via crontask (out of scope here).

Testing Guidance
----------------

- Prepare storage entries under a small prefix.
- Fetch `/torrent/{prefix}` and bdecode to verify `files`, `piece length`, `url-list`.
- Fetch `/seed/{prefix}/{path}` for each file and compare bytes to stored values.

Limitations
-----------

- No HTTP Range support yet (clients still work with full responses; add later for efficiency).
- All data treated as UTF-8 strings. Future work: binary-aware storage (base64) and content-type guessing.


