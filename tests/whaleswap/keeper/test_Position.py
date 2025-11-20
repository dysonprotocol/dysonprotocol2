"""
Position query handler coverage tests.

Tests the Position query endpoint which retrieves a leverage position by ID
with comprehensive health and interest information. Covers success paths,
validation errors, and health status calculations.
"""

import json
import pytest
from deep_parse import deep_parse


def test_position_success_open(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Position query with open position."""
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
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert pos_attrs, f"position_id missing: {json.dumps(pos_result, indent=2)}"
    position_id = pos_attrs[0].strip('"')

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = f"""
from dys import _query

def demo_position_success():
    position_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": {position_id}
    }})
    return position_resp
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
        "demo_position_success",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    position_resp = demo_result

    # Validate response structure (Type)
    assert isinstance(
        position_resp, dict
    ), f"Position response should be dict, got {type(position_resp)}. Full response: {json.dumps(position_resp, indent=2)}"

    # Validate response structure (Shape)
    assert (
        "position" in position_resp
    ), f"Position response missing 'position' key. Keys: {list(position_resp.keys())}"
    assert (
        "health_status" in position_resp
    ), f"Position response missing 'health_status' key. Keys: {list(position_resp.keys())}"
    assert (
        "current_collateral_ratio" in position_resp
    ), f"Position response missing 'current_collateral_ratio' key. Keys: {list(position_resp.keys())}"
    assert (
        "liquidation_threshold" in position_resp
    ), f"Position response missing 'liquidation_threshold' key. Keys: {list(position_resp.keys())}"
    assert (
        "borrowed" in position_resp
    ), f"Position response missing 'borrowed' key. Keys: {list(position_resp.keys())}"
    assert (
        "can_close_by_owner" in position_resp
    ), f"Position response missing 'can_close_by_owner' key. Keys: {list(position_resp.keys())}"
    assert (
        "can_initialize_liquidation" in position_resp
    ), f"Position response missing 'can_initialize_liquidation' key. Keys: {list(position_resp.keys())}"
    assert (
        "can_finalize_liquidation" in position_resp
    ), f"Position response missing 'can_finalize_liquidation' key. Keys: {list(position_resp.keys())}"
    assert (
        "interest" in position_resp
    ), f"Position response missing 'interest' key. Keys: {list(position_resp.keys())}"

    # Validate position details (Type + Values)
    position = position_resp["position"]
    assert isinstance(position, dict), f"Position should be dict, got {type(position)}"
    assert int(position["position_id"]) == int(position_id), f"Position ID mismatch: expected {position_id}, got {position['position_id']}"
    assert position["pool_id"] == pool_id, f"Pool ID mismatch: expected {pool_id}, got {position['pool_id']}"
    assert position["user"] == alice_addr, f"User address mismatch: expected {alice_addr}, got {position['user']}"

    # Validate collateral (Type + Shape + Values)
    assert "collateral" in position, f"Position missing 'collateral' key. Keys: {list(position.keys())}"
    collateral = position["collateral"]
    assert collateral["denom"] == bar_name, f"Collateral denom mismatch: expected {bar_name}, got {collateral['denom']}"
    assert collateral["amount"] == "750", f"Collateral amount mismatch: expected '750', got {collateral['amount']}"

    # Validate borrowed amount (Type + Shape + Values)
    borrowed = position_resp["borrowed"]
    assert borrowed["denom"] == foo_name, f"Borrowed denom mismatch: expected {foo_name}, got {borrowed['denom']}"
    assert borrowed["amount"] == "500", f"Borrowed amount mismatch: expected '500', got {borrowed['amount']}"

    # Validate health status (Type)
    health_status = position_resp["health_status"]
    assert isinstance(health_status, str), f"Health status should be string, got {type(health_status)}"

    # Validate numeric fields are strings (cosmos.Dec format)
    assert isinstance(
        position_resp["current_collateral_ratio"], str
    ), f"Current collateral ratio should be string, got {type(position_resp['current_collateral_ratio'])}"
    assert isinstance(
        position_resp["liquidation_threshold"], str
    ), f"Liquidation threshold should be string, got {type(position_resp['liquidation_threshold'])}"

    # Validate boolean fields
    assert isinstance(
        position_resp["can_close_by_owner"], bool
    ), f"Can close by owner should be bool, got {type(position_resp['can_close_by_owner'])}"
    assert isinstance(
        position_resp["can_initialize_liquidation"], bool
    ), f"Can initialize liquidation should be bool, got {type(position_resp['can_initialize_liquidation'])}"
    assert isinstance(
        position_resp["can_finalize_liquidation"], bool
    ), f"Can finalize liquidation should be bool, got {type(position_resp['can_finalize_liquidation'])}"

    # Validate interest structure
    interest = position_resp["interest"]
    assert isinstance(interest, dict), f"Interest should be dict, got {type(interest)}"
    assert "interest_due" in interest, f"Interest missing 'interest_due' key. Keys: {list(interest.keys())}"
    assert "total_repayment" in interest, f"Interest missing 'total_repayment' key. Keys: {list(interest.keys())}"
    assert "time_elapsed" in interest, f"Interest missing 'time_elapsed' key. Keys: {list(interest.keys())}"
    assert "annual_rate" in interest, f"Interest missing 'annual_rate' key. Keys: {list(interest.keys())}"


def test_position_zero_id(chainnet):
    """Test Position query with zero position ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_position_zero_id():
    try:
        position_resp = _query({
            "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
            "position_id": 0
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_position_zero_id",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    assert demo_result.get("expected") is True, f"Expected error for zero position_id. Result: {json.dumps(demo_result, indent=2)}"


def test_position_not_found(chainnet):
    """Test Position query with non-existent position ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_position_not_found():
    try:
        position_resp = _query({
            "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
            "position_id": 99999
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_position_not_found",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    assert demo_result.get("expected") is True, f"Expected error for non-existent position. Result: {json.dumps(demo_result, indent=2)}"

