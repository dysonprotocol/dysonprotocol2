import json
from decimal import Decimal, ROUND_CEILING


def test_trades_by_pool_lists_swaps_pagination(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]

    # Creator mints custom denom and creates a pool with udys
    [creator_name, creator_addr] = generate_account("amm_tr_pool_creator")
    faucet(creator_addr, amount=2_000_000)
    denom = register_name(dysond, creator_name, creator_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = Decimal(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = Decimal(1000)
    mint_fee = int((units * fee_per_unit).to_integral_value(rounding=ROUND_CEILING))
    mint = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{int(units)}{denom}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        creator_name,
    )
    assert mint.get("code", 1) == 0, f"mint-coins failed: {json.dumps(mint, indent=2)}"

    # Create a pool with 1000udys and 500 of custom denom
    create = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        "1000udys",
        "--coins",
        f"500{denom}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        creator_name,
    )
    assert create.get("code", 1) == 0, (
        f"create-pool failed: {json.dumps(create, indent=2)}"
    )

    # Extract pool_id from the create-pool transaction
    pool_events = [
        e
        for e in create.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_events, f"EventPoolCreated missing: {json.dumps(create, indent=2)}"
    pool_id_attrs = [
        a
        for e in pool_events
        for a in e.get("attributes", [])
        if a.get("key") == "pool_id"
    ]
    assert pool_id_attrs, (
        f"pool_id attribute missing: {json.dumps(pool_events, indent=2)}"
    )
    pool_id = int(pool_id_attrs[0].get("value", "").strip('"'))

    # Taker executes two swaps against the pool
    [taker_name, taker_addr] = generate_account("amm_tr_pool_taker")
    faucet(taker_addr, amount=2_000_000)

    # Swap 1: udys -> custom denom
    in1 = f"100udys"
    out1 = denom
    # parse amount/denom explicitly
    amt1 = "".join([c for c in in1 if c.isdigit()])
    den1 = in1[len(amt1) :]
    legs1 = json.dumps(
        {"swap": {"pool_id": pool_id, "swap_in": {"denom": den1, "amount": amt1}}}
    )
    swap1 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        in1,
        "--op",
        legs1,
        "--min-output",
        f"1{out1}",
        "--from",
        taker_name,
    )
    assert swap1.get("code", 1) == 0, f"swap1 failed: {json.dumps(swap1, indent=2)}"

    # Swap 2: custom denom -> udys
    in2 = f"20{denom}"
    out2 = "udys"
    amt2 = "".join([c for c in in2 if c.isdigit()])
    den2 = in2[len(amt2) :]
    legs2 = json.dumps(
        {"swap": {"pool_id": pool_id, "swap_in": {"denom": den2, "amount": amt2}}}
    )
    swap2 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        in2,
        "--op",
        legs2,
        "--min-output",
        f"1{out2}",
        "--from",
        taker_name,
    )
    assert swap2.get("code", 1) == 0, f"swap2 failed: {json.dumps(swap2, indent=2)}"

    # Paginate trades-by-pool strictly
    page1 = dysond(
        "query",
        "whaleswap",
        "trades-by-pool",
        "--pool-id",
        str(pool_id),
        "--page-limit",
        "1",
    )
    t1 = page1.get("trades", [])
    assert len(t1) == 1, f"page1 expected 1 trade: {json.dumps(page1, indent=2)}"
    next_key = page1.get("pagination", {}).get("next_key")
    assert next_key, f"expected next_key on page1: {json.dumps(page1, indent=2)}"

    page2 = dysond(
        "query",
        "whaleswap",
        "trades-by-pool",
        "--pool-id",
        str(pool_id),
        "--page-limit",
        "1",
        "--page-key",
        next_key,
    )
    t2 = page2.get("trades", [])
    assert len(t2) == 1, f"page2 expected 1 trade: {json.dumps(page2, indent=2)}"
    nk2 = page2.get("pagination", {}).get("next_key")

    # No third page should be available
    assert not nk2, f"unexpected next_key on last page: {json.dumps(page2, indent=2)}"

    trades = t1 + t2
    # Verify strict fields; order should be ascending by trade_id
    trades_sorted = sorted(trades, key=lambda x: int(x.get("trade_id")))
    # Map expected IO by order of creation
    expected = [
        {"sent": in1, "out_denom": out1},
        {"sent": in2, "out_denom": out2},
    ]
    for idx, tr in enumerate(trades_sorted):
        # Validate new Trade structure
        assert "trader" in tr, f"missing trader: {json.dumps(tr, indent=2)}"
        assert "operations" in tr, f"missing operations: {json.dumps(tr, indent=2)}"
        assert tr.get("trader") == taker_addr, (
            f"trader mismatch: {json.dumps(tr, indent=2)}"
        )

        # Extract pool_id from operations (amino encoding: Op.value.swap)
        ops = tr.get("operations", [])
        assert len(ops) == 1, (
            f"expected 1 operation per PoolSwap trade: {json.dumps(tr, indent=2)}"
        )
        op_val = ops[0].get("Op", {}).get("value", {})
        assert "swap" in op_val, (
            f"operation missing swap: {json.dumps(ops[0], indent=2)}"
        )
        assert int(op_val["swap"]["pool_id"]) == pool_id, (
            f"pool_id mismatch: {json.dumps(op_val, indent=2)}"
        )

        # Validate totals (now arrays)
        total_sent = tr.get("total_sent", [])
        total_recv = tr.get("total_received", [])
        assert len(total_sent) == 1, (
            f"expected 1 total_sent: {json.dumps(tr, indent=2)}"
        )
        assert len(total_recv) == 1, (
            f"expected 1 total_received: {json.dumps(tr, indent=2)}"
        )

        sent = total_sent[0]
        recv = total_recv[0]
        # Sent must match exactly the provided input
        exp_sent = expected[idx]["sent"]
        assert f"{sent.get('amount')}{sent.get('denom')}" == exp_sent, (
            f"sent coin mismatch: got={sent} exp={exp_sent} full={json.dumps(tr, indent=2)}"
        )
        # Received denom must match requested out-denom and amount must be positive
        assert recv.get("denom") == expected[idx]["out_denom"], (
            f"received denom mismatch: {json.dumps(tr, indent=2)}"
        )
        assert int(recv.get("amount")) > 0, (
            f"received amount must be > 0: {json.dumps(tr, indent=2)}"
        )
