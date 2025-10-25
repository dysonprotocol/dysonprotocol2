import json


def test_make_trade_note_recorded(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    a = env["denoms"][0]
    b = env["denoms"][1]
    trader_name = env["acc1"]["name"]
    trader_addr = env["acc1"]["addr"]

    # Create pool
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--from",
        trader_name,
    )
    assert txp.get("code", 1) == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"
    ev_pc = [
        e
        for e in txp.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(ev_pc) > 0, f"missing EventPoolCreated: {json.dumps(txp, indent=2)}"
    attrs = {a.get("key"): a.get("value") for a in ev_pc[0].get("attributes", [])}
    pool_id = int(json.loads(attrs["pool_id"]))

    # Execute make-trade with a note
    note_text = "test trade note"
    op = {"swap": {"pool_id": pool_id, "swap_in": {"denom": a, "amount": "10"}}}
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"20{a}",
        "--op",
        json.dumps(op),
        "--trade-note",
        note_text,
        "--from",
        trader_name,
    )
    assert tx.get("code", 1) == 0, f"make-trade failed: {json.dumps(tx, indent=2)}"

    # Verify note in EventTradeRecorded
    trade_events = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        len(trade_events) > 0
    ), f"missing EventTradeRecorded: {json.dumps(tx, indent=2)}"
    event_attrs = {
        a.get("key"): a.get("value") for a in trade_events[0].get("attributes", [])
    }
    assert (
        event_attrs.get("note", "").strip('"') == note_text
    ), f"note mismatch in event: got {event_attrs.get('note')} want {note_text}"
    trade_id = int(event_attrs.get("trade_id", "0").strip('"'))

    # Query trade and verify note persisted
    qtrade = dysond("query", "whaleswap", "trade", "--trade-id", str(trade_id))
    assert isinstance(qtrade, dict), f"query returned non-dict: {type(qtrade)} {qtrade}"
    trade = qtrade.get("trade", {})
    assert isinstance(trade, dict), f"trade is not dict: {type(trade)} {trade}"
    assert (
        trade.get("note") == note_text
    ), f"note not persisted: {json.dumps(trade, indent=2)}"


def test_make_trade_note_length_validation(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    a = env["denoms"][0]
    b = env["denoms"][1]
    trader_name = env["acc1"]["name"]

    # Query max_note_length param
    params = dysond("query", "whaleswap", "params")["params"]
    max_len = int(params.get("max_note_length", 128))
    assert max_len > 0, f"max_note_length must be > 0: {params}"

    # Create pool
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--from",
        trader_name,
    )
    assert txp.get("code", 1) == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"
    ev_pc = [
        e
        for e in txp.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(ev_pc) > 0, f"missing EventPoolCreated: {json.dumps(txp, indent=2)}"
    attrs = {a.get("key"): a.get("value") for a in ev_pc[0].get("attributes", [])}
    pool_id = int(json.loads(attrs["pool_id"]))

    # Attempt make-trade with note exceeding max_note_length
    long_note = "x" * (max_len + 1)
    op = {"swap": {"pool_id": pool_id, "swap_in": {"denom": a, "amount": "5"}}}
    out = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"10{a}",
        "--op",
        json.dumps(op),
        "--trade-note",
        long_note,
        "--from",
        trader_name,
        "--gas",
        "100000000",  # raw=True requires gas flag
        raw=True,
    )
    # raw=True with --gas returns dict for failed transactions
    assert isinstance(out, dict), f"expected dict response, got: {type(out)}"
    assert out.get("code", 0) != 0, f"expected transaction to fail, got success: {out}"
    raw_log = out.get("raw_log", "").lower()
    assert "note too long" in raw_log, f"expected 'note too long' error, got: {out}"


def test_params_max_note_length_default(chainnet):
    dysond = chainnet[0]
    params = dysond("query", "whaleswap", "params")["params"]
    max_note_length = int(params.get("max_note_length", 0))
    assert (
        max_note_length == 128
    ), f"expected default max_note_length=128, got {max_note_length}"
