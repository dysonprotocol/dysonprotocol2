import json


def _mint(dysond, owner, denom, units):
    params = dysond("query", "nameservice", "params")
    from decimal import Decimal, ROUND_CEILING

    fee_per = Decimal(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    fee = int((Decimal(units) * fee_per).to_integral_value(rounding=ROUND_CEILING))
    res = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{denom}",
        "--mint-fee",
        f"{fee}udys",
        "--from",
        owner,
    )
    assert res.get("code", 1) == 0, f"mint failed: {json.dumps(res, indent=2)}"


def _create_pool_udys_custom(dysond, owner, custom, amt_udys: int, amt_custom: int):
    _mint(dysond, owner, custom, amt_custom)
    a = "udys"
    b = custom
    amt_a = amt_udys
    amt_b = amt_custom
    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"{amt_a}{a}",
        "--coins",
        f"{amt_b}{b}",
        "--from",
        owner,
    )
    assert tx.get("code", 1) == 0, f"create-pool failed: {json.dumps(tx, indent=2)}"
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pid = int(
        str(
            [a for a in evs[0].get("attributes", []) if a.get("key") == "pool_id"][0][
                "value"
            ]
        ).strip('"')
    )
    return pid


def _create_pool_custom_custom(dysond, owner, a, b, amt_a: int, amt_b: int):
    _mint(dysond, owner, a, amt_a)
    _mint(dysond, owner, b, amt_b)
    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"{amt_a}{a}",
        "--coins",
        f"{amt_b}{b}",
        "--from",
        owner,
    )
    assert tx.get("code", 1) == 0, f"create-pool failed: {json.dumps(tx, indent=2)}"
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pid = int(
        str(
            [a for a in evs[0].get("attributes", []) if a.get("key") == "pool_id"][0][
                "value"
            ]
        ).strip('"')
    )
    return pid


def test_route_two_leg_across_two_pools(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [creator, creator_addr] = generate_account("route2_creator")
    faucet(creator_addr, amount=2_000_000)

    # Denoms
    b = register_name(dysond, creator, creator_addr, "1000udys")
    c = register_name(dysond, creator, creator_addr, "1000udys")

    # Pools: udys/b and b/c
    p1 = _create_pool_udys_custom(dysond, creator, b, 1000, 500)
    p2 = _create_pool_custom_custom(dysond, creator, b, c, 500, 300)

    [trader, trader_addr] = generate_account("route2_trader")
    faucet(trader_addr, amount=1_000_000)

    leg1 = json.dumps({"pool_id": p1, "swap_in": {"denom": "udys", "amount": "150"}})
    leg2 = json.dumps({"pool_id": p2, "swap_in": {"denom": b, "amount": "50"}})
    # Balance before (denom c)
    bal_before = dysond("query", "bank", "balances", trader_addr)
    by_before = {
        b.get("denom"): int(b.get("amount")) for b in bal_before.get("balances", [])
    }
    c_before = by_before.get(c, 0)

    tx = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--input",
        "200udys",
        "--input",
        f"200{b}",
        "--legs",
        leg1,
        "--legs",
        leg2,
        "--min-output",
        f"1{c}",
        "--from",
        trader,
    )
    assert tx.get("code", 1) == 0, f"route two-leg failed: {json.dumps(tx, indent=2)}"

    # Validate by events and bank balance
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        len(evs) >= 2
    ), f"expected at least 2 trades recorded: {json.dumps(tx, indent=2)}"

    bal_after = dysond("query", "bank", "balances", trader_addr)
    by_after = {
        b.get("denom"): int(b.get("amount")) for b in bal_after.get("balances", [])
    }
    c_after = by_after.get(c, 0)
    assert (
        c_after > c_before
    ), f"no {c} received: before={c_before} after={c_after} tx={json.dumps(tx, indent=2)}"

    # Each pool should record at least one trade
    q1 = dysond("query", "whaleswap", "trades-by-pool", str(p1), "--page-limit", "1")
    q2 = dysond("query", "whaleswap", "trades-by-pool", str(p2), "--page-limit", "1")
    assert q1.get(
        "trades", []
    ), f"no trades found for pool1: {json.dumps(q1, indent=2)}"
    assert q2.get(
        "trades", []
    ), f"no trades found for pool2: {json.dumps(q2, indent=2)}"
