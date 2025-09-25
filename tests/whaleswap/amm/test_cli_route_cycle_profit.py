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


def _create_pool(dysond, owner, denom_x, amt_x, denom_y, amt_y):
    _mint(dysond, owner, denom_x, amt_x)
    _mint(dysond, owner, denom_y, amt_y)
    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"{amt_x}{denom_x}",
        "--coins",
        f"{amt_y}{denom_y}",
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


def test_route_cycle_profit_no_inputs(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]

    # Creator and trader
    [creator, creator_addr] = generate_account("cycle_creator")
    faucet(creator_addr, amount=2_000_000)
    [trader, trader_addr] = generate_account("cycle_trader")
    faucet(trader_addr, amount=1_000_000)

    # Three custom denoms A, B, C
    A = register_name(dysond, creator, creator_addr, "1000udys")
    B = register_name(dysond, creator, creator_addr, "1000udys")
    C = register_name(dysond, creator, creator_addr, "1000udys")

    # Skewed pools to bias each edge favorably
    # AB: small A, large B
    ab_id = _create_pool(dysond, creator, A, 100, B, 100000)
    # BC: small B, large C
    bc_id = _create_pool(dysond, creator, B, 100, C, 100000)
    # CA: small C, very large A
    ca_id = _create_pool(dysond, creator, C, 100, A, 110000)

    # Record trader balances before
    before = dysond("query", "bank", "balances", trader_addr)
    bal_before = {
        b.get("denom"): int(b.get("amount")) for b in before.get("balances", [])
    }
    a0 = bal_before.get(A, 0)
    b0 = bal_before.get(B, 0)
    c0 = bal_before.get(C, 0)

    # Legs for circular route; no inputs provided
    leg_ab = json.dumps({"pool_id": ab_id, "swap_in": {"denom": A, "amount": "10"}})
    leg_bc = json.dumps({"pool_id": bc_id, "swap_in": {"denom": B, "amount": "10"}})
    leg_ca = json.dumps({"pool_id": ca_id, "swap_in": {"denom": C, "amount": "10"}})

    tx = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--legs",
        leg_ab,
        "--legs",
        leg_bc,
        "--legs",
        leg_ca,
        "--min-output",
        f"1{A}",
        "--from",
        trader,
    )
    assert tx.get("code", 1) == 0, f"cycle swap failed: {json.dumps(tx, indent=2)}"

    # Expect at least 3 trades recorded
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert len(evs) >= 3, f"expected >=3 trades: {json.dumps(tx, indent=2)}"

    # No trader debits: ensure no coin_spent by trader address
    spent = [e for e in tx.get("events", []) if e.get("type") == "coin_spent"]
    trader_spent = [
        attrs.get("amount", "")
        for e in spent
        for attrs in [{a.get("key"): a.get("value") for a in e.get("attributes", [])}]
        if attrs.get("spender") == trader_addr
    ]
    assert (
        not trader_spent
    ), f"unexpected trader debits: {trader_spent}\n{json.dumps(tx, indent=2)}"

    # Balances after: at least one profit; specifically A should increase due to --min-output 1A
    after = dysond("query", "bank", "balances", trader_addr)
    bal_after = {
        b.get("denom"): int(b.get("amount")) for b in after.get("balances", [])
    }
    a1 = bal_after.get(A, 0)
    b1 = bal_after.get(B, 0)
    c1 = bal_after.get(C, 0)

    assert (
        a1 > a0
    ), f"no profit in A: before={a0} after={a1} tx={json.dumps(tx, indent=2)}"
    # Optional: ensure no denom decreased
    assert b1 >= b0 and c1 >= c0, f"unexpected debits: B {b0}->{b1}, C {c0}->{c1}"
