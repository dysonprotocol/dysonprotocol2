import json


def test_update_pool_config_owner_only(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [creator_name, creator_addr] = generate_account("amm_owner")
    faucet(creator_addr, amount=2_000_000)

    name = register_name(dysond, creator_name, creator_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 1000
    required_fee = int(units * fee_per_unit)
    mint = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{name}",
        "--mint-fee",
        f"{required_fee}udys",
        "--from",
        creator_name,
    )
    assert mint.get("code", 1) == 0, f"mint-coins failed: {json.dumps(mint, indent=2)}"

    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        "1000udys",
        "--coins",
        f"500{name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        creator_name,
    )
    assert tx.get("code", 1) == 0, f"create-pool failed: {json.dumps(tx, indent=2)}"
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pool_attrs = evs[0].get("attributes", [])
    pool_id = int(
        str([a for a in pool_attrs if a.get("key") == "pool_id"][0]["value"]).strip('"')
    )

    # Canonicalize denoms to match keeper's Sort() behavior
    base, quote = sorted(["udys", name])

    [stranger_name, stranger_addr] = generate_account("amm_stranger")
    faucet(stranger_addr, amount=500_000)
    bad = dysond(
        "tx",
        "whaleswap",
        "update-pool-config",
        "--pool-id",
        str(pool_id),
        "--fee-pct",
        "0.001",
        "--from",
        stranger_name,
    )
    assert (
        bad.get("code", 0) != 0
    ), f"expected owner-only failure: {json.dumps(bad, indent=2)}"

    ok = dysond(
        "tx",
        "whaleswap",
        "update-pool-config",
        "--pool-id",
        str(pool_id),
        "--fee-pct",
        "0.002",
        "--min-price",
        f"3{base}",
        "--min-price",
        f"1{quote}",
        "--max-price",
        f"1{base}",
        "--max-price",
        f"3{quote}",
        "--from",
        creator_name,
    )
    assert ok.get("code", 1) == 0, f"owner update failed: {json.dumps(ok, indent=2)}"
