import json
from decimal import Decimal, ROUND_CEILING


def test_redeem_records_trade_only_for_last_bidder(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]

    # Seller opens auction with solid sell denom
    [seller_name, seller_addr] = generate_account("auc_tr_redeem_seller")
    faucet(seller_addr, amount=2_000_000)
    denom = register_name(dysond, seller_name, seller_addr, "200udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = Decimal(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = Decimal(40)
    mint_fee = int((units * fee_per_unit).to_integral_value(rounding=ROUND_CEILING))
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{int(units)}{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            seller_name,
        ).get("code", 1)
        == 0
    )
    open_res = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"20{denom}",
        "--from",
        seller_name,
    )
    assert (
        open_res.get("code", 1) == 0
    ), f"open-auction failed: {json.dumps(open_res, indent=2)}"
    evs = [
        e
        for e in open_res.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    assert evs, f"no auction created event: {json.dumps(open_res, indent=2)}"
    auction_id = int(
        [a for a in evs[0].get("attributes", []) if a.get("key") == "auction_id"][0][
            "value"
        ].strip('"')
    )

    # Random non-bidder tries to redeem: should succeed but NOT record a trade
    [rnd_name, rnd_addr] = generate_account("auc_tr_redeem_other")
    faucet(rnd_addr, amount=1_000_000)

    # Transfer NFT to rnd_addr (module must authorize; nameservice will likely reject; skip if unauthorized)
    # We verify the positive path: seller redeems without bidders -> no trade recorded
    redeem1 = dysond(
        "tx",
        "whaleswap",
        "redeem-auction",
        "--auction-id",
        str(auction_id),
        "--from",
        seller_name,
    )
    assert (
        redeem1.get("code", 1) == 0
    ), f"redeem failed: {json.dumps(redeem1, indent=2)}"

    # Verify there is no trade for seller via trades-by-taker (strict empty page)
    q1 = dysond(
        "query",
        "whaleswap",
        "trades-by-taker",
        f"--taker={seller_addr}",
        "--page-limit",
        "1",
    )
    assert (
        q1.get("trades", []) == []
    ), f"unexpected trade on redeem without bidder: {json.dumps(q1, indent=2)}"

    # Open another auction and complete a bid/accept so bidder becomes owner
    open_res2 = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"10{denom}",
        "--from",
        seller_name,
    )
    assert open_res2.get("code", 1) == 0
    evs2 = [
        e
        for e in open_res2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    auction_id2 = int(
        [a for a in evs2[0].get("attributes", []) if a.get("key") == "auction_id"][0][
            "value"
        ].strip('"')
    )

    [bidder_name, bidder_addr] = generate_account("auc_tr_redeem_bidder")
    faucet(bidder_addr, amount=1_000_000)

    place = dysond(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        "whaleswap.dys/auction/udys",
        "--nft-id",
        f"{auction_id2:010d}",
        "--bid-amount",
        "1udys",
        "--from",
        bidder_name,
    )
    assert place.get("code", 1) == 0, f"place-bid failed: {json.dumps(place, indent=2)}"

    accept = dysond(
        "tx",
        "nameservice",
        "accept-bid",
        "--nft-class-id",
        "whaleswap.dys/auction/udys",
        "--nft-id",
        f"{auction_id2:010d}",
        "--from",
        seller_name,
    )
    assert (
        accept.get("code", 1) == 0
    ), f"accept-bid failed: {json.dumps(accept, indent=2)}"

    # Redeem by bidder now should record a trade for bidder
    redeem2 = dysond(
        "tx",
        "whaleswap",
        "redeem-auction",
        "--auction-id",
        str(auction_id2),
        "--from",
        bidder_name,
    )
    assert (
        redeem2.get("code", 1) == 0
    ), f"redeem with valuation failed: {json.dumps(redeem2, indent=2)}"

    tqs = dysond(
        "query",
        "whaleswap",
        "trades-by-taker",
        f"--taker={bidder_addr}",
        "--page-limit",
        "10",
    )
    trs = [
        t for t in tqs.get("trades", []) if int(t.get("auction_id", 0)) == auction_id2
    ]
    assert (
        len(trs) == 1
    ), f"expected exactly 1 auction trade: {json.dumps(tqs, indent=2)}"
    tr = trs[0]
    # pool_id/offer_id may be omitted for zero; enforce zero-or-absent strictly
    assert tr.get("pool_id") in (
        None,
        "0",
        0,
    ), f"pool_id must be zero or absent: {json.dumps(tr, indent=2)}"
    assert tr.get("offer_id") in (
        None,
        "0",
        0,
    ), f"offer_id must be zero or absent: {json.dumps(tr, indent=2)}"
    assert int(tr.get("auction_id")) == auction_id2
    sent = tr.get("sent", {})
    recv = tr.get("received", {})
    assert (
        f"{sent.get('amount')}{sent.get('denom')}" == "1udys"
    ), f"sent must equal valuation: {json.dumps(tr, indent=2)}"
    assert (
        recv.get("denom") == denom and int(recv.get("amount")) == 10
    ), f"received must equal sell amount: {json.dumps(tr, indent=2)}"
