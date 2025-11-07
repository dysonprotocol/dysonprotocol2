import json
import pytest


def test_cli_invariant_bug_part1_metrics_count_closed_offer_escrow(
    chainnet, ws_setup_env, ws_create_offer
):
    """
    Test that MakeTrade properly maintains invariants when closing offers.

    When MakeTrade closes an offer:
    - Offer status changes to "closed", remaining_have becomes 0
    - Coins are sent from module to taker (escrow released)
    - Metrics correctly exclude closed offer from escrowed_offer_coins

    This causes: module_balance == sum(metrics components)

    With fix (MakeTrade calls AssertInvariants): Test PASSES
    Module balances match metrics, closed offers properly excluded.
    """
    dysond = chainnet[0]
    env = ws_setup_env

    foo_denom = env["denoms"][0]
    bar_denom = env["denoms"][1]
    acc1_name = env["acc1"]["name"]
    acc2_name = env["acc2"]["name"]

    # Setup: pools + offer
    dysond(
        "tx",
        "bank",
        "send",
        env["acc3"]["addr"],
        env["acc1"]["addr"],
        f"200{foo_denom},200{bar_denom}",
        "--from",
        env["acc3"]["name"],
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
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        acc1_name,
    )

    offer_id = ws_create_offer(
        acc2_name, have=f"256{bar_denom}", want=f"256{foo_denom}"
    )

    # Close the offer via MakeTrade
    close_tx = dysond(
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
    assert close_tx["code"] == 0

    # Verify offer is closed
    offers = dysond("query", "whaleswap", "offers")
    closed = [o for o in offers["offers"] if o["offer_id"] == str(offer_id)][0]
    assert closed["status"] == "closed"
    assert closed["remaining_have"]["amount"] == "0"

    # Get actual module balance
    module_account = dysond("query", "auth", "module-account", "whaleswap")
    module_addr = module_account["account"]["value"]["address"]
    module_balances = dysond(
        "query", "bank", "balances", module_addr, "--page-limit", "1000"
    )
    actual = {b["denom"]: int(b["amount"]) for b in module_balances.get("balances", [])}

    # Get expected from metrics
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

    # FIXED: Module balance should match expected (closed offers excluded from metrics)
    bar_actual = actual.get(bar_denom, 0)
    bar_expected = expected.get(bar_denom, 0)

    assert (
        bar_actual == bar_expected
    ), f"Module balance mismatch after closing offer. module={bar_actual} expected={bar_expected}. Metrics offers: {json.dumps(m.get('escrowed_offer_coins', []))}"


def test_cli_invariant_bug_part2_make_offer_fails_after_closed_offer(
    chainnet, ws_setup_env, ws_create_offer
):
    """
    Test that MakeOffer succeeds after MakeTrade closes an offer.

    After MakeTrade closes an offer, creating a new offer should succeed:
    - MakeOffer calls AssertInvariants() after escrowing coins
    - Invariants pass because closed offers are excluded from metrics
    - New offer is created successfully

    With fix (MakeTrade calls AssertInvariants): Test PASSES
    MakeOffer succeeds after closed offers; closed-offer escrow is excluded
    from metrics and invariants hold.
    """
    dysond = chainnet[0]
    env = ws_setup_env

    foo_denom = env["denoms"][0]
    bar_denom = env["denoms"][1]
    acc1_name = env["acc1"]["name"]
    acc2_name = env["acc2"]["name"]

    # Setup: pools + offer
    dysond(
        "tx",
        "bank",
        "send",
        env["acc3"]["addr"],
        env["acc1"]["addr"],
        f"200{foo_denom},200{bar_denom}",
        "--from",
        env["acc3"]["name"],
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
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        acc1_name,
    )

    offer_id = ws_create_offer(
        acc2_name, have=f"256{bar_denom}", want=f"256{foo_denom}"
    )

    # Close the offer via MakeTrade
    close_tx = dysond(
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
    assert close_tx["code"] == 0

    # With the invariant fix, creating a new offer should succeed without
    # module balance mismatch related to the previously closed offer.
    new_offer_tx = ws_create_offer(
        acc2_name, have=f"10{bar_denom}", want=f"10{foo_denom}"
    )


def test_cli_invariant_make_trade_should_call_assert_invariants(
    chainnet, ws_setup_env, ws_create_offer
):
    """
    Test ensuring MakeTrade maintains module balance invariants.

    Verifies that after MakeTrade operations involving both pools and offers,
    the module account balances correctly reflect all components.

    Currently PASSING: module balances are correct even though MakeTrade
    only calls AssertAMMInvariants() and not the full AssertInvariants().
    """
    dysond = chainnet[0]
    env = ws_setup_env

    foo_denom = env["denoms"][0]
    bar_denom = env["denoms"][1]
    acc1_name = env["acc1"]["name"]
    acc2_name = env["acc2"]["name"]

    # Setup liquidity
    dysond(
        "tx",
        "bank",
        "send",
        env["acc2"]["addr"],
        env["acc1"]["addr"],
        f"100{foo_denom},100{bar_denom}",
        "--from",
        acc2_name,
    )

    pool_tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"50{foo_denom}",
        "--coins",
        f"50{bar_denom}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        acc1_name,
    )
    assert pool_tx["code"] == 0

    offer_id = ws_create_offer(acc2_name, have=f"10{bar_denom}", want=f"10{foo_denom}")

    # Partial take from offer
    trade_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"5{foo_denom}",
        "--op",
        json.dumps({"take": {"offer_id": str(offer_id), "take_units": "5"}}),
        "--min-output",
        f"1{bar_denom}",
        "--from",
        acc1_name,
    )
    assert trade_tx["code"] == 0

    # Verify module balance invariants are maintained
    module_account = dysond("query", "auth", "module-account", "whaleswap")
    module_addr = module_account["account"]["value"]["address"]
    module_balances = dysond(
        "query", "bank", "balances", module_addr, "--page-limit", "1000"
    )
    actual = {b["denom"]: int(b["amount"]) for b in module_balances.get("balances", [])}

    metrics = dysond("query", "whaleswap", "metrics")
    m = metrics.get("metrics", {})
    expected_pool = m.get("escrowed_pool_coins", [])
    expected_offer = m.get("escrowed_offer_coins", [])
    expected_liquid = m.get("escrowed_liquid_coins", [])
    expected_auction = m.get("escrowed_auction_coins", [])

    expected = {}
    for coin_list in [expected_pool, expected_offer, expected_liquid, expected_auction]:
        for coin in coin_list:
            denom = coin["denom"]
            amount = int(coin["amount"])
            expected[denom] = expected.get(denom, 0) + amount

    # Assert module balances == expected components for denoms used in this test only
    # (avoid false failures from residual state left by other tests)
    test_denoms = {foo_denom, bar_denom}
    for denom in test_denoms:
        exp = expected.get(denom, 0)
        act = actual.get(denom, 0)
        assert (
            exp == act
        ), f"Module balance mismatch for {denom}: module={act} expected={exp}"
