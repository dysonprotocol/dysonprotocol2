import json
from tests.whaleswap.amm.parse_amounts_multi import (
    parse_amounts_multi,
    sum_transfers_for_addr,
)
from tests.whaleswap.amm.normalize_events import normalize_events


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr)
    return {b.get("denom"): int(b.get("amount")) for b in res.get("balances", [])}


def _parse_pool_id_attr(attrs):
    assert "pool_id" in attrs, f"missing pool_id in attrs: {attrs}"
    pid = int(attrs["pool_id"])  # supports both int and numeric string
    assert pid > 0, f"invalid pool_id: {pid} from attrs={attrs}"
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


def _create_pool(dysond, creator_name, a, b, ai=10, bi=10):
    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"{ai}{a}",
        "--coins",
        f"{bi}{b}",
        "--from",
        creator_name,
    )
    assert tx.get("code", 1) == 0, f"create-pool failed: {json.dumps(tx, indent=2)}"
    assert "events" in tx, f"no events in tx: {json.dumps(tx, indent=2)}"
    evdict = normalize_events(tx["events"])  # deep-parsed
    etype = "dysonprotocol.whaleswap.v1.EventPoolCreated"
    assert etype in evdict, f"missing {etype}: {json.dumps(evdict, indent=2)}"
    rows = evdict[etype]
    assert len(rows) == 1, f"expected one {etype}, got {len(rows)}: {rows}"
    attrs = rows[0]
    return _parse_pool_id_attr(attrs)


def _take_op(offer_id, units):
    return {"take": {"offer_id": offer_id, "take_units": str(units)}}


def _swap_in_op(pool_id, denom_in, amount_in):
    return {
        "swap": {
            "pool_id": pool_id,
            "swap_in": {"denom": denom_in, "amount": str(amount_in)},
        }
    }


def _make_offer(dysond, maker_name, have, want):
    tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        have,
        "--want",
        want,
        "--from",
        maker_name,
    )
    assert tx.get("code", 1) == 0, f"make-offer failed: {json.dumps(tx, indent=2)}"
    assert "events" in tx, f"no events in tx: {json.dumps(tx, indent=2)}"
    evdict = normalize_events(tx["events"])  # deep-parsed
    etype = "dysonprotocol.whaleswap.v1.EventOfferCreated"
    assert etype in evdict, f"missing {etype}: {json.dumps(evdict, indent=2)}"
    rows = evdict[etype]
    assert len(rows) == 1, f"expected one {etype}, got {len(rows)}: {rows}"
    attrs = rows[0]
    assert "offer_id" in attrs, f"missing offer_id: {attrs}"
    offer_id = int(attrs["offer_id"])  # supports both int and numeric string
    assert offer_id > 0, f"invalid offer_id: {offer_id} attrs={attrs}"
    return offer_id


def _sum_transfers(tx, addr):
    return sum_transfers_for_addr(tx, addr)


def test_parity_swap_then_take_vs_take_then_swap(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    maker_name = env["acc2"]["name"]

    # Create pool and offer
    pid = _create_pool(dysond, taker_name, a, b, ai=10, bi=10)
    offer_id = _make_offer(dysond, maker_name, have=f"10{a}", want=f"2{b}")

    # Route 1: swap then take
    pre1 = _bal_map(dysond, taker_addr)
    op1 = _swap_in_op(pid, denom_in=a, amount_in=5)
    op2 = _take_op(offer_id, units=1)
    tx1 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"100{a}",
        "--op",
        json.dumps(op1),
        "--op",
        json.dumps(op2),
        "--from",
        taker_name,
    )
    assert tx1.get("code", 1) == 0, f"route1 failed: {json.dumps(tx1, indent=2)}"
    d1, c1 = _sum_transfers(tx1, taker_addr)
    in1_a = sum([amt for (amt, den) in d1 if den == a])
    out1_a = sum([amt for (amt, den) in c1 if den == a])
    net1_a = in1_a - out1_a
    net1_b = sum([amt for (amt, den) in c1 if den == b]) - sum(
        [amt for (amt, den) in d1 if den == b]
    )
    post1 = _bal_map(dysond, taker_addr)

    # Route 2: take then swap
    pre2 = _bal_map(dysond, taker_addr)
    tx2 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"100{a}",
        "--op",
        json.dumps(_take_op(offer_id, units=1)),
        "--op",
        json.dumps(_swap_in_op(pid, denom_in=a, amount_in=5)),
        "--from",
        taker_name,
    )
    assert tx2.get("code", 1) == 0, f"route2 failed: {json.dumps(tx2, indent=2)}"
    d2, c2 = _sum_transfers(tx2, taker_addr)
    in2_a = sum([amt for (amt, den) in d2 if den == a])
    out2_a = sum([amt for (amt, den) in c2 if den == a])
    net2_a = in2_a - out2_a
    net2_b = sum([amt for (amt, den) in c2 if den == b]) - sum(
        [amt for (amt, den) in d2 if den == b]
    )
    post2 = _bal_map(dysond, taker_addr)

    # Per-route balance consistency with transfer-derived NET values
    assert (pre1.get(a, 0) - post1.get(a, 0)) == net1_a, "route1 A net debit mismatch"
    assert (post1.get(b, 0) - pre1.get(b, 0)) == net1_b, "route1 B net credit mismatch"
    assert (pre2.get(a, 0) - post2.get(a, 0)) == net2_a, "route2 A net debit mismatch"
    assert (post2.get(b, 0) - pre2.get(b, 0)) == net2_b, "route2 B net credit mismatch"
    # Parity: equal A debits and A credits across route orderings
    assert in1_a == in2_a, f"A debits differ: route1={in1_a} route2={in2_a}"
    assert out1_a == out2_a, f"A credits differ: route1={out1_a} route2={out2_a}"
