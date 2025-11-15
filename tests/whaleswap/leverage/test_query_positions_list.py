"""
Test PositionsByAddress and PositionsByPool queries for leverage positions.

Tests that:
1. When status is unspecified, all positions are returned (OPEN, CLOSED, LIQUIDATED)
2. When status is specified, only positions with that status are returned
"""

import json
import pytest
from deep_parse import deep_parse


def test_positions_by_address_all_statuses(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test PositionsByAddress returns all positions when status is unspecified."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool using multi-block transaction
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert (
        pool_result.get("code", 1) == 0
    ), f"create-pool failed: {json.dumps(pool_result, indent=2)}"

    # Extract pool_id from events
    pool_events = [
        e
        for e in pool_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_events, f"missing EventPoolCreated: {json.dumps(pool_result, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    # Create position 1
    pos1_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"750{bar_name}",
        "--borrow",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        pos1_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(pos1_result, indent=2)}"

    pos1_attrs = [
        attr.get("value")
        for event in pos1_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert pos1_attrs, f"position_id missing: {json.dumps(pos1_result, indent=2)}"
    pos1_id = pos1_attrs[0].strip('"')

    # Create position 2
    pos2_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"600{bar_name}",
        "--borrow",
        f"400{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        pos2_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(pos2_result, indent=2)}"

    pos2_attrs = [
        attr.get("value")
        for event in pos2_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert pos2_attrs, f"position_id missing: {json.dumps(pos2_result, indent=2)}"
    pos2_id = pos2_attrs[0].strip('"')

    # Wait for block delay, then close position 1
    # Use close-position for full close
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        pos1_id,
        "--fraction",
        "1.0",
        "--from",
        alice_name,
    )
    assert (
        close_result.get("code", 1) == 0
    ), f"close-position failed: {json.dumps(close_result, indent=2)}"

    # Query all positions (status unspecified) - should return both OPEN and CLOSED
    # Filter by pool_id to avoid state leakage from other tests
    all_positions = dysond(
        "query",
        "whaleswap",
        "positions-by-address",
        "--address",
        alice_addr,
        "--pool-id",
        pool_id,
    )
    assert isinstance(
        all_positions, dict
    ), f"All positions should be dict, got {type(all_positions)}"
    assert (
        "positions" in all_positions
    ), f"Missing 'positions' key. Keys: {list(all_positions.keys())}"

    all_pos_list = all_positions["positions"]

    assert isinstance(
        all_pos_list, list
    ), f"Positions should be list, got {type(all_pos_list)}"

    assert (
        len(all_pos_list) == 2
    ), f"Should return 2 positions (one OPEN, one CLOSED when status unspecified), got {len(all_pos_list)}"

    # Verify one OPEN and one CLOSED
    open_count = sum(
        1 for pos in all_pos_list if pos.get("borrowed", {}).get("amount", "0") != "0"
    )
    closed_count = sum(
        1 for pos in all_pos_list if pos.get("borrowed", {}).get("amount", "0") == "0"
    )
    assert open_count == 1, f"Expected 1 OPEN position, got {open_count}"
    assert closed_count == 1, f"Expected 1 CLOSED position, got {closed_count}"

    # Query only OPEN positions
    # Filter by pool_id to avoid state leakage from other tests
    open_positions = dysond(
        "query",
        "whaleswap",
        "positions-by-address",
        "--address",
        alice_addr,
        "--pool-id",
        pool_id,
        "--status",
        "open",
    )
    open_pos_list = open_positions["positions"]
    assert isinstance(
        open_pos_list, list
    ), f"Open positions should be list, got {type(open_pos_list)}"
    assert (
        len(open_pos_list) == 1
    ), f"Should return 1 OPEN position, got {len(open_pos_list)}"
    assert (
        open_pos_list[0]["status"] == "POSITION_STATUS_OPEN"
    ), f"Position should be OPEN, got {open_pos_list[0]['status']}"

    # Query only CLOSED positions - should return 1 since retained with status CLOSED
    # Filter by pool_id to avoid state leakage from other tests
    closed_positions = dysond(
        "query",
        "whaleswap",
        "positions-by-address",
        "--address",
        alice_addr,
        "--pool-id",
        pool_id,
        "--status",
        "closed",
    )
    closed_pos_list = closed_positions["positions"]
    assert isinstance(
        closed_pos_list, list
    ), f"Closed positions should be list, got {type(closed_pos_list)}"
    assert (
        len(closed_pos_list) == 1
    ), f"Should return 1 CLOSED position (retained after close), got {len(closed_pos_list)}"
    assert (
        closed_pos_list[0]["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be CLOSED, got {closed_pos_list[0]['status']}"


def test_positions_by_pool_all_statuses(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test PositionsByPool returns all positions when status is unspecified."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool using multi-block transaction
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert (
        pool_result.get("code", 1) == 0
    ), f"create-pool failed: {json.dumps(pool_result, indent=2)}"

    # Extract pool_id from events
    pool_events = [
        e
        for e in pool_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_events, f"missing EventPoolCreated: {json.dumps(pool_result, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    # Create position 1
    pos1_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"750{bar_name}",
        "--borrow",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        pos1_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(pos1_result, indent=2)}"

    pos1_attrs = [
        attr.get("value")
        for event in pos1_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert pos1_attrs, f"position_id missing: {json.dumps(pos1_result, indent=2)}"
    pos1_id = pos1_attrs[0].strip('"')

    # Create position 2
    pos2_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"600{bar_name}",
        "--borrow",
        f"400{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        pos2_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(pos2_result, indent=2)}"

    pos2_attrs = [
        attr.get("value")
        for event in pos2_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert pos2_attrs, f"position_id missing: {json.dumps(pos2_result, indent=2)}"
    pos2_id = pos2_attrs[0].strip('"')

    # Wait for block delay, then close position 2
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        pos2_id,
        "--fraction",
        "1.0",
        "--from",
        alice_name,
    )
    assert (
        close_result.get("code", 1) == 0
    ), f"close-position failed: {json.dumps(close_result, indent=2)}"

    # Query all positions (status unspecified) - should return both OPEN and CLOSED
    all_positions = dysond(
        "query",
        "whaleswap",
        "positions-by-pool",
        "--pool-id",
        pool_id,
    )
    assert isinstance(
        all_positions, dict
    ), f"All positions should be dict, got {type(all_positions)}"
    assert (
        "positions" in all_positions
    ), f"Missing 'positions' key. Keys: {list(all_positions.keys())}"

    all_pos_list = all_positions["positions"]
    assert isinstance(
        all_pos_list, list
    ), f"Positions should be list, got {type(all_pos_list)}"
    assert (
        len(all_pos_list) == 2
    ), f"Should return 2 positions (one OPEN, one CLOSED when status unspecified), got {len(all_pos_list)}"

    # Verify one OPEN and one CLOSED
    open_count = sum(
        1 for pos in all_pos_list if pos.get("borrowed", {}).get("amount", "0") != "0"
    )
    closed_count = sum(
        1 for pos in all_pos_list if pos.get("borrowed", {}).get("amount", "0") == "0"
    )
    assert open_count == 1, f"Expected 1 OPEN position, got {open_count}"
    assert closed_count == 1, f"Expected 1 CLOSED position, got {closed_count}"

    # Query only OPEN positions
    open_positions = dysond(
        "query",
        "whaleswap",
        "positions-by-pool",
        "--pool-id",
        pool_id,
        "--status",
        "open",
    )
    open_pos_list = open_positions["positions"]
    assert isinstance(
        open_pos_list, list
    ), f"Open positions should be list, got {type(open_pos_list)}"
    assert (
        len(open_pos_list) == 1
    ), f"Should return 1 OPEN position, got {len(open_pos_list)}"
    assert (
        open_pos_list[0]["status"] == "POSITION_STATUS_OPEN"
    ), f"Position should be OPEN, got {open_pos_list[0]['status']}"

    # Query only CLOSED positions - should return 1 since retained with status CLOSED
    closed_positions = dysond(
        "query",
        "whaleswap",
        "positions-by-pool",
        "--pool-id",
        pool_id,
        "--status",
        "closed",
    )
    closed_pos_list = closed_positions["positions"]
    assert isinstance(
        closed_pos_list, list
    ), f"Closed positions should be list, got {type(closed_pos_list)}"
    assert (
        len(closed_pos_list) == 1
    ), f"Should return 1 CLOSED position (retained after close), got {len(closed_pos_list)}"
    assert (
        closed_pos_list[0]["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be CLOSED, got {closed_pos_list[0]['status']}"
