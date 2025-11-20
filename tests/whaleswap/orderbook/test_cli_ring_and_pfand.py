import json
import pytest


def test_ring_coincidence_of_wants(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [maker_a_name, maker_a_addr] = generate_account("ring_maker_a")
    [maker_b_name, maker_b_addr] = generate_account("ring_maker_b")
    [maker_c_name, maker_c_addr] = generate_account("ring_maker_c")
    [taker_name, taker_addr] = generate_account("ring_taker")
    faucet(maker_a_addr, amount=2_000_000)
    faucet(maker_b_addr, amount=2_000_000)
    faucet(maker_c_addr, amount=2_000_000)
    faucet(taker_addr, amount=1_000_000)

    coin_a = register_name(dysond, maker_a_name, maker_a_addr, "1000udys")
    coin_b = register_name(dysond, maker_b_name, maker_b_addr, "1000udys")
    coin_c = register_name(dysond, maker_c_name, maker_c_addr, "1000udys")
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
            f"{units}{coin_a}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_a_name,
        ).get("code", 1)
        == 0
    )
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_b}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_b_name,
        ).get("code", 1)
        == 0
    )
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_c}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_c_name,
        ).get("code", 1)
        == 0
    )

    tx_a = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_a}",
        "--want",
        f"1{coin_b}",
        "--from",
        maker_a_name,
    )
    tx_b = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_b}",
        "--want",
        f"1{coin_c}",
        "--from",
        maker_b_name,
    )
    tx_c = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_c}",
        "--want",
        f"1{coin_a}",
        "--from",
        maker_c_name,
    )
    assert (
        tx_a.get("code", 1) == 0
        and tx_b.get("code", 1) == 0
        and tx_c.get("code", 1) == 0
    )

    def _offer_id(tx):
        evs = [
            e
            for e in tx.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
        ]
        attrs = evs[0].get("attributes", [])
        oid_attr = [a for a in attrs if a.get("key") == "offer_id"]
        return int(oid_attr[0].get("value"))

    offer_a = _offer_id(tx_a)
    offer_b = _offer_id(tx_b)
    offer_c = _offer_id(tx_c)

    take_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "0udys",
        "--op",
        json.dumps({"take": {"offer_id": offer_a, "take_units": ""}}),
        "--op",
        json.dumps({"take": {"offer_id": offer_b, "take_units": ""}}),
        "--op",
        json.dumps({"take": {"offer_id": offer_c, "take_units": ""}}),
        "--from",
        taker_name,
    )
    assert (
        take_tx.get("code", 1) == 0
    ), f"ring take failed: {json.dumps(take_tx, indent=2)}"

    qa = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_a))
    qb = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_b))
    qc = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_c))
    assert qa.get("offer", {}).get("status") == "closed"
    assert qb.get("offer", {}).get("status") == "closed"
    assert qc.get("offer", {}).get("status") == "closed"


def test_ring_with_liquid_and_pfand(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [maker_a_name, maker_a_addr] = generate_account("ringL_maker_a")
    [maker_b_name, maker_b_addr] = generate_account("ringL_maker_b")
    [maker_c_name, maker_c_addr] = generate_account("ringL_maker_c")
    [taker_name, taker_addr] = generate_account("ringL_taker")
    faucet(maker_a_addr, amount=2_000_000)
    faucet(maker_b_addr, amount=2_000_000)
    faucet(maker_c_addr, amount=2_000_000)
    faucet(taker_addr, amount=1_000_000)

    coin_a = register_name(dysond, maker_a_name, maker_a_addr, "1000udys")
    coin_b = register_name(dysond, maker_b_name, maker_b_addr, "1000udys")
    coin_c = register_name(dysond, maker_c_name, maker_c_addr, "1000udys")
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
            f"{units}{coin_a}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_a_name,
        ).get("code", 1)
        == 0
    )
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_b}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_b_name,
        ).get("code", 1)
        == 0
    )
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_c}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_c_name,
        ).get("code", 1)
        == 0
    )

    # No liquid conversions; use base coins with settlement-liquid offers

    tx_a = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_a}",
        "--want",
        f"1{coin_b}",
        "--settlement-mode",
        "settlement-liquid",
        "--from",
        maker_a_name,
    )
    tx_b = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_b}",
        "--want",
        f"1{coin_c}",
        "--settlement-mode",
        "settlement-liquid",
        "--from",
        maker_b_name,
    )
    tx_c = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_c}",
        "--want",
        f"1{coin_a}",
        "--settlement-mode",
        "settlement-liquid",
        "--from",
        maker_c_name,
    )
    assert (
        tx_a.get("code", 1) == 0
        and tx_b.get("code", 1) == 0
        and tx_c.get("code", 1) == 0
    )

    def _offer_id(tx):
        evs = [
            e
            for e in tx.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
        ]
        attrs = evs[0].get("attributes", [])
        oid_attr = [a for a in attrs if a.get("key") == "offer_id"]
        return int(oid_attr[0].get("value"))

    offer_a = _offer_id(tx_a)
    offer_b = _offer_id(tx_b)
    offer_c = _offer_id(tx_c)

    take_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "0udys",
        "--op",
        json.dumps({"take": {"offer_id": offer_a, "take_units": ""}}),
        "--op",
        json.dumps({"take": {"offer_id": offer_b, "take_units": ""}}),
        "--op",
        json.dumps({"take": {"offer_id": offer_c, "take_units": ""}}),
        "--from",
        taker_name,
    )
    assert (
        take_tx.get("code", 1) == 0
    ), f"ring liquid take failed: {json.dumps(take_tx, indent=2)}"

    qa = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_a))
    qb = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_b))
    qc = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_c))
    assert qa.get("offer", {}).get("status") == "closed"
    assert qb.get("offer", {}).get("status") == "closed"
    assert qc.get("offer", {}).get("status") == "closed"

    bals = dysond("query", "bank", "balances", taker_addr)
    by_denom = {b.get("denom"): int(b.get("amount")) for b in bals.get("balances", [])}
    p = dysond("query", "whaleswap", "params")
    pf = p.get("params", {}).get("pfand_per_offer", {})
    pf_denom = pf.get("denom")
    pf_amt = int(pf.get("amount", "0"))
    expected_min = pf_amt * 3
    assert by_denom.get(pf_denom, 0) >= expected_min
