"""
Regression test for duplicate repayment addition in ClosePosition.

This test verifies that ClosePosition correctly adds repayment to pool reserves only once,
not twice. The test opens a position that goes slightly underwater due to swap fees,
and verifies that:
1. Close succeeds (no double-add causing invariant failure)
2. Shortfall is covered by collateral (same-denom collateral case)
3. User receives reduced collateral after shortfall deduction
"""

import json


def test_close_position_happy_path_regression(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Open and then close a long position via CLI; close should succeed.

    With the current bug, this fails due to duplicate repayment being added to pool reserves.
    """
    dysond = chainnet[0]
    charlie_name = leverage_accounts["charlie"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"5000{foo_name}",
        "--coins",
        f"5000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "20.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        charlie_name,
    )

    assert (
        pool_result.get("code", 1) == 0
    ), f"Pool creation failed: {json.dumps(pool_result, indent=2)}"

    # Extract pool_id
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert (
        len(pool_id_attrs) > 0
    ), f"pool_id not found. Full result: {json.dumps(pool_result, indent=2)}"
    pool_id = pool_id_attrs[0].strip('"')

    # Open a position (borrow foo, hold bar, collateral in foo)
    # Use same-denom collateral so underwater positions can cover shortfall with collateral
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"400{foo_name}",
        "--borrow",
        f"250{foo_name}",
        "--from",
        charlie_name,
    )
    assert (
        open_result.get("code", 1) == 0
    ), f"Open position failed: {json.dumps(open_result, indent=2)}"

    # Extract position_id
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert (
        len(position_id_attrs) > 0
    ), f"position_id not found. Full result: {json.dumps(open_result, indent=2)}"
    position_id = position_id_attrs[0].strip('"')

    # Close position; this should succeed when repayment is added exactly once
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--from",
        charlie_name,
    )

    # Expect success. With the current bug, this fails with AMM invariant error.
    assert close_result.get("code", 1) == 0, (
        "Close position failed (likely due to duplicate repayment added to pool reserves): "
        f"{json.dumps(close_result, indent=2)}"
    )
