import json


def test_route_two_pools(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [creator, creator_addr] = generate_account("amm_route_creator")
    faucet(creator_addr, amount=2_000_000)

    # Create two custom denoms and two pools: A/B and B/C
    denom_a = register_name(dysond, creator, creator_addr, "1000udys")
    denom_b = register_name(dysond, creator, creator_addr, "1000udys")
    denom_c = register_name(dysond, creator, creator_addr, "1000udys")

    # Mint enough supply for creator to fund both pools
    params = dysond("query", "nameservice", "params")
    from decimal import Decimal, ROUND_CEILING

    fee_per = Decimal(params["params"]["mint_fee_per_coin"])  # e.g., 0.01

    def _mint(denom: str, units: int):
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
            creator,
        )
        assert res.get("code", 1) == 0, f"mint failed: {json.dumps(res, indent=2)}"

    _mint(denom_a, 1000)
    _mint(denom_b, 2000)  # needed for A/B and B/C pools
    _mint(denom_c, 1000)

    # Pools: A/B then B/C
    p1 = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"1000{denom_a}",
        "--coins",
        f"1000{denom_b}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
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
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
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

    # Top-up creator balances post pool-creation to fund trader
    _mint(denom_a, 200)
    _mint(denom_b, 200)

    # Fund trader with required custom denoms via bank send from creator
    send_a = dysond(
        "tx",
        "bank",
        "send",
        creator,
        trader_addr,
        f"100{denom_a}",
        "--from",
        creator,
    )
    assert (
        send_a.get("code", 1) == 0
    ), f"send A->trader failed: {json.dumps(send_a, indent=2)}"
    send_b = dysond(
        "tx",
        "bank",
        "send",
        creator,
        trader_addr,
        f"50{denom_b}",
        "--from",
        creator,
    )
    assert (
        send_b.get("code", 1) == 0
    ), f"send B->trader failed: {json.dumps(send_b, indent=2)}"

    # Route: A->B via ab_id, then B->C via bc_id
    # Provide operations as multiple --op flags
    op1 = json.dumps(
        {"swap": {"pool_id": ab_id, "swap_in": {"denom": denom_a, "amount": "100"}}}
    )
    op2 = json.dumps({"swap": {"pool_id": bc_id, "swap_in": {"denom": denom_b, "amount": "50"}}})
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"100{denom_a}",
        "--max-input",
        f"50{denom_b}",
        "--op",
        op1,
        "--op",
        op2,
        "--min-output",
        f"1{denom_c}",
        "--from",
        trader,
    )
    assert tx.get("code", 1) == 0, f"route failed: {json.dumps(tx, indent=2)}"
    # Validate via events and balances (response fields are opaque)
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    # Now expect 1 Trade with 2 operations (2 legs)
    assert len(evs) == 1, f"expected 1 EventTradeRecorded: {json.dumps(tx, indent=2)}"
    bal_after = dysond("query", "bank", "balances", trader_addr)
    by_after = {
        b.get("denom"): int(b.get("amount")) for b in bal_after.get("balances", [])
    }
    assert (
        by_after.get(denom_c, 0) > 0
    ), f"no {denom_c} received: after={json.dumps(bal_after, indent=2)} tx={json.dumps(tx, indent=2)}"
