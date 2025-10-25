import json

from tests.whaleswap.amm.parse_amounts_multi import sum_transfers_for_addr


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr)
    assert isinstance(res, dict), f"bad balances response: {res}"
    assert "balances" in res, f"missing balances: {res}"
    out = {}
    for b in res["balances"]:
        assert "denom" in b and "amount" in b, f"bad row: {b}"
        out[b["denom"]] = int(b["amount"])
    return out


def _take(offer_id, units):
    return {"take": {"offer_id": offer_id, "take_units": str(units)}}


def test_make_trade_netting_two_takes_no_debit(chainnet, ws_setup_env, ws_create_offer):
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    maker1 = env["acc2"]["name"]
    maker2 = env["acc3"]["name"]

    # Two complementary offers: maker1 A->B, maker2 B->A (balanced units)
    offer1 = ws_create_offer(maker1, have=f"10{a}", want=f"5{b}")
    offer2 = ws_create_offer(maker2, have=f"10{b}", want=f"5{a}")

    # Single MakeTrade: take 1 unit from each offer
    pre = _bal_map(dysond, taker_addr)
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "100udys",
        "--op",
        json.dumps(_take(offer1, 1)),
        "--op",
        json.dumps(_take(offer2, 1)),
        "--from",
        taker_name,
    )
    assert tx.get("code", 1) == 0, f"make-trade failed: {json.dumps(tx, indent=2)}"

    # Expect profit-only route: no debits on A/B, credits equal unit net (1 each)
    debits, credits = sum_transfers_for_addr(tx, taker_addr)
    in_a = sum([amt for (amt, den) in debits if den == a])
    out_a = sum([amt for (amt, den) in credits if den == a])
    in_b = sum([amt for (amt, den) in debits if den == b])
    out_b = sum([amt for (amt, den) in credits if den == b])
    assert in_a == 0, f"unexpected A debit: {in_a} tx={json.dumps(tx, indent=2)}"
    assert in_b == 0, f"unexpected B debit: {in_b} tx={json.dumps(tx, indent=2)}"
    assert out_a == 1, f"unexpected A credit: {out_a} tx={json.dumps(tx, indent=2)}"
    assert out_b == 1, f"unexpected B credit: {out_b} tx={json.dumps(tx, indent=2)}"

    post = _bal_map(dysond, taker_addr)
    assert (
        a in pre and a in post
    ), f"missing denom a in balances: pre={pre}, post={post}"
    assert (
        b in pre and b in post
    ), f"missing denom b in balances: pre={pre}, post={post}"
    assert post[a] == pre[a] + 1, f"A balance wrong: pre={pre[a]} post={post[a]}"
    assert post[b] == pre[b] + 1, f"B balance wrong: pre={pre[b]} post={post[b]}"
