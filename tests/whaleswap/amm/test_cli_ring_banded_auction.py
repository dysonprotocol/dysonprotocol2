import json
from decimal import Decimal, ROUND_CEILING


def _parse_pool_id_attr(attrs):
    raw = attrs["pool_id"]
    val = json.loads(raw)
    pid = int(val)
    assert pid > 0
    return pid


def _mint(dysond, owner, denom, units):
    params = dysond("query", "nameservice", "params")
    fee_per = (
        Decimal(params["params"]["mint_fee_per_coin"])
        if params["params"].get("mint_fee_per_coin")
        else Decimal("0")
    )
    fee = int((Decimal(units) * fee_per).to_integral_value(rounding=ROUND_CEILING))
    res = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{denom}",
        "--mint-fee",
        f"{fee}udys",
        "--from",
        owner,
    )
    assert res.get("code", 1) == 0, f"mint failed: {json.dumps(res, indent=2)}"


def test_ring_trade_banded_auction(
    chainnet, ws_setup_env, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    c = env["denoms"][2]
    taker = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]

    # Create v3 pool (banded) for A/B with narrow band containing initial price
    tx_v3 = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--min-price",
        f"2{a}",
        "--min-price",
        f"1{b}",
        "--max-price",
        f"1{a}",
        "--max-price",
        f"2{b}",
        "--from",
        taker,
        "--gas",
        "auto",
    )
    assert tx_v3.get("code", 1) == 0, json.dumps(tx_v3, indent=2)
    ev_pc = [
        e
        for e in tx_v3.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pid_v3 = _parse_pool_id_attr(
        {a.get("key"): a.get("value") for a in ev_pc[0].get("attributes", [])}
    )

    # Create v2 pool for A/C to close ring later
    tx_v2 = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{c}",
        "--from",
        taker,
        "--gas",
        "auto",
    )
    assert tx_v2.get("code", 1) == 0, json.dumps(tx_v2, indent=2)
    ev_pc2 = [
        e
        for e in tx_v2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pid_v2 = _parse_pool_id_attr(
        {a.get("key"): a.get("value") for a in ev_pc2[0].get("attributes", [])}
    )

    # Intentional failure: PoolSwap exact-out near band without cap for A (defaults 0) => should fail on cap
    leg_fail = {"pool_id": pid_v3, "swap_out": {"denom": b, "amount": "1"}}
    out_fail = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--legs",
        json.dumps(leg_fail),
        "--from",
        taker,
        "--gas",
        "auto",
        raw=True,
    )
    low = (out_fail or "").lower()
    assert "debit exceeds cap" in low, f"unexpected error for missing cap: {out_fail}"

    # Create two offers: solid maker B->C and liquid-have maker l/A->B
    [maker_solid, maker_solid_addr] = generate_account("ring_maker_solid")
    faucet(maker_solid_addr, amount=1_000_000)
    [maker_liq, maker_liq_addr] = generate_account("ring_maker_liq")
    faucet(maker_liq_addr, amount=1_000_000)

    # Mint extra to fund makers then send
    owner = env["owner_name"]
    _mint(dysond, owner, b, 50)
    _mint(dysond, owner, a, 50)
    # send 20b to maker_solid, 20l/a to maker_liq
    send_b = dysond(
        "tx", "bank", "send", owner, maker_solid_addr, f"20{b}", "--from", owner
    )
    assert send_b.get("code", 1) == 0, f"send b failed: {json.dumps(send_b, indent=2)}"
    lA = "whaleswap.dys/coins/" + a
    conv = dysond(
        "tx",
        "whaleswap",
        "convert-to-liquid",
        "--denom",
        a,
        "--amount",
        "20",
        "--from",
        owner,
    )
    assert conv.get("code", 1) == 0, f"convert failed: {json.dumps(conv, indent=2)}"
    send_lA = dysond(
        "tx", "bank", "send", owner, maker_liq_addr, f"20{lA}", "--from", owner
    )
    assert (
        send_lA.get("code", 1) == 0
    ), f"send lA failed: {json.dumps(send_lA, indent=2)}"

    make1 = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"20{b}",
        "--want",
        f"10{c}",
        "--from",
        maker_solid,
    )
    assert (
        make1.get("code", 1) == 0
    ), f"make-offer solid failed: {json.dumps(make1, indent=2)}"
    ev_m1 = [
        e
        for e in make1.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    offer_id1 = int(
        str(
            [a for a in ev_m1[0].get("attributes", []) if a.get("key") == "offer_id"][
                0
            ]["value"]
        ).strip('"')
    )

    make2 = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"20{lA}",
        "--want",
        f"20{b}",
        "--from",
        maker_liq,
    )
    assert (
        make2.get("code", 1) == 0
    ), f"make-offer liquid failed: {json.dumps(make2, indent=2)}"
    ev_m2 = [
        e
        for e in make2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    offer_id2 = int(
        str(
            [a for a in ev_m2[0].get("attributes", []) if a.get("key") == "offer_id"][
                0
            ]["value"]
        ).strip('"')
    )

    # Mixed MakeTrade: v3 exact-out B, take liquid offer fully, take solid partially, v2 exact-in C->A
    op1 = {"swap": {"pool_id": pid_v3, "swap_out": {"denom": b, "amount": "1"}}}
    op2 = {
        "take": {"offer_id": offer_id2}
    }  # full close liquid have -> triggers pfand release
    op3 = {"take": {"offer_id": offer_id1, "take_units": "5"}}
    op4 = {"swap": {"pool_id": pid_v2, "swap_in": {"denom": c, "amount": "5"}}}

    tx_mt = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"100{a}",
        "--max-input",
        f"50{b}",
        "--max-input",
        f"20{c}",
        "--op",
        json.dumps(op1),
        "--op",
        json.dumps(op2),
        "--op",
        json.dumps(op3),
        "--op",
        json.dumps(op4),
        "--min-output",
        f"1{a}",
        "--from",
        taker,
        "--gas",
        "auto",
    )
    assert (
        tx_mt.get("code", 1) == 0
    ), f"make-trade failed: {json.dumps(tx_mt, indent=2)}"
    ev_tr = [
        e
        for e in tx_mt.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert ev_tr, f"no trade events: {json.dumps(tx_mt, indent=2)}"

    # Auction flow: open -> bidder accepts -> bidder redeems → records auction trade
    [seller_name, seller_addr] = generate_account("ring_auc_seller")
    faucet(seller_addr, amount=1_000_000)
    sell_denom = register_name(dysond, seller_name, seller_addr, "200udys")
    _mint(dysond, seller_name, sell_denom, 20)
    open_res = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"10{sell_denom}",
        "--from",
        seller_name,
    )
    assert (
        open_res.get("code", 1) == 0
    ), f"open-auction failed: {json.dumps(open_res, indent=2)}"
    ev_ac = [
        e
        for e in open_res.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    auction_id = int(
        str(
            [a for a in ev_ac[0].get("attributes", []) if a.get("key") == "auction_id"][
                0
            ]["value"]
        ).strip('"')
    )

    [bidder_name, bidder_addr] = generate_account("ring_auc_bidder")
    faucet(bidder_addr, amount=1_000_000)
    pb = dysond(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        "whaleswap.dys/auction/udys",
        "--nft-id",
        f"{auction_id:010d}",
        "--bid-amount",
        "1udys",
        "--from",
        bidder_name,
    )
    assert pb.get("code", 1) == 0, f"place-bid failed: {json.dumps(pb, indent=2)}"
    ab = dysond(
        "tx",
        "nameservice",
        "accept-bid",
        "--nft-class-id",
        "whaleswap.dys/auction/udys",
        "--nft-id",
        f"{auction_id:010d}",
        "--from",
        seller_name,
    )
    assert ab.get("code", 1) == 0, f"accept-bid failed: {json.dumps(ab, indent=2)}"
    red = dysond(
        "tx",
        "whaleswap",
        "redeem-auction",
        "--auction-id",
        str(auction_id),
        "--from",
        bidder_name,
    )
    assert red.get("code", 1) == 0, f"redeem failed: {json.dumps(red, indent=2)}"
    q = dysond(
        "query", "whaleswap", "trades-by-taker", bidder_addr, "--page-limit", "5"
    )
    trs = [t for t in q.get("trades", []) if int(t.get("auction_id", 0)) == auction_id]
    assert (
        len(trs) == 1
    ), f"expected 1 auction trade, got {len(trs)}: {json.dumps(q, indent=2)}"
