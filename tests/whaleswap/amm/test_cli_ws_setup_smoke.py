import json


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr)
    return {b.get("denom"): int(b.get("amount")) for b in res.get("balances", [])}


def test_ws_setup_env_balances(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a1 = env["acc1"]["addr"]
    a2 = env["acc2"]["addr"]
    a3 = env["acc3"]["addr"]

    denoms = env["denoms"]
    # liquid denoms removed in settlement-mode rewrite

    for addr in [a1, a2, a3]:
        bm = _bal_map(dysond, addr)
        for d in denoms:
            assert (
                bm.get(d, 0) == 300
            ), f"missing 300 base of {d} for {addr}: {json.dumps(bm, indent=2)}"
