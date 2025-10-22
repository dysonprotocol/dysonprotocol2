import json


def _take(offer_id, units):
    return {"take": {"offer_id": offer_id, "take_units": str(units)}}


def test_cli_events_indexing_trades(chainnet, ws_setup_env, ws_create_offer):
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    maker = env["acc2"]["name"]

    # Create offer and take 1 unit (unit_have=5a, unit_want=1b)
    oid = ws_create_offer(maker, have=f"10{a}", want=f"2{b}")
    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        "100udys",
        "--max-input",
        f"10{b}",
        "--op",
        json.dumps(_take(oid, 1)),
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert isinstance(tx, dict), f"bad tx result: {tx}"
    assert "code" in tx and tx["code"] == 0, f"tx failed: {json.dumps(tx, indent=2)}"

    # Query by taker (still works, uses TradesByTraderIndex internally)
    qt = dysond("query", "whaleswap", "trades-by-taker", f"--taker={taker_addr}")
    assert isinstance(qt, dict), f"bad taker query: {qt}"
    assert "trades" in qt, f"missing trades: {qt}"
    trades_taker = qt["trades"]
    assert isinstance(trades_taker, list), f"trades not list: {trades_taker}"
    assert (
        len(trades_taker) == 1
    ), f"expected 1 trade for taker, got {len(trades_taker)}: {trades_taker}"
    t0 = trades_taker[0]

    # Validate new Trade structure
    assert "trade_id" in t0, f"missing trade_id: {json.dumps(t0, indent=2)}"
    assert "trader" in t0, f"missing trader: {json.dumps(t0, indent=2)}"
    assert "operations" in t0, f"missing operations: {json.dumps(t0, indent=2)}"
    assert "total_sent" in t0, f"missing total_sent: {json.dumps(t0, indent=2)}"
    assert "total_received" in t0, f"missing total_received: {json.dumps(t0, indent=2)}"

    trade_id = int(t0["trade_id"])
    assert trade_id > 0
    assert t0["trader"] == taker_addr

    # Validate operation contains offer_id (amino encoding wraps in Op.value)
    ops = t0.get("operations", [])
    assert len(ops) == 1, f"expected 1 operation: {json.dumps(ops, indent=2)}"
    op_val = ops[0].get("Op", {}).get("value", {})
    assert "take" in op_val, f"operation missing take: {json.dumps(ops[0], indent=2)}"
    assert int(op_val["take"]["offer_id"]) == oid

    # Validate totals are arrays with valid coins
    total_sent = t0.get("total_sent", [])
    total_recv = t0.get("total_received", [])
    assert len(total_sent) > 0, f"total_sent empty: {json.dumps(t0, indent=2)}"
    assert len(total_recv) > 0, f"total_received empty: {json.dumps(t0, indent=2)}"
    assert "denom" in total_sent[0] and "amount" in total_sent[0]
    assert "denom" in total_recv[0] and "amount" in total_recv[0]

    # Query by offer
    qo = dysond("query", "whaleswap", "trades-by-offer", "--offer-id", str(oid))
    assert isinstance(qo, dict), f"bad offer query: {qo}"
    assert "trades" in qo
    trades_offer = qo["trades"]
    assert isinstance(trades_offer, list)
    assert (
        len(trades_offer) == 1
    ), f"expected 1 trade for offer, got {len(trades_offer)}: {trades_offer}"
    o0 = trades_offer[0]
    assert "trade_id" in o0
    assert "trader" in o0
    assert "operations" in o0
    assert int(o0["trade_id"]) == trade_id
    assert o0["trader"] == taker_addr

    # Verify operation has offer_id (amino encoding)
    ops_o = o0.get("operations", [])
    assert len(ops_o) == 1
    op_o_val = ops_o[0].get("Op", {}).get("value", {})
    assert "take" in op_o_val
    assert int(op_o_val["take"]["offer_id"]) == oid

    # Query single trade
    q1 = dysond("query", "whaleswap", "trade", "--trade-id", str(trade_id))
    assert isinstance(q1, dict)
    assert "trade" in q1
    tr = q1["trade"]
    assert "trade_id" in tr
    assert "trader" in tr
    assert "operations" in tr
    assert int(tr["trade_id"]) == trade_id
    assert tr["trader"] == taker_addr

    # Verify operation structure (amino encoding)
    tr_ops = tr.get("operations", [])
    assert len(tr_ops) == 1
    tr_op_val = tr_ops[0].get("Op", {}).get("value", {})
    assert "take" in tr_op_val
    assert int(tr_op_val["take"]["offer_id"]) == oid
