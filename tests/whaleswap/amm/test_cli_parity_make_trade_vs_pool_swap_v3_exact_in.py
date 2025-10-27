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


def test_parity_make_trade_vs_pool_swap_v3_exact_in(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]

    # Create two identical v3 pools with band strictly containing initial price [0.5, 2.0]
    def _create_v3():
        tx = dysond(
            "tx",
            "whaleswap",
            "create-pool",
            "--coins",
            f"100{a}",
            "--coins",
            f"100{b}",
            "--min-price",
            f"2{a}",
            "--min-price",
            f"1{b}",
            "--max-price",
            f"1{a}",
            "--max-price",
            f"2{b}",
            "--min-collateral-ratio",
            "1.5",
            "--max-leverage-ratio",
            "3.0",
            "--max-borrow-percent",
            "0.8",
            "--from",
            taker,
            "--gas",
            "auto",
        )
        assert tx.get("code", 1) == 0, json.dumps(tx, indent=2)
        ev_pc = [
            e
            for e in tx.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
        ]
        return _parse_pool_id_attr(
            {a.get("key"): a.get("value") for a in ev_pc[0].get("attributes", [])}
        )

    pid1 = _create_v3()
    pid2 = _create_v3()

    # PoolSwap on pid1: exact-in 10a
    leg_swap = {
        "pool_id": pid1,
        "swap_in": {"denom": a, "amount": "10"},
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

    # MakeTrade on pid2: single swap leg exact-in 10a
    op = {
        "swap": {
            "pool_id": pid2,
            "swap_in": {"denom": a, "amount": "10"},
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
        in_a_ps == 10 and in_a_mt == 10
    ), f"expected debit 10{a}, got pool={in_a_ps}, make={in_a_mt}"
    assert (
        out_b_ps == out_b_mt
    ), f"out parity mismatch: pool={out_b_ps}{b} make={out_b_mt}{b}"
