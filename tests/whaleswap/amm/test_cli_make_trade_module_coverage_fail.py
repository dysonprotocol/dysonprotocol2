import json


def _take(offer_id, units):
    return {"take": {"offer_id": offer_id, "take_units": str(units)}}


def test_make_trade_module_coverage_fail(chainnet, ws_setup_env, ws_create_offer):
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    maker = env["acc2"]["name"]
    drain_rcpt = env["acc3"]["addr"]

    # Drain ALL B from taker (base only; no liquid wrappers)
    txd = dysond(
        "tx",
        "bank",
        "send",
        taker_name,
        drain_rcpt,
        f"300{b}",
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert txd.get("code", 1) == 0, f"drain failed: {json.dumps(txd, indent=2)}"

    # Offer requiring 90 B per unit
    oid = ws_create_offer(maker, have=f"10{a}", want=f"900{b}")

    # Attempt take (no B available): expect failure due to insufficient taker base B
    out = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        json.dumps(_take(oid, 1)),
        "--from",
        taker_name,
        "--gas",
        "auto",
        raw=True,
    )
    assert isinstance(out, str), f"expected raw error string, got {type(out)}: {out}"
    low = out.lower()
    expected = f"insufficient inputs for {b}".lower()
    assert expected in low, f"missing expected insufficient inputs for {b} error: {out}"
