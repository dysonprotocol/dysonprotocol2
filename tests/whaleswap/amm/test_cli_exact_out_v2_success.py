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


def test_exact_out_v2_success(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [creator, creator_addr] = generate_account("amm_exact_out_creator")
    faucet(creator_addr, amount=2_000_000)

    # Create custom denom and pool (constant product)
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
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
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

    [trader, trader_addr] = generate_account("amm_exact_out_trader")
    faucet(trader_addr, amount=1_000_000)

    # Before balance (foo)
    bal_before = dysond("query", "bank", "balances", trader_addr)
    by_before = {
        b.get("denom"): int(b.get("amount")) for b in bal_before.get("balances", [])
    }
    foo_before = by_before.get(foo, 0)

    # Exact-out leg: request 10 foo, pay in udys automatically computed; cap udys generously
    leg = json.dumps({"pool_id": pid, "swap_out": {"denom": foo, "amount": "10"}})
    tx2 = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        "1000udys",
        "--legs",
        leg,
        "--min-output",
        f"10{foo}",
        "--from",
        trader,
    )
    assert (
        tx2.get("code", 1) == 0
    ), f"exact-out swap failed: {json.dumps(tx2, indent=2)}"

    # Validate via events and balances
    evs2 = [
        e
        for e in tx2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert evs2, f"expected trade recorded: {json.dumps(tx2, indent=2)}"
    bal_after = dysond("query", "bank", "balances", trader_addr)
    by_after = {
        b.get("denom"): int(b.get("amount")) for b in bal_after.get("balances", [])
    }
    foo_after = by_after.get(foo, 0)
    assert (
        foo_after - foo_before >= 10
    ), f"foo did not increase by >=10: before={foo_before} after={foo_after} tx={json.dumps(tx2, indent=2)}"
