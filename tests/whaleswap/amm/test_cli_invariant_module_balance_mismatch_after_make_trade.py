import json


def _parse_offer_id(tx):
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    assert (
        len(evs) == 1
    ), f"missing/ambiguous EventOfferCreated: {json.dumps(tx, indent=2)}"
    attrs = {a.get("key"): a.get("value") for a in evs[0].get("attributes", [])}
    return int(json.loads(attrs["offer_id"]))


def test_invariant_module_balance_mismatch_after_make_trade(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    # Use the first two solid denoms; call them bar, foo to mirror the report
    bar = env["denoms"][0]
    foo = env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    maker_name = env["acc2"]["name"]
    drain_rcpt = env["acc3"]["addr"]

    # Liquid denom helper (used in debug snapshots)
    lbar = "whaleswap.dys/coins/" + bar

    # Unconditional pre-offer debug snapshot to aid diagnosis when invariants fail later.
    # - Whaleswap module address and balances (all denoms)
    # - Whaleswap metrics (amm, escrow, pfand, auctions, liquid_backing)
    # - Current pools (if any)
    mod_acct = dysond("query", "auth", "module-account", "whaleswap")
    mod_addr = (
        mod_acct.get("account", {}).get("base_account", {}).get("address")
        or mod_acct.get("account", {}).get("address")
        or ""
    )
    mod_balances = dysond("query", "bank", "balances", mod_addr) if mod_addr else {}
    ws_metrics = dysond("query", "whaleswap", "metrics")
    ws_pools = dysond("query", "whaleswap", "pools")
    pre_offer_debug = {
        "bar": bar,
        "lbar": lbar,
        "module_addr": mod_addr,
        "module_balances": mod_balances,
        "metrics": ws_metrics,
        "pools": ws_pools,
    }

    # Maker escrows bar via a normal offer so module holds bar as escrow
    mk1 = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"256{bar}",
        "--want",
        f"256{foo}",
        "--from",
        maker_name,
    )
    assert mk1.get("code", 1) == 0, "make-offer(escrow bar) failed: " + json.dumps(
        {
            "tx": mk1,
            "pre_offer_debug": pre_offer_debug,
        },
        indent=2,
    )
    oid_escrow_bar = _parse_offer_id(mk1)
    assert oid_escrow_bar > 0

    # Execute a trade that requires paying bar (module will cover since taker has none)
    # Maker creates a second offer want=bar so taker takes it, forcing coverage of bar
    mk2 = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"100{foo}",
        "--want",
        f"100{bar}",
        "--from",
        maker_name,
    )
    assert (
        mk2.get("code", 1) == 0
    ), f"make-offer(want bar) failed: {json.dumps(mk2, indent=2)}"
    oid_want_bar = _parse_offer_id(mk2)

    op_take = {"take": {"offer_id": oid_want_bar, "take_units": ""}}  # full take
    tx_trade = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"100{bar}",
        "--op",
        json.dumps(op_take),
        "--min-output",
        f"1{foo}",
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert (
        tx_trade.get("code", 1) == 0
    ), f"make-trade failed: {json.dumps(tx_trade, indent=2)}"

    # Trigger invariant check by attempting another MakeOffer; expect module-balance mismatch mentioning bar.dys
    out = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"1{foo}",
        "--want",
        f"1{bar}",
        "--from",
        maker_name,
        "--gas",
        "auto",
        "--yes",
        raw=True,
    )
    assert isinstance(out, str), f"expected error string, got: {out}"
    low = (out or "").lower()
    # The keeper error message includes this exact prefix when invariant splits parts
    assert (
        "module balance mismatch for" in low and bar.lower() in low
    ), f"expected invariant module-balance mismatch mentioning {bar}, got: {out}"
