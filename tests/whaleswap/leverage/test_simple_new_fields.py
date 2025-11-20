"""
Simple test to verify new leverage fields are working.
"""

import json


def test_simple_new_fields(chainnet, leverage_accounts, leverage_names_and_coins):
    """Simple test that new fields are set correctly."""
    dysond = chainnet[0]
    trader_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool with both denoms - using proper DecCoin format
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"5000{foo_name}",
        "--coins",
        f"5000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        trader_name,
    )
    assert pool_result["code"] == 0, f"Pool creation failed: {pool_result}"

    # Extract pool ID from events using list comprehension pattern (like existing tests)
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_id_attrs, f"pool_id not found: {json.dumps(pool_result, indent=2)}"
    pool_id = int(pool_id_attrs[0].strip('"'))

    # Open leverage position
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        str(pool_id),
        "--collateral",
        f"1000{foo_name}",
        "--borrow",
        f"500{bar_name}",
        "--from",
        trader_name,
    )
    assert open_result["code"] == 0, f"Position opening failed: {open_result}"

    # Extract position ID from events using list comprehension pattern
    position_opened_events = [
        event
        for event in open_result.get("events", [])
        if event.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert position_opened_events, (
        f"EventLeveragePositionOpened missing: {json.dumps(open_result, indent=2)}"
    )

    position_id_attrs = [
        attr.get("value")
        for event in position_opened_events
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
    ]
    assert position_id_attrs, (
        f"position_id missing: {json.dumps(position_opened_events[0], indent=2)}"
    )
    position_id = int(position_id_attrs[0].strip('"'))

    # Query the position to verify new fields
    position_result = dysond(
        "query",
        "whaleswap",
        "position",
        "--position-id",
        str(position_id),
    )

    position = position_result["position"]

    # Verify new fields are set correctly
    assert position["initial_held"]["denom"] == foo_name, (
        f"initial_held denom should be {foo_name}"
    )
    assert int(position["initial_held"]["amount"]) > 0, (
        "initial_held amount should be positive"
    )

    assert position["initial_collateral"]["denom"] == foo_name, (
        f"initial_collateral denom should be {foo_name}"
    )
    assert int(position["initial_collateral"]["amount"]) == 1000, (
        "initial_collateral amount should match collateral"
    )

    # Verify interest_rate format - it might be string for zero values or dict for non-zero
    interest_rate_value = position["interest_rate"]
    print(f"DEBUG: interest_rate value: {interest_rate_value}")
    print(f"DEBUG: interest_rate type: {type(interest_rate_value)}")

    # For new positions with default/zero interest rate, check the format
    borrowed_denom = position["borrowed"]["denom"]
    interest_rate_str = str(interest_rate_value)

    # The interest rate should contain the borrowed denom and be zero
    assert borrowed_denom in interest_rate_str, (
        f"interest_rate should contain borrowed denom {borrowed_denom}, got: {interest_rate_str}"
    )
    assert "0.000000000000000000" in interest_rate_str, (
        f"interest_rate should be zero for new position: {interest_rate_str}"
    )

    # Verify accrued_interest_remainder is now DecCoin format
    remainder_value = position["accrued_interest_remainder"]
    remainder_str = str(remainder_value)

    # The remainder should contain the borrowed denom and be zero
    assert borrowed_denom in remainder_str, (
        f"accrued_interest_remainder should contain borrowed denom {borrowed_denom}, got: {remainder_str}"
    )
    assert "0.000000000000000000" in remainder_str, (
        f"accrued_interest_remainder should be zero for new position: {remainder_str}"
    )
