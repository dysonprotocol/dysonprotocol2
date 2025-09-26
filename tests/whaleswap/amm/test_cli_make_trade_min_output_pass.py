import json


def _parse_pool_id_attr(attrs):
    raw = attrs["pool_id"]
    val = json.loads(raw)
    pid = int(val)
    assert pid > 0
    return pid


def _parse_amount_coin(s):
    text = str(s)
    i = 0
    n = len(text)
    while i < n and text[i].isdigit():
        i += 1
    return int(text[:i]), text[i:]


def test_make_trade_min_output_pass(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]

    # Create v2 pool a/b
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
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

    # MakeTrade: exact-in 10a, require min-output 1b (vector pass)
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
        f"1{b}",
        "--from",
        taker,
        "--gas",
        "auto",
    )
    assert tx.get("code", 1) == 0, f"min-output pass failed: {json.dumps(tx, indent=2)}"
    transfers = [e for e in tx.get("events", []) if e.get("type") == "transfer"]
    rows = [
        {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in transfers
    ]
    out_b = sum(
        [
            _parse_amount_coin(r.get("amount", "0"))[0]
            for r in rows
            if r.get("recipient") == taker_addr
            and _parse_amount_coin(r.get("amount", "0"))[1] == b
        ]
    )
    assert out_b >= 1, f"expected at least 1{b}, got {out_b}{b}"
