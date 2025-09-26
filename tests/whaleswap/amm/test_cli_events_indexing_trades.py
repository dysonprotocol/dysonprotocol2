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
        f"1{b}",
        "--op",
        json.dumps(_take(oid, 1)),
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert isinstance(tx, dict), f"bad tx result: {tx}"
    assert "code" in tx and tx["code"] == 0, f"tx failed: {json.dumps(tx, indent=2)}"

    # Query by taker
    qt = dysond("query", "whaleswap", "trades-by-taker", taker_addr)
    assert isinstance(qt, dict), f"bad taker query: {qt}"
    assert "trades" in qt, f"missing trades: {qt}"
    trades_taker = qt["trades"]
    assert isinstance(trades_taker, list), f"trades not list: {trades_taker}"
    assert (
        len(trades_taker) == 1
    ), f"expected 1 trade for taker, got {len(trades_taker)}: {trades_taker}"
    t0 = trades_taker[0]
    for k in ["trade_id", "offer_id", "taker", "sent", "received"]:
        assert k in t0, f"missing {k}: {t0}"
    trade_id = int(t0["trade_id"])
    assert trade_id > 0
    assert int(t0["offer_id"]) == oid
    assert t0["taker"] == taker_addr
    assert "denom" in t0["sent"] and "amount" in t0["sent"]
    assert "denom" in t0["received"] and "amount" in t0["received"]

    # Query by offer
    qo = dysond("query", "whaleswap", "trades-by-offer", str(oid))
    assert isinstance(qo, dict), f"bad offer query: {qo}"
    assert "trades" in qo
    trades_offer = qo["trades"]
    assert isinstance(trades_offer, list)
    assert (
        len(trades_offer) == 1
    ), f"expected 1 trade for offer, got {len(trades_offer)}: {trades_offer}"
    o0 = trades_offer[0]
    for k in ["trade_id", "offer_id", "taker"]:
        assert k in o0
    assert int(o0["trade_id"]) == trade_id
    assert int(o0["offer_id"]) == oid
    assert o0["taker"] == taker_addr

    # Query single trade
    q1 = dysond("query", "whaleswap", "trade", str(trade_id))
    assert isinstance(q1, dict)
    assert "trade" in q1
    tr = q1["trade"]
    for k in ["trade_id", "offer_id", "taker", "sent", "received"]:
        assert k in tr
    assert int(tr["trade_id"]) == trade_id
    assert int(tr["offer_id"]) == oid
    assert tr["taker"] == taker_addr
