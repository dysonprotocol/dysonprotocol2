import json


def test_cancel_normal_refunds_escrow(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [maker_name, maker_addr] = generate_account("ob_cancel_m")
    faucet(maker_addr, amount=2_000_000)

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

    start = {
        b.get("denom"): int(b.get("amount"))
        for b in dysond("query", "bank", "balances", maker_addr).get("balances", [])
    }.get(coin_x, 0)
    offer_have = 50
    tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"{offer_have}{coin_x}",
        "--want",
        "25udys",
        "--from",
        maker_name,
    )
    assert tx.get("code", 1) == 0
    mid = {
        b.get("denom"): int(b.get("amount"))
        for b in dysond("query", "bank", "balances", maker_addr).get("balances", [])
    }.get(coin_x, 0)
    assert mid == start - offer_have
    offer_id = int(
        [
            a
            for e in tx.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
            for a in e["attributes"]
            if a.get("key") == "offer_id"
        ][0]["value"]
    )
    cancel = dysond(
        "tx",
        "whaleswap",
        "cancel-offer",
        "--offer-id",
        str(offer_id),
        "--from",
        maker_name,
    )
    assert cancel.get("code", 1) == 0
    end = {
        b.get("denom"): int(b.get("amount"))
        for b in dysond("query", "bank", "balances", maker_addr).get("balances", [])
    }.get(coin_x, 0)
    assert end == start


def test_duplicate_offer_id_batch_fails(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [maker_name, maker_addr] = generate_account("ob_dup_m")
    faucet(maker_addr, amount=2_000_000)
    [taker_name, taker_addr] = generate_account("ob_dup_t")
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
        f"10{coin_x}",
        "--want",
        "5udys",
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
        "make-trade",
        "--max-input",
        "0udys",
        "--op",
        json.dumps({"take": {"offer_id": offer_id, "take_units": ""}}),
        "--op",
        json.dumps({"take": {"offer_id": offer_id, "take_units": ""}}),
        "--from",
        taker_name,
    )
    assert take.get("code", 0) != 0
