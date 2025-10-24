import json


def _bal_map(dysond, addr):
    res = dysond("query", "bank", "balances", addr, "--page-limit", "1000")
    return {b.get("denom"): int(b.get("amount")) for b in res.get("balances", [])}


def test_cli_metrics_post_setup_smoke(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    denoms = env["denoms"]

    # Right after setup: pools=0, offers=0, auctions=0, pfand=0
    # Module account should not unexpectedly hold user base balances
    mod = dysond("query", "auth", "module-account", "whaleswap")
    maddr = mod.get("account", {}).get("value", {}).get("address")
    assert isinstance(maddr, str) and maddr.startswith(
        "dys"
    ), f"bad module account: {json.dumps(mod, indent=2)}"
    mb = _bal_map(dysond, maddr)
    # Allow zero or small dust; assert no large unexpected holdings
    for d in denoms:
        assert (
            mb.get(d, 0) <= 5
        ), f"module should not hold {d} after setup: {json.dumps(mb, indent=2)}"
