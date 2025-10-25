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


def test_make_trade_two_makers_multi_take_single_settlement(
    chainnet, ws_setup_env, ws_create_offer
):
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    m1_name = env["acc2"]["name"]
    m1_addr = env["acc2"]["addr"]
    m2_name = env["acc3"]["name"]
    m2_addr = env["acc3"]["addr"]

    # Two offers with different unit sizes; take one unit from each
    # Offer1: 10a have, 2b want -> unit 5a / 1b
    # Offer2: 20a have, 2b want -> unit 10a / 1b
    o1 = ws_create_offer(m1_name, have=f"10{a}", want=f"2{b}")
    o2 = ws_create_offer(m2_name, have=f"20{a}", want=f"2{b}")

    pre_taker = _bal_map(dysond, taker_addr)
    pre_m1 = _bal_map(dysond, m1_addr)
    pre_m2 = _bal_map(dysond, m2_addr)

    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "100udys",
        "--max-input",
        f"2{b}",
        "--op",
        json.dumps(_take(o1, 1)),
        "--op",
        json.dumps(_take(o2, 1)),
        "--from",
        taker_name,
    )
    assert isinstance(tx, dict), f"bad tx result: {tx}"
    assert "code" in tx and tx["code"] == 0, f"tx failed: {json.dumps(tx, indent=2)}"

    # Taker net: debit 2b, credit 15a
    d_t, c_t = sum_transfers_for_addr(tx, taker_addr)
    deb_b = sum([amt for amt, den in d_t if den == b])
    cre_a = sum([amt for amt, den in c_t if den == a])
    assert deb_b == 2, f"taker B debit wrong: {deb_b} events={d_t}"
    assert cre_a == 15, f"taker A credit wrong: {cre_a} events={c_t}"

    post_taker = _bal_map(dysond, taker_addr)
    assert a in pre_taker and a in post_taker
    assert b in pre_taker and b in post_taker
    assert (
        post_taker[a] == pre_taker[a] + 15
    ), f"taker A wrong: pre={pre_taker[a]} post={post_taker[a]}"
    assert (
        post_taker[b] == pre_taker[b] - 2
    ), f"taker B wrong: pre={pre_taker[b]} post={post_taker[b]}"

    # Maker1 receives 1b
    d_m1, c_m1 = sum_transfers_for_addr(tx, m1_addr)
    cre_m1_b = sum([amt for amt, den in c_m1 if den == b])
    assert cre_m1_b == 1, f"maker1 B credit wrong: {cre_m1_b}"
    post_m1 = _bal_map(dysond, m1_addr)
    assert b in pre_m1 and b in post_m1
    assert (
        post_m1[b] == pre_m1[b] + 1
    ), f"maker1 B wrong: pre={pre_m1[b]} post={post_m1[b]}"

    # Maker2 receives 1b
    d_m2, c_m2 = sum_transfers_for_addr(tx, m2_addr)
    cre_m2_b = sum([amt for amt, den in c_m2 if den == b])
    assert cre_m2_b == 1, f"maker2 B credit wrong: {cre_m2_b}"
    post_m2 = _bal_map(dysond, m2_addr)
    assert b in pre_m2 and b in post_m2
    assert (
        post_m2[b] == pre_m2[b] + 1
    ), f"maker2 B wrong: pre={pre_m2[b]} post={post_m2[b]}"
