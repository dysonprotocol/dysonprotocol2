import json


def test_take_offer_closes_offer(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [maker_name, maker_addr] = generate_account("ob_maker2")
    faucet(maker_addr, amount=2_000_000)
    [taker_name, taker_addr] = generate_account("ob_taker2")
    faucet(taker_addr, amount=1_000_000)

    name = register_name(dysond, maker_name, maker_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 200
    required_fee = int(units * fee_per_unit)
    mint = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{name}",
        "--mint-fee",
        f"{required_fee}udys",
        "--from",
        maker_name,
    )
    assert mint.get("code", 1) == 0, f"mint-coins failed: {json.dumps(mint, indent=2)}"

    have = f"100{name}"
    want = "50udys"
    tx = dysond(
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
    assert tx.get("code", 1) == 0, f"make-offer failed: {json.dumps(tx, indent=2)}"

    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    assert evs, f"EventOfferCreated not found: {tx}"
    attrs = evs[0].get("attributes", [])
    oid_attr = [a for a in attrs if a.get("key") == "offer_id"]
    offer_id = int(oid_attr[0].get("value"))

    take = dysond(
        "tx",
        "whaleswap",
        "take-offer",
        "--trades",
        f"offer_id={offer_id}",
        "--from",
        taker_name,
    )
    assert take.get("code", 1) == 0, f"take-offer failed: {json.dumps(take, indent=2)}"

    q = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    offer = q.get("offer")
    assert (
        offer and offer["status"] == "closed"
    ), f"offer not closed: {json.dumps(q, indent=2)}"
