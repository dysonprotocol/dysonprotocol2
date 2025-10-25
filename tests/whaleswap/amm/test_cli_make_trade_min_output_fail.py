import json


def _parse_pool_id_attr(attrs):
    raw = attrs["pool_id"]
    val = json.loads(raw)
    pid = int(val)
    assert pid > 0
    return pid


def test_make_trade_min_output_fail(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker = env["acc1"]["name"]

    # Create v2 pool a/b
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"60{a}",
        "--coins",
        f"60{b}",
        "--from",
        taker,
    )
    assert txp.get("code", 1) == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"
    ev_pc = [
        e
        for e in txp.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pid = _parse_pool_id_attr(
        {a.get("key"): a.get("value") for a in ev_pc[0].get("attributes", [])}
    )

    # MakeTrade: exact-in 10a, require impossible min-output 1000b
    op = {
        "swap": {
            "pool_id": pid,
            "swap_in": {"denom": a, "amount": "10"},
        }
    }
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"50{a}",
        "--op",
        json.dumps(op),
        "--min-output",
        f"1000{b}",
        "--from",
        taker,
        "--yes",
    )
    assert isinstance(tx, dict), f"non-dict tx response: {tx}"
    assert (
        tx.get("code", 0) != 0
    ), f"expected failure, got success: {json.dumps(tx, indent=2)}"
    raw_log = tx.get("raw_log", "")
    assert isinstance(raw_log, str), f"raw_log not a string: {json.dumps(tx, indent=2)}"
    assert (
        "min_output not met for" in raw_log.lower()
    ), f"unexpected error: {json.dumps(tx, indent=2)}"
