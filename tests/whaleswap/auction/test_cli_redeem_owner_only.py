import json


def test_redeem_auction_no_bidder_owner_only(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [seller_name, seller_addr] = generate_account("auc_seller2")
    faucet(seller_addr, amount=2_000_000)

    name = register_name(dysond, seller_name, seller_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 100
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
        seller_name,
    )
    assert mint.get("code", 1) == 0, f"mint-coins failed: {json.dumps(mint, indent=2)}"

    tx = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"{units}{name}",
        "--from",
        seller_name,
    )
    assert tx.get("code", 1) == 0, f"open-auction failed: {json.dumps(tx, indent=2)}"
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    auction_id = int(
        str(
            [a for a in evs[0].get("attributes", []) if a.get("key") == "auction_id"][
                0
            ]["value"]
        ).strip('"')
    )

    redeem = dysond(
        "tx",
        "whaleswap",
        "redeem-auction",
        "--auction-id",
        str(auction_id),
        "--from",
        seller_name,
    )
    assert (
        redeem.get("code", 1) == 0
    ), f"redeem-auction failed: {json.dumps(redeem, indent=2)}"

    q = dysond("query", "whaleswap", "auction", "--auction-id", str(auction_id))
    assert isinstance(q, str), f"expected error string, got {type(q)}: {q}"
    assert "auction not found" in q, f"unexpected error string: {q}"
