import json


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr)
    return {b.get("denom"): int(b.get("amount")) for b in res.get("balances", [])}


def _parse_pool_id_attr(attrs):
    raw = attrs["pool_id"]
    val = json.loads(raw)
    pid = int(val)
    assert pid > 0, f"invalid pool_id: {val} from raw={raw}"
    return pid


def _parse_amount_coin(s):
    text = str(s)
    i = 0
    n = len(text)
    while i < n and text[i].isdigit():
        i += 1
    amt = int(text[:i])
    denom = text[i:]
    return amt, denom


def test_make_trade_v3_exact_in_happy(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]

    # Create v3 pool with band strictly containing initial price (1.0 b/a): [0.5, 2.0]
    txp = dysond(
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
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert txp.get("code", 1) == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"
    ev_pc = [
        e
        for e in txp.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert ev_pc, f"missing EventPoolCreated: {json.dumps(txp, indent=2)}"
    pid = _parse_pool_id_attr(
        {a.get("key"): a.get("value") for a in ev_pc[0].get("attributes", [])}
    )

    # Pre balances
    pre = _bal_map(dysond, taker_addr)
    pre_a = pre.get(a, 0)
    pre_b = pre.get(b, 0)

    # Exact-in 5 a
    op = {
        "swap": {
            "pool_id": pid,
            "swap_in": {"denom": a, "amount": "5"},
        }
    }
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"20{a}",
        "--op",
        json.dumps(op),
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert (
        tx.get("code", 1) == 0
    ), f"make-trade exact-in failed: {json.dumps(tx, indent=2)}"

    swaps = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolSwap"
    ]
    assert swaps, f"expected EventPoolSwap: {json.dumps(tx, indent=2)}"
    pid_swap = _parse_pool_id_attr(
        {a.get("key"): a.get("value") for a in swaps[0].get("attributes", [])}
    )
    assert pid_swap == pid, f"pool_id mismatch: {pid_swap} != {pid}"

    tr_events = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert tr_events, f"missing EventTradeRecorded: {json.dumps(tx, indent=2)}"

    # Parse transfer events
    transfers = [e for e in tx.get("events", []) if e.get("type") == "transfer"]
    rows = [
        {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in transfers
    ]
    debits = [
        _parse_amount_coin(r.get("amount", "0"))
        for r in rows
        if r.get("sender") == taker_addr
    ]
    credits = [
        _parse_amount_coin(r.get("amount", "0"))
        for r in rows
        if r.get("recipient") == taker_addr
    ]
    in_a = sum([amt for (amt, den) in debits if den == a])
    out_b = sum([amt for (amt, den) in credits if den == b])

    # Post balances and exact checks
    post = _bal_map(dysond, taker_addr)
    post_a = post.get(a, 0)
    post_b = post.get(b, 0)

    assert in_a == 5, f"expected debit 5{a}, got {in_a}{a}"
    assert pre_a - in_a == post_a, f"a mismatch: pre={pre_a} in={in_a} post={post_a}"
    assert post_b - pre_b == out_b, f"b mismatch: pre={pre_b} out={out_b} post={post_b}"
