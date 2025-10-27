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


def test_make_trade_v2_exact_in_happy(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    a = env["denoms"][0]
    b = env["denoms"][1]
    taker_name = env["acc3"]["name"]
    taker_addr = env["acc3"]["addr"]

    # Create v2 pool a/b with small reserves from acc3 (has 20 each)
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10{a}",
        "--coins",
        f"10{b}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        taker_name,
    )
    assert txp.get("code", 1) == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"
    ev_pc = [
        e
        for e in txp.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(ev_pc) > 0, f"missing EventPoolCreated: {json.dumps(txp, indent=2)}"
    attrs = {a.get("key"): a.get("value") for a in ev_pc[0].get("attributes", [])}
    pid = _parse_pool_id_attr(attrs)

    # Pre balances
    pre = _bal_map(dysond, taker_addr)
    pre_a = pre.get(a, 0)
    pre_b = pre.get(b, 0)

    # Swap exact-in 5a -> expect some b out
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
    )
    assert (
        tx.get("code", 1) == 0
    ), f"make-trade swap exact-in failed: {json.dumps(tx, indent=2)}"

    # Events
    swaps = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolSwap"
    ]
    assert len(swaps) > 0, f"expected EventPoolSwap, tx: {json.dumps(tx, indent=2)}"
    attrs_s = {a.get("key"): a.get("value") for a in swaps[0].get("attributes", [])}
    pid_swap = _parse_pool_id_attr(attrs_s)
    assert pid_swap == pid, f"swap event pool_id mismatch: got {pid_swap} want {pid}"

    tr_events = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        len(tr_events) > 0
    ), f"expected EventTradeRecorded, tx: {json.dumps(tx, indent=2)}"

    # Parse exact transfer amounts from events
    transfers = [e for e in tx.get("events", []) if e.get("type") == "transfer"]
    # Sum amounts sent by taker (debits)
    sent_attrs = [
        {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in transfers
    ]
    debits = [
        _parse_amount_coin(attrs.get("amount", "0"))
        for attrs in sent_attrs
        if attrs.get("sender") == taker_addr
    ]
    credits = [
        _parse_amount_coin(attrs.get("amount", "0"))
        for attrs in sent_attrs
        if attrs.get("recipient") == taker_addr
    ]
    in_a = sum([amt for (amt, den) in debits if den == a])
    out_b = sum([amt for (amt, den) in credits if den == b])

    # Post balances
    post = _bal_map(dysond, taker_addr)
    post_a = post.get(a, 0)
    post_b = post.get(b, 0)

    # Exact equality checks
    assert in_a == 5, f"expected exact debit: 5{a}, got {in_a}{a}"
    assert (
        pre_a - post_a == in_a
    ), f"debit mismatch: pre_a={pre_a} post_a={post_a} in_a={in_a}"
    assert (
        post_b - pre_b == out_b
    ), f"credit mismatch: pre_b={pre_b} post_b={post_b} out_b={out_b}"
