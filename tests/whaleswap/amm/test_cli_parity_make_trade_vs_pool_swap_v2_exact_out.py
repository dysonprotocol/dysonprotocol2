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


def test_parity_make_trade_vs_pool_swap_v2_exact_out(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]

    # Create two identical v2 pools (100a/100b each)
    tx1 = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        taker,
    )
    assert tx1.get("code", 1) == 0, json.dumps(tx1, indent=2)
    ev_pc1 = [
        e
        for e in tx1.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pid1 = _parse_pool_id_attr(
        {a.get("key"): a.get("value") for a in ev_pc1[0].get("attributes", [])}
    )

    tx2 = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        taker,
    )
    assert tx2.get("code", 1) == 0, json.dumps(tx2, indent=2)
    ev_pc2 = [
        e
        for e in tx2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pid2 = _parse_pool_id_attr(
        {a.get("key"): a.get("value") for a in ev_pc2[0].get("attributes", [])}
    )

    # PoolSwap on pid1: exact-out 9b
    leg_swap = {
        "pool_id": pid1,
        "swap_out": {"denom": b, "amount": "9"},
    }
    ps = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        f"50{a}",
        "--legs",
        json.dumps(leg_swap),
        "--from",
        taker,
    )
    assert ps.get("code", 1) == 0, json.dumps(ps, indent=2)
    transfers_ps = [e for e in ps.get("events", []) if e.get("type") == "transfer"]
    rows_ps = [
        {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in transfers_ps
    ]
    in_a_ps = sum(
        [
            _parse_amount_coin(r.get("amount", "0"))[0]
            for r in rows_ps
            if r.get("sender") == taker_addr
            and _parse_amount_coin(r.get("amount", "0"))[1] == a
        ]
    )
    out_b_ps = sum(
        [
            _parse_amount_coin(r.get("amount", "0"))[0]
            for r in rows_ps
            if r.get("recipient") == taker_addr
            and _parse_amount_coin(r.get("amount", "0"))[1] == b
        ]
    )

    # MakeTrade on pid2: single swap leg exact-out 9b
    op = {
        "swap": {
            "pool_id": pid2,
            "swap_out": {"denom": b, "amount": "9"},
        }
    }
    mt = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"50{a}",
        "--op",
        json.dumps(op),
        "--from",
        taker,
    )
    assert mt.get("code", 1) == 0, json.dumps(mt, indent=2)
    transfers_mt = [e for e in mt.get("events", []) if e.get("type") == "transfer"]
    rows_mt = [
        {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in transfers_mt
    ]
    in_a_mt = sum(
        [
            _parse_amount_coin(r.get("amount", "0"))[0]
            for r in rows_mt
            if r.get("sender") == taker_addr
            and _parse_amount_coin(r.get("amount", "0"))[1] == a
        ]
    )
    out_b_mt = sum(
        [
            _parse_amount_coin(r.get("amount", "0"))[0]
            for r in rows_mt
            if r.get("recipient") == taker_addr
            and _parse_amount_coin(r.get("amount", "0"))[1] == b
        ]
    )

    assert (
        out_b_ps == 9 and out_b_mt == 9
    ), f"expected credit 9{b}, got pool={out_b_ps}, make={out_b_mt}"
    assert (
        in_a_ps == in_a_mt
    ), f"in parity mismatch: pool={in_a_ps}{a} make={in_a_mt}{a}"
