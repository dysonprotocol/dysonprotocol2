import json


def _create_pool(dysond, creator, c1, c2):
    # Ensure creator has supply of both custom denoms
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 1000
    required_fee = int(units * fee_per_unit)
    m1 = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{c1}",
        "--mint-fee",
        f"{required_fee}udys",
        "--from",
        creator,
    )
    assert m1.get("code", 1) == 0, json.dumps(m1, indent=2)
    m2 = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{c2}",
        "--mint-fee",
        f"{required_fee}udys",
        "--from",
        creator,
    )
    assert m2.get("code", 1) == 0, json.dumps(m2, indent=2)
    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"1000{c1}",
        "--coins",
        f"1000{c2}",
        "--from",
        creator,
    )
    assert tx.get("code", 1) == 0, json.dumps(tx, indent=2)
    pid = int(
        str(
            [
                a
                for e in tx["events"]
                if e["type"] == "dysonprotocol.whaleswap.v1.EventPoolCreated"
                for a in e["attributes"]
                if a["key"] == "pool_id"
            ][0]["value"]
        ).strip('"')
    )
    return pid


def test_cap_enforced(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [creator, creator_addr] = generate_account("amm_cap_creator")
    faucet(creator_addr, amount=2_000_000)
    a = register_name(dysond, creator, creator_addr, "1000udys")
    b = register_name(dysond, creator, creator_addr, "1000udys")
    pid = _create_pool(dysond, creator, a, b)

    [trader, trader_addr] = generate_account("amm_cap_trader")
    faucet(trader_addr, amount=1_000_000)

    leg = json.dumps({"pool_id": pid, "swap_in": {"denom": a, "amount": "101"}})
    tx = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        f"100{a}",
        "--legs",
        leg,
        "--min-output",
        f"1{b}",
        "--from",
        trader,
    )
    assert tx.get("code", 0) != 0, f"expected cap failure: {json.dumps(tx, indent=2)}"


def test_min_output_enforced(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [creator, creator_addr] = generate_account("amm_min_creator")
    faucet(creator_addr, amount=2_000_000)
    a = register_name(dysond, creator, creator_addr, "1000udys")
    b = register_name(dysond, creator, creator_addr, "1000udys")
    pid = _create_pool(dysond, creator, a, b)

    [trader, trader_addr] = generate_account("amm_min_trader")
    faucet(trader_addr, amount=1_000_000)

    leg = json.dumps({"pool_id": pid, "swap_in": {"denom": a, "amount": "10"}})
    tx = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        f"10{a}",
        "--legs",
        leg,
        "--min-output",
        f"1000000{b}",
        "--from",
        trader,
    )
    assert (
        tx.get("code", 0) != 0
    ), f"expected min-output failure: {json.dumps(tx, indent=2)}"
