import json

from tests.whaleswap.amm.normalize_events import normalize_events
from tests.whaleswap.amm.parse_amounts_multi import sum_transfers_for_addr


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr)
    assert isinstance(res, dict) and "balances" in res, f"bad balances: {res}"
    out = {}
    for b in res["balances"]:
        assert "denom" in b and "amount" in b
        out[b["denom"]] = int(b["amount"])
    return out


def test_cli_make_trade_caps_duplicate_normalization_pass(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]

    # Create pool
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"20{a}",
        "--coins",
        f"20{b}",
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert (
        "code" in txp and txp["code"] == 0
    ), f"create-pool failed: {json.dumps(txp, indent=2)}"
    assert "events" in txp
    ev = normalize_events(txp["events"])  # deep-parsed
    et = "dysonprotocol.whaleswap.v1.EventPoolCreated"
    assert et in ev
    rows = ev[et]
    assert len(rows) == 1
    pid = int(str(rows[0]["pool_id"]))
    assert pid > 0

    pre = _bal_map(dysond, taker_addr)
    op = {"swap": {"pool_id": pid, "swap_in": {"denom": a, "amount": "10"}}}
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"11{a}",
        "--op",
        json.dumps(op),
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert (
        "code" in tx and tx["code"] == 0
    ), f"make-trade failed: {json.dumps(tx, indent=2)}"

    # Transfer-derived exact amounts
    debits, credits = sum_transfers_for_addr(tx, taker_addr)
    in_a = sum([amt for (amt, den) in debits if den == a])
    out_b = sum([amt for (amt, den) in credits if den == b])

    post = _bal_map(dysond, taker_addr)
    assert a in pre and a in post and b in pre and b in post
    assert pre[a] - post[a] == in_a == 10
    assert post[b] - pre[b] == out_b
