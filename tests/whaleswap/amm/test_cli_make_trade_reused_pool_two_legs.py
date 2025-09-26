import json

from tests.whaleswap.amm.parse_amounts_multi import sum_transfers_for_addr
from tests.whaleswap.amm.normalize_events import normalize_events


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr)
    assert isinstance(res, dict), f"bad balances response: {res}"
    assert "balances" in res, f"missing balances: {res}"
    out = {}
    for b in res["balances"]:
        assert "denom" in b and "amount" in b, f"bad row: {b}"
        out[b["denom"]] = int(b["amount"])
    return out


def test_make_trade_reused_pool_two_legs(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]

    # Create pool a/b with moderate reserves
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert (
        "code" in txp and txp["code"] == 0
    ), f"create-pool failed: {json.dumps(txp, indent=2)}"
    ev = normalize_events(txp["events"])  # deep-parsed
    et = "dysonprotocol.whaleswap.v1.EventPoolCreated"
    assert et in ev
    rows = ev[et]
    assert len(rows) == 1
    pid = (
        int(rows[0]["pool_id"])
        if isinstance(rows[0]["pool_id"], int)
        else int(json.loads(rows[0]["pool_id"]))
    )
    assert pid > 0

    # Two legs on the same pool: swap_in 5a then swap_in 5a
    pre = _bal_map(dysond, taker_addr)
    leg1 = {"swap": {"pool_id": pid, "swap_in": {"denom": a, "amount": "5"}}}
    leg2 = {"swap": {"pool_id": pid, "swap_in": {"denom": a, "amount": "5"}}}
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"10{a}",
        "--op",
        json.dumps(leg1),
        "--op",
        json.dumps(leg2),
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert (
        "code" in tx and tx["code"] == 0
    ), f"make-trade failed: {json.dumps(tx, indent=2)}"

    # Sum transfers for taker
    d, c = sum_transfers_for_addr(tx, taker_addr)
    deb_a = sum([amt for amt, den in d if den == a])
    cre_b = sum([amt for amt, den in c if den == b])
    assert deb_a == 10, f"taker A debit wrong: {deb_a}"

    post = _bal_map(dysond, taker_addr)
    assert a in pre and a in post and b in pre and b in post
    assert post[a] == pre[a] - 10, f"A delta wrong: pre={pre[a]} post={post[a]}"
    assert (
        post[b] == pre[b] + cre_b
    ), f"B delta wrong: pre={pre[b]} post={post[b]} credit={cre_b}"
