import json


def test_open_auction_basic(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [seller_name, seller_addr] = generate_account("auc_seller")
    faucet(seller_addr, amount=2_000_000)

    # Prepare custom sell denom with supply; use udys as bid denom (has supply)
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

    # Open auction: escrow custom denom; bids in udys
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

    # Extract auction_id
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    assert evs, f"EventAuctionCreated not found: {tx}"
    attrs = evs[0].get("attributes", [])
    aid_attr = [a for a in attrs if a.get("key") == "auction_id"]
    assert aid_attr, f"auction_id missing: {evs}"
    auction_id = int(str(aid_attr[0].get("value")).strip('"'))

    # Query auction
    q = dysond("query", "whaleswap", "auction", "--auction-id", str(auction_id))
    auction = q.get("auction")
    assert auction, f"auction not found: {q}"
    assert auction["sell"]["denom"] == name, f"unexpected sell denom: {auction}"
    assert auction["bid_denom"] == "udys", f"unexpected bid denom: {auction}"
