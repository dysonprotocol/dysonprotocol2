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


def test_make_trade_mixed_swap_then_take(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [creator, creator_addr] = generate_account("maketrade_creator")
    faucet(creator_addr, amount=2_000_000)

    # Setup: pool udys/foo and offer (maker wants udys, gives foo)
    foo = register_name(dysond, creator, creator_addr, "1000udys")
    bar = "udys"
    _mint(dysond, creator, foo, 500)

    # Create pool udys/foo
    txp = dysond(
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
    assert txp.get("code", 1) == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"
    evs = [
        e
        for e in txp.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pid = int(
        str(
            [a for a in evs[0].get("attributes", []) if a.get("key") == "pool_id"][0][
                "value"
            ]
        ).strip('"')
    )

    # Create maker offer: have=20foo want=10bar
    [maker, maker_addr] = generate_account("maker")
    faucet(maker_addr, amount=1_000_000)
    # Top up creator with extra foo then send 20foo to maker (only name owner can mint)
    _mint(dysond, creator, foo, 50)
    send = dysond(
        "tx",
        "bank",
        "send",
        creator,
        maker_addr,
        f"20{foo}",
        "--from",
        creator,
    )
    assert (
        send.get("code", 1) == 0
    ), f"send foo to maker failed: {json.dumps(send, indent=2)}"
    make = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"20{foo}",
        "--want",
        f"10{bar}",
        "--from",
        maker,
    )
    assert make.get("code", 1) == 0, f"make-offer failed: {json.dumps(make, indent=2)}"
    evm = [
        e
        for e in make.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    offer_id = int(
        str(
            [a for a in evm[0].get("attributes", []) if a.get("key") == "offer_id"][0][
                "value"
            ]
        ).strip('"')
    )

    # Trader executes: swap 100udys->foo, then take 5 units (half offer)
    [trader, trader_addr] = generate_account("maketrade_trader")
    faucet(trader_addr, amount=1_000_000)

    op1 = json.dumps(
        {"swap": {"pool_id": pid, "swap_in": {"denom": "udys", "amount": "100"}}}
    )
    op2 = json.dumps({"take": {"offer_id": offer_id, "take_units": "5"}})

    # Pre-snapshot balances for assertions
    bal_before = dysond("query", "bank", "balances", trader_addr)
    by_before = {
        b.get("denom"): int(b.get("amount")) for b in bal_before.get("balances", [])
    }
    foo_before = by_before.get(foo, 0)
    # bar_before not required since want is udys

    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "500udys",
        "--op",
        op1,
        "--op",
        op2,
        "--min-output",
        f"1{foo}",
        "--from",
        trader,
    )
    assert tx.get("code", 1) == 0, f"make-trade failed: {json.dumps(tx, indent=2)}"
    # At least one EventTradeRecorded emitted
    evs_tr = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert evs_tr, f"no trade events: {json.dumps(tx, indent=2)}"

    # Post balances: trader should have more foo (from swap) and paid udys for take
    bal_after = dysond("query", "bank", "balances", trader_addr)
    by_after = {
        b.get("denom"): int(b.get("amount")) for b in bal_after.get("balances", [])
    }
    assert (
        by_after.get(foo, 0) > foo_before
    ), f"no foo increase: before={foo_before} after={by_after.get(foo,0)} tx={json.dumps(tx, indent=2)}"
    # no assertion on udys balance
