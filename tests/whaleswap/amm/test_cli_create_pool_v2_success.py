import json


def test_create_pool_v2_success(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [creator_name, creator_addr] = generate_account("amm_creator")
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
        "--max-borrow-percent",
        "0.8",
        "--from",
        creator_name,
    )
    assert tx.get("code", 1) == 0, f"create-pool failed: {json.dumps(tx, indent=2)}"

    pool_events = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_events, f"EventPoolCreated not found in tx events: {tx}"
    attrs = pool_events[0].get("attributes", [])
    pool_id_attr = [a for a in attrs if a.get("key") == "pool_id"]
    assert pool_id_attr, f"pool_id attribute missing in EventPoolCreated: {pool_events}"
    pool_id_raw = pool_id_attr[0].get("value")
    pool_id = int(str(pool_id_raw).strip('"'))

    q = dysond("query", "whaleswap", "pool", "--pool-id", str(pool_id))
    pool = q.get("pool")
    assert pool, f"pool not found: {q}"
    coins = pool.get("coins", [])
    assert isinstance(coins, list) and len(coins) == 2, f"invalid coins shape: {pool}"
    assert coins[0]["denom"] < coins[1]["denom"], f"denom order not canonical: {pool}"
    assert pool["shares_denom"].startswith(
        "whaleswap.dys/pools/"
    ), f"invalid shares denom: {pool['shares_denom']}"
