import json


def test_partial_fill_exact_units(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [maker_name, maker_addr] = generate_account("ob_pf_maker")
    faucet(maker_addr, amount=2_000_000)
    [taker_name, taker_addr] = generate_account("ob_pf_taker")
    faucet(taker_addr, amount=1_000_000)

    coin_x = register_name(dysond, maker_name, maker_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])
    units = 200
    required_fee = int(units * fee_per_unit)
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_x}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_name,
        ).get("code", 1)
        == 0
    )

    tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"8{coin_x}",
        "--want",
        "4udys",
        "--from",
        maker_name,
    )
    assert tx.get("code", 1) == 0
    offer_id = int(
        [
            a
            for e in tx.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
            for a in e["attributes"]
            if a.get("key") == "offer_id"
        ][0]["value"]
    )

    take = dysond(
        "tx",
        "whaleswap",
        "take-offer",
        "--trades",
        f"offer_id={offer_id},take_units=2",
        "--from",
        taker_name,
    )
    assert (
        take.get("code", 1) == 0
    ), f"partial take failed: {json.dumps(take, indent=2)}"

    q = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    offer = q.get("offer", {})
    assert offer.get("status") == "open"
    assert offer.get("remaining_units") == "2"
    assert offer.get("remaining_have", {}).get("denom") == coin_x
    assert int(offer.get("remaining_have", {}).get("amount", "0")) == 4
    assert offer.get("remaining_want", {}).get("denom") == "udys"
    assert int(offer.get("remaining_want", {}).get("amount", "0")) == 2
    bals = dysond("query", "bank", "balances", taker_addr)
    got = {b.get("denom"): int(b.get("amount")) for b in bals.get("balances", [])}
    assert got.get(coin_x, 0) >= 4


def test_take_units_overflow_fails(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [maker_name, maker_addr] = generate_account("ob_over_maker")
    faucet(maker_addr, amount=2_000_000)
    [taker_name, taker_addr] = generate_account("ob_over_taker")
    faucet(taker_addr, amount=1_000_000)

    coin_x = register_name(dysond, maker_name, maker_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])
    units = 200
    required_fee = int(units * fee_per_unit)
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_x}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_name,
        ).get("code", 1)
        == 0
    )

    tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"4{coin_x}",
        "--want",
        "2udys",
        "--from",
        maker_name,
    )
    assert tx.get("code", 1) == 0
    offer_id = int(
        [
            a
            for e in tx.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
            for a in e["attributes"]
            if a.get("key") == "offer_id"
        ][0]["value"]
    )

    take = dysond(
        "tx",
        "whaleswap",
        "take-offer",
        "--trades",
        f"offer_id={offer_id},take_units=3",
        "--from",
        taker_name,
    )
    assert (
        take.get("code", 0) != 0
    ), f"overflowed take_units should fail: {json.dumps(take, indent=2)}"
