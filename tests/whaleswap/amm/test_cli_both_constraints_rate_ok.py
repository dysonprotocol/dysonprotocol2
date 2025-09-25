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


def test_both_constraints_rate_ok(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [creator, creator_addr] = generate_account("amm_both_creator")
    faucet(creator_addr, amount=2_000_000)

    foo = register_name(dysond, creator, creator_addr, "1000udys")
    _mint(dysond, creator, foo, 500)
    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        "1000udys",
        "--coins",
        f"500{foo}",
        "--from",
        creator,
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

    [trader, trader_addr] = generate_account("amm_both_trader")
    faucet(trader_addr, amount=1_000_000)

    # Both constraints: ask that out >= 5foo for 100udys in
    leg = json.dumps(
        {
            "pool_id": pid,
            "swap_in": {"denom": "udys", "amount": "100"},
            "swap_out": {"denom": foo, "amount": "5"},
        }
    )
    tx2 = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        "100udys",
        "--legs",
        leg,
        "--min-output",
        f"5{foo}",
        "--from",
        trader,
    )
    assert (
        tx2.get("code", 1) == 0
    ), f"both-constraints swap failed: {json.dumps(tx2, indent=2)}"
    evs2 = [
        e
        for e in tx2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert evs2, f"expected trade recorded: {json.dumps(tx2, indent=2)}"
