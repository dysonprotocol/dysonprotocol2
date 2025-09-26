import json


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr)
    return {b.get("denom"): int(b.get("amount")) for b in res.get("balances", [])}


def test_cli_metrics_liquid_backing_smoke(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    owner = env["owner_addr"]
    denoms = env["denoms"]
    ldenoms = env["liquid_denoms"]

    # Sanity: setup minted 900 liquid each and held 900 solid backing in module
    # Metrics should report escrowed_liquid_coins equal to 900 per base denom
    m = dysond("query", "whaleswap", "metrics")
    assert isinstance(m, dict), f"unexpected metrics shape: {json.dumps(m, indent=2)}"
    tm = m.get("metrics", {})
    elc = {
        c.get("denom"): int(c.get("amount"))
        for c in tm.get("escrowed_liquid_coins", [])
    }

    # Verify all base denoms present with 900 units backing
    for d in denoms:
        amt = elc.get(d, 0)
        assert (
            amt == 900
        ), f"expected 900 backing for {d}, got {amt}. Full: {json.dumps(m, indent=2)}"

    # Module balances must equal sum of components; spot-check one denom by reconstructing
    # expected = pools + offers + auctions + pfand + liquid_backing
    # Here right after setup: pools=0, offers=0, auctions=0, pfand=0, liquid_backing=900 per denom
    mod = dysond("query", "auth", "module-account", "whaleswap")
    maddr = mod.get("account", {}).get("value", {}).get("address")
    assert isinstance(maddr, str) and maddr.startswith(
        "dys"
    ), f"bad module account: {json.dumps(mod, indent=2)}"
    mb = _bal_map(dysond, maddr)
    for d in denoms:
        assert (
            mb.get(d, 0) >= 900
        ), f"module missing backing for {d}: {json.dumps(mb, indent=2)}"
    # Ensure module holds no liquid user balances after setup distribution
    for ld in ldenoms:
        assert (
            mb.get(ld, 0) == 0
        ), f"module should not hold liquid {ld}: {json.dumps(mb, indent=2)}"
