import json


def test_route_two_pools(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [creator, creator_addr] = generate_account("amm_route_creator")
    faucet(creator_addr, amount=2_000_000)

    # Create two custom denoms and two pools: A/B and B/C
    denom_a = register_name(dysond, creator, creator_addr, "1000udys")
    denom_b = register_name(dysond, creator, creator_addr, "1000udys")
    denom_c = register_name(dysond, creator, creator_addr, "1000udys")

    # Pools: udys<->A first to bootstrap balances, then A<->B and B<->C
    p1 = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"1000{denom_a}",
        "--coins",
        f"1000{denom_b}",
        "--from",
        creator,
    )
    assert p1.get("code", 1) == 0, f"create-pool A/B failed: {json.dumps(p1, indent=2)}"
    ab_id = int(
        str(
            [
                a
                for e in p1["events"]
                if e["type"] == "dysonprotocol.whaleswap.v1.EventPoolCreated"
                for a in e["attributes"]
                if a["key"] == "pool_id"
            ][0]["value"]
        ).strip('"')
    )

    p2 = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"1000{denom_b}",
        "--coins",
        f"1000{denom_c}",
        "--from",
        creator,
    )
    assert p2.get("code", 1) == 0, f"create-pool B/C failed: {json.dumps(p2, indent=2)}"
    bc_id = int(
        str(
            [
                a
                for e in p2["events"]
                if e["type"] == "dysonprotocol.whaleswap.v1.EventPoolCreated"
                for a in e["attributes"]
                if a["key"] == "pool_id"
            ][0]["value"]
        ).strip('"')
    )

    [trader, trader_addr] = generate_account("amm_route_trader")
    faucet(trader_addr, amount=1_000_000)

    # Route: A->B via ab_id, then B->C via bc_id
    # Provide legs as multiple flags since CLI flag is singular
    leg1 = json.dumps(
        {"pool_id": ab_id, "swap_in": {"denom": denom_a, "amount": "100"}}
    )
    leg2 = json.dumps({"pool_id": bc_id, "swap_in": {"denom": denom_b, "amount": "50"}})
    tx = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--input",
        f"100{denom_a}",
        "--input",
        f"50{denom_b}",
        "--legs",
        leg1,
        "--legs",
        leg2,
        "--min-output",
        f"1{denom_c}",
        "--from",
        trader,
    )
    assert tx.get("code", 1) == 0, f"route failed: {json.dumps(tx, indent=2)}"
    outs = {c["denom"]: int(c["amount"]) for c in tx.get("amount_out", [])}
    assert outs.get(denom_c, 0) > 0, f"no C received: {json.dumps(tx, indent=2)}"
