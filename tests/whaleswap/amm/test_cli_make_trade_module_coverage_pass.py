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


def test_make_trade_module_coverage_pass(chainnet, ws_setup_env, ws_create_offer):
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    maker = env["acc2"]["name"]
    drain_rcpt = env["acc3"]["addr"]

    # Move all solid B out and leave exactly 90 B with taker
    txd1 = dysond(
        "tx",
        "bank",
        "send",
        taker_name,
        drain_rcpt,
        f"210{b}",
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert txd1.get("code", 1) == 0, f"drain part1 failed: {json.dumps(txd1, indent=2)}"

    # Maker wants large B that taker will not cover; module must cover (per-unit 90)
    offer = ws_create_offer(maker, have=f"10{a}", want=f"900{b}")

    pre_taker = _bal_map(dysond, taker_addr)
    pre_maker = _bal_map(dysond, env["acc2"]["addr"])

    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "100udys",
        "--max-input",
        f"90{b}",
        "--op",
        json.dumps(_take(offer, 1)),
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert tx.get("code", 1) == 0, f"make-trade failed: {json.dumps(tx, indent=2)}"

    debits, credits = sum_transfers_for_addr(tx, taker_addr)
    in_b = sum([amt for (amt, den) in debits if den == b])
    out_b = sum([amt for (amt, den) in credits if den == b])
    out_a = sum([amt for (amt, den) in credits if den == a])
    assert in_b == 90, f"taker B debit mismatch: {in_b} tx={json.dumps(tx, indent=2)}"
    assert (
        out_b == 0
    ), f"taker credited B unexpectedly: {out_b} tx={json.dumps(tx, indent=2)}"
    assert (
        out_a == 1
    ), f"taker did not receive A have: got {out_a} tx={json.dumps(tx, indent=2)}"

    post_taker = _bal_map(dysond, taker_addr)
    post_maker = _bal_map(dysond, env["acc2"]["addr"])
    assert (
        a in pre_taker and a in post_taker
    ), f"missing denom a: pre={pre_taker} post={post_taker}"
    # After draining 210B, taker has exactly 90B pre-trade; post-trade, taker has no B
    assert (
        b in pre_taker and pre_taker[b] == 90
    ), f"pre B balance wrong: pre={pre_taker}"
    assert b not in post_taker, f"post B should be absent: post={post_taker}"
    assert b in pre_maker and b in post_maker
    assert (
        post_taker[a] == pre_taker[a] + 1
    ), f"taker A wrong: pre={pre_taker[a]} post={post_taker[a]}"
    assert (
        post_maker[b] == pre_maker[b] + 90
    ), f"maker B wrong: pre={pre_maker[b]} post={post_maker[b]}"
