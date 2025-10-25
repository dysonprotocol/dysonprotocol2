import json


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr)
    return {b.get("denom"): int(b.get("amount")) for b in res.get("balances", [])}


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


def test_make_trade_rate_constraint_pass_fail(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker = env["acc1"]["name"]
    taddr = env["acc1"]["addr"]

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

    # XOR invalid: swap_in + swap_out must fail within MakeTrade
    op_both = {
        "swap": {
            "pool_id": pid,
            "swap_in": {"denom": a, "amount": "10"},
            "swap_out": {"denom": b, "amount": "9"},
        }
    }
    tx1 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"50{a}",
        "--op",
        json.dumps(op_both),
        "--from",
        taker,
        "--gas",
        "200000",
        "--yes",
    )
    assert isinstance(tx1, dict), f"non-dict tx response: {tx1}"
    assert (
        tx1.get("code", 0) != 0
    ), f"expected XOR failure, got success: {json.dumps(tx1, indent=2)}"
    raw_log = tx1.get("raw_log", "")
    assert isinstance(
        raw_log, str
    ), f"raw_log not a string: {json.dumps(tx1, indent=2)}"
    assert (
        "cannot both be set" in raw_log.lower()
    ), f"unexpected error: {json.dumps(tx1, indent=2)}"

    # FAIL: both provided must fail (any amounts)
    out = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"50{a}",
        "--op",
        json.dumps(
            {
                "swap": {
                    "pool_id": pid,
                    "swap_in": {"denom": a, "amount": "10"},
                    "swap_out": {"denom": b, "amount": "11"},
                }
            }
        ),
        "--from",
        taker,
        "--gas",
        "200000",
        "--yes",
    )
    # Must fail with XOR error text
    assert isinstance(out, dict), f"non-dict tx response: {out}"
    assert (
        out.get("code", 0) != 0
    ), f"expected failure, got success: {json.dumps(out, indent=2)}"
    raw_log = out.get("raw_log", "")
    assert isinstance(
        raw_log, str
    ), f"raw_log not a string: {json.dumps(out, indent=2)}"
    assert (
        "cannot both be set" in raw_log.lower()
    ), f"unexpected error: {json.dumps(out, indent=2)}"
