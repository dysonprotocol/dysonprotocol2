import json
from decimal import Decimal, ROUND_CEILING


def test_auctions_query_filters_and_index_cleanup(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [seller_name, seller_addr] = generate_account("auc_idx")
    faucet(seller_addr, amount=2_000_000)

    name = register_name(dysond, seller_name, seller_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 42
    # Use ceiling like other tests to avoid underpaying by truncation
    required_fee = int(
        (Decimal(units) * Decimal(str(fee_per_unit))).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
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
    assert mint.get("code", 1) == 0

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
    assert tx.get("code", 1) == 0
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    attrs = evs[0].get("attributes", [])
    auction_id = int(
        str([a for a in attrs if a.get("key") == "auction_id"][0]["value"]).strip('"')
    )

    lst = dysond(
        "query", "whaleswap", "auctions", "--sell-denom", name, "--bid-denom", "udys"
    )
    ids = [int(a.get("auction_id")) for a in lst.get("auctions", [])]
    assert (
        auction_id in ids
    ), f"auction id not in filtered list: {json.dumps(lst, indent=2)}"

    redeem = dysond(
        "tx",
        "whaleswap",
        "redeem-auction",
        "--auction-id",
        str(auction_id),
        "--from",
        seller_name,
    )
    assert redeem.get("code", 1) == 0

    q = dysond("query", "whaleswap", "auction", "--auction-id", str(auction_id))
    assert isinstance(q, str), f"expected error string, got {type(q)}: {q}"
    assert "auction not found" in q, f"unexpected error string: {q}"

    lst2 = dysond(
        "query", "whaleswap", "auctions", "--sell-denom", name, "--bid-denom", "udys"
    )
    ids2 = [int(a.get("auction_id")) for a in lst2.get("auctions", [])]
    assert (
        auction_id not in ids2
    ), f"auction id still present after redeem: {json.dumps(lst2, indent=2)}"


def test_auctions_query_pagination_filters_strict(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [seller_a_name, seller_a_addr] = generate_account("auc_qry_a")
    faucet(seller_a_addr, amount=2_000_000)
    [seller_b_name, seller_b_addr] = generate_account("auc_qry_b")
    faucet(seller_b_addr, amount=2_000_000)

    denom_s = register_name(dysond, seller_a_name, seller_a_addr, "200udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units_s = 120
    mint_fee_s = int(
        (Decimal(units_s) * Decimal(str(fee_per_unit))).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    mint_s = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units_s}{denom_s}",
        "--mint-fee",
        f"{mint_fee_s}udys",
        "--from",
        seller_a_name,
    )
    assert mint_s.get("code", 1) == 0

    open1 = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"50{denom_s}",
        "--from",
        seller_a_name,
    )
    assert open1.get("code", 1) == 0
    evs1 = [
        e
        for e in open1.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    aid1 = int(
        str(
            [a for a in evs1[0].get("attributes", []) if a.get("key") == "auction_id"][
                0
            ]["value"]
        ).strip('"')
    )

    open2 = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"30{denom_s}",
        "--from",
        seller_a_name,
    )
    assert open2.get("code", 1) == 0
    evs2 = [
        e
        for e in open2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    aid2 = int(
        str(
            [a for a in evs2[0].get("attributes", []) if a.get("key") == "auction_id"][
                0
            ]["value"]
        ).strip('"')
    )

    denom_t = register_name(dysond, seller_b_name, seller_b_addr, "200udys")
    units_t = 60
    mint_fee_t = int(
        (Decimal(units_t) * Decimal(str(fee_per_unit))).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    mint_t = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units_t}{denom_t}",
        "--mint-fee",
        f"{mint_fee_t}udys",
        "--from",
        seller_b_name,
    )
    assert mint_t.get("code", 1) == 0

    open3 = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"40{denom_t}",
        "--from",
        seller_b_name,
    )
    assert open3.get("code", 1) == 0
    evs3 = [
        e
        for e in open3.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    aid3 = int(
        str(
            [a for a in evs3[0].get("attributes", []) if a.get("key") == "auction_id"][
                0
            ]["value"]
        ).strip('"')
    )

    first = dysond(
        "query",
        "whaleswap",
        "auctions",
        "--sell-denom",
        denom_s,
        "--bid-denom",
        "udys",
        "--page-limit",
        "1",
    )
    ids_first = [int(a.get("auction_id")) for a in first.get("auctions", [])]
    assert ids_first == [
        min(aid1, aid2)
    ], f"page1 ids mismatch: {json.dumps(first, indent=2)}"
    page_key = first.get("pagination", {}).get("next_key")
    assert page_key, f"missing next_key on first page: {json.dumps(first, indent=2)}"

    second = dysond(
        "query",
        "whaleswap",
        "auctions",
        "--sell-denom",
        denom_s,
        "--bid-denom",
        "udys",
        "--page-limit",
        "1",
        "--page-key",
        page_key,
    )
    ids_second = [int(a.get("auction_id")) for a in second.get("auctions", [])]
    assert ids_second == [
        max(aid1, aid2)
    ], f"page2 ids mismatch: {json.dumps(second, indent=2)}"

    # After consuming 2 items with limit=1, next_key should be absent
    assert not second.get("pagination", {}).get(
        "next_key"
    ), f"expected no next_key after second page: {json.dumps(second, indent=2)}"
