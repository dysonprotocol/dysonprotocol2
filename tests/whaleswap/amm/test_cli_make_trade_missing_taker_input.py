import json


def test_cli_make_trade_missing_taker_input_accounting(
    chainnet, ws_setup_env, ws_create_offer
):
    """
    Regression test for previous MakeTrade accounting bug around Take operations.

    Status: FIXED. MakeTrade now nets taker credits and covers maker wants via
    tradeNetAndCover. The module balance invariants pass and the transaction
    should succeed.
    """
    dysond = chainnet[0]
    env = ws_setup_env

    foo_denom = env["denoms"][0]
    bar_denom = env["denoms"][1]
    acc1_name = env["acc1"]["name"]
    acc2_name = env["acc2"]["name"]
    acc3_name = env["acc3"]["name"]

    # Create pool first (this adds to the complexity like your live system)
    dysond(
        "tx",
        "bank",
        "send",
        env["acc3"]["addr"],
        env["acc1"]["addr"],
        f"200{foo_denom},200{bar_denom}",
        "--from",
        acc3_name,
    )

    dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"50{foo_denom}",
        "--coins",
        f"30{bar_denom}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        acc1_name,
    )

    # Create LARGE offer matching your live system: acc2 offers bar, wants foo
    offer_id = ws_create_offer(
        acc2_name, have=f"256{bar_denom}", want=f"256{foo_denom}"
    )

    # Take from the offer: Alice sends foo, receives bar
    # BUG: MakeTrade handler (lines 82-93) doesn't call addIn(trader, makerWant)
    # This means: module sends foo to maker without recording taker sent it
    # Result: module balance decreases but inputsByAddr doesn't track it
    trade_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"256{foo_denom}",
        "--op",
        json.dumps({"take": {"offer_id": str(offer_id), "take_units": ""}}),
        "--min-output",
        f"1{bar_denom}",
        "--from",
        acc1_name,
    )

    # With the fix: addIn(trader, makerWant) properly records taker's input
    # Transaction should succeed with correct accounting
    assert trade_tx["code"] == 0, f"Trade failed: {trade_tx.get('raw_log', 'N/A')}"

    # Verify module balance invariants are maintained
    module_account = dysond("query", "auth", "module-account", "whaleswap")
    module_addr = module_account["account"]["value"]["address"]
    module_balances = dysond(
        "query", "bank", "balances", module_addr, "--page-limit", "1000"
    )
    actual = {b["denom"]: int(b["amount"]) for b in module_balances.get("balances", [])}

    metrics = dysond("query", "whaleswap", "metrics")
    m = metrics.get("metrics", {})
    expected = {}
    for coin_list in [
        m.get("escrowed_pool_coins", []),
        m.get("escrowed_offer_coins", []),
        m.get("escrowed_liquid_coins", []),
        m.get("escrowed_auction_coins", []),
    ]:
        for coin in coin_list:
            denom = coin["denom"]
            amount = int(coin["amount"])
            expected[denom] = expected.get(denom, 0) + amount

    # Verify accounting is correct for denoms used in this test only
    # (avoid false failures from residual state left by other tests)
    test_denoms = {foo_denom, bar_denom}
    for denom in test_denoms:
        exp = expected.get(denom, 0)
        act = actual.get(denom, 0)
        assert (
            exp == act
        ), f"Module balance mismatch for {denom}: module={act} expected={exp}"
