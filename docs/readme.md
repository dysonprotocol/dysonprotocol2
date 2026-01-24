### Dyson Protocol Docs

- **Bank Guide** — Query balances and transfer tokens via CLI and dyslang.
  - [docs/bank_guide.md](./bank_guide.md)

- **Staking Guide** — List validators, delegate, query/withdraw rewards, and harvest‑and‑restake via scripts.
  - [docs/staking_guide.md](./staking_guide.md)

- **Scripting Guide** — Deploy and execute on‑chain Python scripts, expose DWapps via WSGI, encode/decode messages, and access scripts by name.
  - [docs/scripting_guide.md](./scripting_guide.md)

- **Dyslang Guide** — Sandbox APIs: `_query`, `_msg`, gas and AST‑node metering, execution context, events, `dys_eval`, and coverage.
  - [docs/dyslang_guide.md](./dyslang_guide.md)

- **Storage Guide** — On‑chain key/value storage with JSON payloads, `index_prefix` listings, pagination, and binary data patterns.
  - [docs/storage_guide.md](./storage_guide.md)

- **Nameservice Guide** — Commit–reveal registration, Harberger valuations, names as NFTs, destinations, minting coins/NFTs, and DWapp resolution.
  - [docs/nameservice_guide.md](./nameservice_guide.md)

- **Crontask Guide** — Schedule messages for future execution, query/delete tasks, and build self‑perpetuating workflows.
  - [docs/crontask_guide.md](./crontask_guide.md)

Do not edit these files directly. Instead, edit the source files in the `notebooks/` directory and run `make test PYTEST_ARGS="tests/test_docs.py -m docs"` to regenerate the markdown files.