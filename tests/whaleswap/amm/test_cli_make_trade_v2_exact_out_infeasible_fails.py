import json
import pytest


def test_make_trade_v2_exact_out_infeasible_fails(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    a = env["denoms"][0]
    b = env["denoms"][1]
    taker_name = env["acc2"]["name"]

    # Create v2 pool a/b with 10/10 from acc2
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10{a}",
        "--coins",
        f"10{b}",
        "--from",
        taker_name,
    )
    assert txp.get("code", 1) == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"
    ev_pc = [
        e
        for e in txp.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    attrs = {a.get("key"): a.get("value") for a in ev_pc[0].get("attributes", [])}
    pid = int(json.loads(attrs["pool_id"]))

    # Request b out equal to reserve (10) to trigger exact-out equals/exceeds reserve
    op = {
        "swap": {
            "pool_id": pid,
            "swap_out": {"denom": b, "amount": "10"},
        }
    }
    with pytest.raises(Exception, match="exact-out equals/exceeds reserve"):
        dysond(
            "tx",
            "whaleswap",
            "make-trade",
            "--max-input",
            f"100000{a}",
            "--op",
            json.dumps(op),
            "--from",
            taker_name,
            "--gas",
            "auto",
        )
