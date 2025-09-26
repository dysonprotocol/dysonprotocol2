import json


def _parse_pool_id_attr(attrs):
    raw = attrs["pool_id"]
    val = json.loads(raw)
    pid = int(val)
    assert pid > 0
    return pid


def test_make_trade_caps_duplicate_normalization_pass(chainnet, ws_setup_env):
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
        f"20{a}",
        "--coins",
        f"20{b}",
        "--from",
        taker,
        "--gas",
        "auto",
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

    # Exact-in 10a; cap normalized client-side to 11a (no duplicates), should pass
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
        f"11{a}",
        "--op",
        json.dumps(op),
        "--from",
        taker,
        "--gas",
        "auto",
    )
    assert (
        tx.get("code", 1) == 0
    ), f"duplicate max-input normalization pass failed: {json.dumps(tx, indent=2)}"
