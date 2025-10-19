import json


def test_pool_swap_v2_single_pool(chainnet, generate_account, faucet, register_name):
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
        "--from",
        creator_name,
    )
    assert tx.get("code", 1) == 0, f"create-pool failed: {json.dumps(tx, indent=2)}"
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert evs, f"EventPoolCreated not found: {tx}"
    attrs = evs[0].get("attributes", [])
    pid_attr = [a for a in attrs if a.get("key") == "pool_id"]
    pool_id = int(str(pid_attr[0].get("value")).strip('"'))

    [trader_name, trader_addr] = generate_account("amm_trader")
    faucet(trader_addr, amount=1_000_000)

    legs = json.dumps(
        {"pool_id": pool_id, "swap_in": {"denom": "udys", "amount": "100"}}
    )
    swap = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        "100udys",
        "--legs",
        legs,
        "--min-output",
        f"1{name}",
        "--from",
        trader_name,
    )
    assert swap.get("code", 1) == 0, f"swap failed: {json.dumps(swap, indent=2)}"

    after = dysond("query", "whaleswap", "pool", "--pool-id", str(pool_id))["pool"]
    assert int(after["num_trades"]) >= 1, f"num_trades not incremented: {after}"
    # coins is an array in canonical order; find reserves by denom
    coins = after["coins"]
    udys = [c for c in coins if c["denom"] == "udys"][0]
    other = [c for c in coins if c["denom"] == name][0]
    r1 = int(udys["amount"])
    r2 = int(other["amount"])
    assert (
        r1 > 0 and r2 > 0
    ), f"reserves not positive after swap: {json.dumps(after, indent=2)}"
