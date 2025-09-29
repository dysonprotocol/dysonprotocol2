import json
from decimal import Decimal, ROUND_CEILING


def test_nft_transfer_then_redeem_new_owner_old_owner_fails(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [seller_name, seller_addr] = generate_account("auc_xfer_seller")
    faucet(seller_addr, amount=2_000_000)
    [other_name, other_addr] = generate_account("auc_xfer_other")
    faucet(other_addr, amount=1_000_000)

    denom = register_name(dysond, seller_name, seller_addr, "200udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = Decimal(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 30
    mint_fee = int(
        (Decimal(units) * fee_per_unit).to_integral_value(rounding=ROUND_CEILING)
    )
    mint = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{denom}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        seller_name,
    )
    assert mint.get("code", 1) == 0

    tx = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"{units}{denom}",
        "--from",
        seller_name,
    )
    assert tx.get("code", 1) == 0
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
    class_id = "whaleswap.dys/auction/udys"
    nft_id = f"{auction_id:010d}"

    # Moving auction NFTs should be unauthorized for the seller (class is module-owned)
    mv = dysond(
        "tx",
        "nameservice",
        "move-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--to-address",
        other_addr,
        "--from",
        seller_name,
    )
    assert (
        mv.get("code", 0) != 0
    ), f"move-nft unexpectedly succeeded: {json.dumps(mv, indent=2)}"
    raw_log = str(mv.get("raw_log", "")).lower()
    assert (
        "unauthorized" in raw_log
    ), f"unexpected move-nft error: {json.dumps(mv, indent=2)}"

    # Seller remains the owner; redeem succeeds for seller
    ok = dysond(
        "tx",
        "whaleswap",
        "redeem-auction",
        "--auction-id",
        str(auction_id),
        "--from",
        seller_name,
    )
    assert (
        ok.get("code", 1) == 0
    ), f"redeem by seller failed: {json.dumps(ok, indent=2)}"

    gone = dysond("query", "whaleswap", "auction", str(auction_id))
    assert isinstance(gone, str) and "auction not found" in gone
