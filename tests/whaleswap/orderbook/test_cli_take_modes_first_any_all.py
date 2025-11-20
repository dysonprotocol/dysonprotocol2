import json


def test_take_mode_first_executes_only_first_feasible(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [maker1_name, maker1_addr] = generate_account(
        "ob_maker_first1", faucet_amount=2_000_000
    )
    [maker2_name, maker2_addr] = generate_account(
        "ob_maker_first2", faucet_amount=2_000_000
    )
    [taker_name, taker_addr] = generate_account(
        "ob_taker_first", faucet_amount=1_000_000
    )

    name = register_name(dysond, maker1_name, maker1_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 200
    required_fee = int(units * fee_per_unit)
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{name}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker1_name,
        ).get("code", 1)
        == 0
    )

    tx_a = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"100{name}",
        "--want",
        "50udys",
        "--from",
        maker1_name,
    )
    assert (
        tx_a.get("code", 1) == 0
    ), f"make-offer A failed: {json.dumps(tx_a, indent=2)}"
    evs_a = [
        e
        for e in tx_a.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    offer_a = int(
        [a for a in evs_a[0]["attributes"] if a.get("key") == "offer_id"][0]["value"]
    )

    tx_b = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        "100udys",
        "--want",
        f"999999{name}",
        "--from",
        maker2_name,
    )
    assert (
        tx_b.get("code", 1) == 0
    ), f"make-offer B failed: {json.dumps(tx_b, indent=2)}"
    evs_b = [
        e
        for e in tx_b.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    offer_b = int(
        [a for a in evs_b[0]["attributes"] if a.get("key") == "offer_id"][0]["value"]
    )

    take_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "0udys",
        "--op",
        json.dumps({"take": {"offer_id": offer_b, "take_units": ""}}),
        "--op",
        json.dumps({"take": {"offer_id": offer_a, "take_units": ""}}),
        "--from",
        taker_name,
    )
    assert (
        take_tx.get("code", 0) != 0
    ), f"batch should fail: {json.dumps(take_tx, indent=2)}"
    qa = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_a))
    qb = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_b))
    assert qa.get("offer", {}).get("status") == "open"
    assert qb.get("offer", {}).get("status") == "open"

    take_a = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "50udys",
        "--op",
        json.dumps({"take": {"offer_id": offer_a, "take_units": ""}}),
        "--from",
        taker_name,
    )
    assert (
        take_a.get("code", 1) == 0
    ), f"take-offer(A) failed: {json.dumps(take_a, indent=2)}"
    qa = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_a))
    qb = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_b))
    assert qa.get("offer", {}).get("status") == "closed"
    assert qb.get("offer", {}).get("status") == "open"


def test_take_mode_any_executes_feasible_subset(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [maker1_name, maker1_addr] = generate_account(
        "ob_maker_any1", faucet_amount=2_000_000
    )
    [maker2_name, maker2_addr] = generate_account(
        "ob_maker_any2", faucet_amount=2_000_000
    )
    [taker_name, taker_addr] = generate_account("ob_taker_any", faucet_amount=1_000_000)

    name = register_name(dysond, maker1_name, maker1_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 200
    required_fee = int(units * fee_per_unit)
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{name}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker1_name,
        ).get("code", 1)
        == 0
    )

    tx_a = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"50{name}",
        "--want",
        "25udys",
        "--from",
        maker1_name,
    )
    tx_b = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        "50udys",
        "--want",
        f"999999{name}",
        "--from",
        maker2_name,
    )
    assert tx_a.get("code", 1) == 0 and tx_b.get("code", 1) == 0

    offer_a = int(
        [
            a
            for e in tx_a.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
            for a in e["attributes"]
            if a.get("key") == "offer_id"
        ][0]["value"]
    )
    offer_b = int(
        [
            a
            for e in tx_b.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
            for a in e["attributes"]
            if a.get("key") == "offer_id"
        ][0]["value"]
    )

    take_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "0udys",
        "--op",
        json.dumps({"take": {"offer_id": offer_b, "take_units": ""}}),
        "--op",
        json.dumps({"take": {"offer_id": offer_a, "take_units": ""}}),
        "--from",
        taker_name,
    )
    assert take_tx.get("code", 0) != 0
    qa = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_a))
    qb = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_b))
    assert qa.get("offer", {}).get("status") == "open"
    assert qb.get("offer", {}).get("status") == "open"

    take_a = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "50udys",
        "--op",
        json.dumps({"take": {"offer_id": offer_a, "take_units": ""}}),
        "--from",
        taker_name,
    )
    assert take_a.get("code", 1) == 0
    qa = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_a))
    qb = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_b))
    assert qa.get("offer", {}).get("status") == "closed"
    assert qb.get("offer", {}).get("status") == "open"


def test_take_mode_all_requires_all_success(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [maker1_name, maker1_addr] = generate_account(
        "ob_maker_all1", faucet_amount=2_000_000
    )
    [maker2_name, maker2_addr] = generate_account(
        "ob_maker_all2", faucet_amount=2_000_000
    )
    [taker_name, taker_addr] = generate_account("ob_taker_all", faucet_amount=1_000_000)

    name = register_name(dysond, maker1_name, maker1_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 200
    required_fee = int(units * fee_per_unit)
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{name}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker1_name,
        ).get("code", 1)
        == 0
    )

    tx_a = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"50{name}",
        "--want",
        "25udys",
        "--from",
        maker1_name,
    )
    tx_b = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        "50udys",
        "--want",
        f"999999{name}",
        "--from",
        maker2_name,
    )
    assert tx_a.get("code", 1) == 0 and tx_b.get("code", 1) == 0
    offer_a = int(
        [
            a
            for e in tx_a.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
            for a in e["attributes"]
            if a.get("key") == "offer_id"
        ][0]["value"]
    )
    offer_b = int(
        [
            a
            for e in tx_b.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
            for a in e["attributes"]
            if a.get("key") == "offer_id"
        ][0]["value"]
    )

    take_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "0udys",
        "--op",
        json.dumps({"take": {"offer_id": offer_b, "take_units": ""}}),
        "--op",
        json.dumps({"take": {"offer_id": offer_a, "take_units": ""}}),
        "--from",
        taker_name,
    )
    assert take_tx.get("code", 1) != 0
