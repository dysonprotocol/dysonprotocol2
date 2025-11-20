"""
PositionsByPool query handler coverage tests.

Tests the PositionsByPool query endpoint which lists all leverage positions
in a specific pool with optional status filter. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_positions_by_pool_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test PositionsByPool query with valid pool ID."""
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

    # Create position using multi-block transaction
    pos_result = dysond(
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
        pos_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(pos_result, indent=2)}"

    # Extract position_id from events
    pos_attrs = [
        attr.get("value")
        for event in pos_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert pos_attrs, f"position_id missing: {json.dumps(pos_result, indent=2)}"
    position_id = pos_attrs[0].strip('"')

    # Query positions by pool using CLI
    positions_response = dysond(
        "query", "whaleswap", "positions-by-pool", "--pool-id", pool_id
    )

    # Validate response structure (Type)
    assert isinstance(
        positions_response, dict
    ), f"PositionsByPool response should be dict, got {type(positions_response)}. Full response: {json.dumps(positions_response, indent=2)}"
    assert (
        "pagination" in positions_response
    ), f"PositionsByPool response missing 'pagination' key. Keys: {list(positions_response.keys())}. Full response: {json.dumps(positions_response, indent=2)}"

    # Validate positions list (Type + Shape)
    positions_list = positions_response.get("positions", [])
    assert isinstance(
        positions_list, list
    ), f"Positions should be list, got {type(positions_list)}. Full response: {json.dumps(positions_response, indent=2)}"

    # Verify position is in results
    position_ids_found = [int(p.get("position_id")) for p in positions_list]
    assert (
        int(position_id) in position_ids_found
    ), f"Position ID {position_id} not found in pool's positions. Found IDs: {position_ids_found}"

    # Validate pagination (Type)
    pagination = positions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_positions_by_pool_zero_id(chainnet):
    """Test PositionsByPool query with zero pool ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_positions_by_pool_zero():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionsByPoolRequest",
        "pool_id": 0
    })
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_positions_by_pool_zero",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for zero pool_id. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "pool_id required" in exception_str
    ), f"Expected 'pool_id required' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"


def test_positions_by_pool_no_positions(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test PositionsByPool query for pool with no positions."""
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

    # Query positions by pool (no positions yet)
    positions_response = dysond(
        "query", "whaleswap", "positions-by-pool", "--pool-id", pool_id
    )

    # Validate response structure (Type)
    assert isinstance(
        positions_response, dict
    ), f"PositionsByPool response should be dict, got {type(positions_response)}. Full response: {json.dumps(positions_response, indent=2)}"
    assert (
        "pagination" in positions_response
    ), f"PositionsByPool response missing 'pagination' key. Keys: {list(positions_response.keys())}. Full response: {json.dumps(positions_response, indent=2)}"

    # Validate positions list is empty (Type + Shape)
    positions_list = positions_response.get("positions", [])
    assert isinstance(
        positions_list, list
    ), f"Positions should be list, got {type(positions_list)}. Full response: {json.dumps(positions_response, indent=2)}"
    assert (
        len(positions_list) == 0
    ), f"Pool with no positions should return empty list. Got {len(positions_list)}: {json.dumps(positions_list, indent=2)}"

    # Validate pagination (Type)
    pagination = positions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_positions_by_pool_status_filter(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test PositionsByPool query with status filter."""
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

    # Create position using multi-block transaction
    pos_result = dysond(
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
        pos_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(pos_result, indent=2)}"

    # Query positions by pool with status filter using CLI
    positions_response = dysond(
        "query",
        "whaleswap",
        "positions-by-pool",
        "--pool-id",
        pool_id,
        "--status",
        "open",
    )

    # Validate response structure (Type)
    assert isinstance(
        positions_response, dict
    ), f"PositionsByPool response should be dict, got {type(positions_response)}. Full response: {json.dumps(positions_response, indent=2)}"
    assert (
        "pagination" in positions_response
    ), f"PositionsByPool response missing 'pagination' key. Keys: {list(positions_response.keys())}. Full response: {json.dumps(positions_response, indent=2)}"

    # Validate positions list (Type + Shape)
    positions_list = positions_response.get("positions", [])
    assert isinstance(
        positions_list, list
    ), f"Positions should be list, got {type(positions_list)}. Full response: {json.dumps(positions_response, indent=2)}"

    # Verify all positions have OPEN status
    for pos in positions_list:
        assert (
            pos.get("status") == "POSITION_STATUS_OPEN"
        ), f"Position {pos.get('position_id')} should be OPEN, got {pos.get('status')}"

    # Validate pagination (Type)
    pagination = positions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"
