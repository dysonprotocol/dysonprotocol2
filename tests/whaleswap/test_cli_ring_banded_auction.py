import json
from decimal import Decimal, ROUND_CEILING
from tests.whaleswap.amm.conftest import ws_setup_env  # noqa: F401


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

    # Assert initial v3 pool reserves and band setup
    q_v3 = dysond("query", "whaleswap", "pool", "--pool-id", str(pid_v3))
    assert "pool" in q_v3, f"missing pool in query: {json.dumps(q_v3, indent=2)}"
    p3 = q_v3["pool"]
    # Coins are in canonical order; expect exactly 100 each
    c3 = {c["denom"]: c["amount"] for c in p3.get("coins", [])}
    assert (
        c3.get(a) == "100"
    ), f"v3 pool A reserve mismatch. Full: {json.dumps(q_v3, indent=2)}"
    assert (
        c3.get(b) == "100"
    ), f"v3 pool B reserve mismatch. Full: {json.dumps(q_v3, indent=2)}"

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

    # Assert initial v2 pool reserves
    q_v2 = dysond("query", "whaleswap", "pool", "--pool-id", str(pid_v2))
    assert "pool" in q_v2, f"missing pool in query: {json.dumps(q_v2, indent=2)}"
    p2 = q_v2["pool"]
    c2 = {c["denom"]: c["amount"] for c in p2.get("coins", [])}
    assert (
        c2.get(a) == "100"
    ), f"v2 pool A reserve mismatch. Full: {json.dumps(q_v2, indent=2)}"
    assert (
        c2.get(c) == "100"
    ), f"v2 pool C reserve mismatch. Full: {json.dumps(q_v2, indent=2)}"

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
    # send 20a to maker_liq (liquid mode will use base-have with pfand)
    send_a_liq = dysond(
        "tx", "bank", "send", owner, maker_liq_addr, f"20{a}", "--from", owner
    )
    assert (
        send_a_liq.get("code", 1) == 0
    ), f"send a to maker_liq failed: {json.dumps(send_a_liq, indent=2)}"

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

    # Assert solid offer state (B->C: 20 -> 10)
    q_o1 = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id1))
    assert "offer" in q_o1, f"missing offer in query: {json.dumps(q_o1, indent=2)}"
    o1 = q_o1["offer"]
    assert (
        o1.get("remaining_have", {}).get("denom") == b
    ), f"offer1 have denom mismatch: {json.dumps(q_o1, indent=2)}"
    assert (
        o1.get("remaining_have", {}).get("amount") == "20"
    ), f"offer1 have amount mismatch: {json.dumps(q_o1, indent=2)}"
    assert (
        o1.get("remaining_want", {}).get("denom") == c
    ), f"offer1 want denom mismatch: {json.dumps(q_o1, indent=2)}"
    assert (
        o1.get("remaining_want", {}).get("amount") == "10"
    ), f"offer1 want amount mismatch: {json.dumps(q_o1, indent=2)}"

    make2 = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"20{a}",
        "--want",
        f"20{b}",
        "--settlement-mode",
        "settlement-liquid",
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

    # Assert liquid-have offer state (l/A -> B: 20 -> 20)
    q_o2 = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id2))
    assert "offer" in q_o2, f"missing offer in query: {json.dumps(q_o2, indent=2)}"
    o2 = q_o2["offer"]
    assert (
        o2.get("remaining_have", {}).get("denom") == a
    ), f"offer2 have denom mismatch: {json.dumps(q_o2, indent=2)}"
    assert (
        o2.get("remaining_have", {}).get("amount") == "20"
    ), f"offer2 have amount mismatch: {json.dumps(q_o2, indent=2)}"
    assert (
        o2.get("remaining_want", {}).get("denom") == b
    ), f"offer2 want denom mismatch: {json.dumps(q_o2, indent=2)}"
    assert (
        o2.get("remaining_want", {}).get("amount") == "20"
    ), f"offer2 want amount mismatch: {json.dumps(q_o2, indent=2)}"

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
        f"10{c}",
        "--max-input",
        f"9{b}",
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
        "2000000",
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

    # Post-trade: assert offers updated
    q_o1_after = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id1))
    o1a = q_o1_after.get("offer", {})
    # Expect partial fill: remaining 10 B -> 5 C, status open
    assert (
        o1a.get("remaining_have", {}).get("denom") == b
    ), f"offer1 after have denom: {json.dumps(q_o1_after, indent=2)}"
    assert (
        o1a.get("remaining_have", {}).get("amount") == "10"
    ), f"offer1 after have amount: {json.dumps(q_o1_after, indent=2)}"
    assert (
        o1a.get("remaining_want", {}).get("denom") == c
    ), f"offer1 after want denom: {json.dumps(q_o1_after, indent=2)}"
    assert (
        o1a.get("remaining_want", {}).get("amount") == "5"
    ), f"offer1 after want amount: {json.dumps(q_o1_after, indent=2)}"
    assert (
        o1a.get("status") == "open"
    ), f"offer1 after status: {json.dumps(q_o1_after, indent=2)}"

    q_o2_after = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id2))
    o2a = q_o2_after.get("offer", {})
    # Expect full close: zero remain, status closed
    assert (
        o2a.get("remaining_have", {}).get("amount") == "0"
    ), f"offer2 after have not zero: {json.dumps(q_o2_after, indent=2)}"
    assert (
        o2a.get("remaining_want", {}).get("amount") == "0"
    ), f"offer2 after want not zero: {json.dumps(q_o2_after, indent=2)}"
    assert (
        o2a.get("status") == "closed"
    ), f"offer2 after status: {json.dumps(q_o2_after, indent=2)}"

    # Post-trade: assert exact pool reserves after ops
    q_v3_after = dysond("query", "whaleswap", "pool", "--pool-id", str(pid_v3))
    q_v2_after = dysond("query", "whaleswap", "pool", "--pool-id", str(pid_v2))
    p3a = q_v3_after.get("pool", {})
    p2a = q_v2_after.get("pool", {})
    m3 = {c["denom"]: c["amount"] for c in p3a.get("coins", [])}
    m2 = {c["denom"]: c["amount"] for c in p2a.get("coins", [])}
    assert (
        m3.get(a) == "103"
    ), f"post-trade v3 pool A reserve mismatch: {json.dumps(q_v3_after, indent=2)}"
    assert (
        m3.get(b) == "99"
    ), f"post-trade v3 pool B reserve mismatch: {json.dumps(q_v3_after, indent=2)}"
    assert (
        m2.get(a) == "96"
    ), f"post-trade v2 pool A reserve mismatch: {json.dumps(q_v2_after, indent=2)}"
    assert (
        m2.get(c) == "105"
    ), f"post-trade v2 pool C reserve mismatch: {json.dumps(q_v2_after, indent=2)}"

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
        b,
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
    # Fund bidder with 1 unit of bid denom (B) to satisfy escrow
    fund_bidder = dysond(
        "tx",
        "bank",
        "send",
        env["owner_addr"],
        bidder_addr,
        f"1{b}",
        "--from",
        env["owner_name"],
    )
    assert (
        fund_bidder.get("code", 1) == 0
    ), f"fund bidder failed: {json.dumps(fund_bidder, indent=2)}"
    pb = dysond(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        f"whaleswap.dys/auction/{b}",
        "--nft-id",
        f"{auction_id:010d}",
        "--bid-amount",
        f"1{b}",
        "--from",
        bidder_name,
    )
    assert pb.get("code", 1) == 0, f"place-bid failed: {json.dumps(pb, indent=2)}"
    ab = dysond(
        "tx",
        "nameservice",
        "accept-bid",
        "--nft-class-id",
        f"whaleswap.dys/auction/{b}",
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
    # Query trades by auction using new TradesByAuction endpoint
    q = dysond(
        "query",
        "whaleswap",
        "trades-by-auction",
        f"--auction-id={auction_id}",
        "--page-limit",
        "5",
    )
    trs = q.get("trades", [])
    assert (
        len(trs) == 1
    ), f"expected 1 auction trade, got {len(trs)}: {json.dumps(q, indent=2)}"

    # Verify it's for the right bidder
    assert (
        trs[0].get("trader") == bidder_addr
    ), f"trader mismatch: {json.dumps(trs[0], indent=2)}"
