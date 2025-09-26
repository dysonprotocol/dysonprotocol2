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


def test_make_trade_take_units_overflow_fails(chainnet, faucet, ws_setup_env):
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

    have = f"4{denom}"
    want = "8udys"

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

    op = json.dumps({"take": {"offer_id": offer_id, "take_units": "5"}})
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        op,
        "--from",
        taker_name,
        "--max-input",
        "100udys",
        "--gas",
        "200000",
        "--yes",
    )
    assert isinstance(tx, dict), f"non-dict tx response: {tx}"
    assert (
        tx.get("code", 0) != 0
    ), f"overflowed take_units should fail: {json.dumps(tx, indent=2)}"
    raw_log = tx.get("raw_log", "")
    assert isinstance(raw_log, str), f"raw_log not a string: {json.dumps(tx, indent=2)}"
    low = raw_log.lower()
    assert (
        "take_units exceeds remaining" in low
    ), f"unexpected error: {json.dumps(tx, indent=2)}"
