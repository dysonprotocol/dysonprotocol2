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
    ldenoms = env["liquid_denoms"]

    for addr in [a1, a2, a3]:
        bm = _bal_map(dysond, addr)
        for d in denoms:
            assert (
                bm.get(d, 0) == 20  # Always assert exact amounts
            ), f"missing 20 solid of {d} for {addr}: {json.dumps(bm, indent=2)}"
        for ld in ldenoms:
            assert (
                bm.get(ld, 0) == 20  # Always assert exact amounts
            ), f"missing 20 liquid of {ld} for {addr}: {json.dumps(bm, indent=2)}"
