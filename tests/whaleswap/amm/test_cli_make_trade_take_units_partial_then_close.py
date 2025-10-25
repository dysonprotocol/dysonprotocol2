import json


def _extract_offer_id(tx):
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    attrs = evs[0].get("attributes", [])
    oid_attr = [a for a in attrs if a.get("key") == "offer_id"]
    # Event values are JSON-encoded
    return int(json.loads(oid_attr[0].get("value")))


def test_make_trade_take_units_partial_then_close(chainnet, faucet, ws_setup_env):
    dysond = chainnet[0]

    # Use pre-minted denoms and funded accounts from ws_setup_env
    maker_name = ws_setup_env["acc2"]["name"]
    maker_addr = ws_setup_env["acc2"]["addr"]
    taker_name = ws_setup_env["acc1"]["name"]
    taker_addr = ws_setup_env["acc1"]["addr"]
    denom = ws_setup_env["denoms"][0]

    # Ensure both have udys for fees
    faucet(maker_addr, amount=2_000_000)
    faucet(taker_addr, amount=2_000_000)

    have = "100udys"
    want = f"5{denom}"

    mk = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        have,
        "--want",
        want,
        "--from",
        maker_name,
    )
    assert mk.get("code", 1) == 0, f"make-offer failed: {json.dumps(mk, indent=2)}"
    offer_id = _extract_offer_id(mk)

    # Partial take via MakeTrade (take_units=1)
    op1 = json.dumps({"take": {"offer_id": offer_id, "take_units": "1"}})
    tx1 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        op1,
        "--max-input",
        f"1{denom}",
        "--from",
        taker_name,
    )
    assert tx1.get("code", 1) == 0, f"partial take failed: {json.dumps(tx1, indent=2)}"
    q1 = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    offer1 = q1.get("offer", {})
    assert offer1.get("status") == "open"
    # GCD units: gcd(100,5)=5 => unit_have=20, unit_want=1, remaining_units=5-1=4
    assert offer1.get("remaining_units") == "4"

    # Close remainder via MakeTrade (take_units=4)
    op2 = json.dumps({"take": {"offer_id": offer_id, "take_units": "4"}})
    tx2 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        op2,
        "--max-input",
        f"4{denom}",
        "--from",
        taker_name,
    )
    assert tx2.get("code", 1) == 0, f"close take failed: {json.dumps(tx2, indent=2)}"
    q2 = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    offer2 = q2.get("offer", {})
    assert offer2.get("status") == "closed"
    assert offer2.get("remaining_units") == "0"
