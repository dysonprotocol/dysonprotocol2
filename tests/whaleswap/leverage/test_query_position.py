"""
Test Position query for leverage positions.

Tests the QueryPosition endpoint which retrieves a single position by ID
with health status, collateral ratio, and liquidation information.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_query_position_basic(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test basic Position query functionality."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_position_query(alice_addr, foo_name, bar_name):
    # Create pool
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "20.0"},
            {"denom": quote, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]

    # Create position
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })

    position_result = sudo_position_result["results"][0]
    position_id = position_result["position_id"]  # Extract from response, don't hardcode!

    # Query the position
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)  # Convert to int for query
    })

    return {
        "pool_id": pool_id,
        "position_id": position_id,
        "position_query": position_query
    }
"""
    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
    )
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_position_query",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"

    print(f"Full query_result: {json.dumps(query_result, indent=2)}")
    print(f"Deep parsed result: {json.dumps(result, indent=2)}")

    assert (
        result is not None
    ), f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    # The actual script result is nested under result["result"]["result"]
    demo_result = result["result"]["result"]

    # Check for exceptions in execution
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    # Verify script returned expected structure
    assert (
        demo_result.get("pool_id") is not None
    ), f"Script should return pool_id. Result: {json.dumps(demo_result, indent=2)}"
    assert (
        demo_result.get("position_id") is not None
    ), f"Script should return position_id. Result: {json.dumps(demo_result, indent=2)}"
    assert (
        demo_result.get("position_query") is not None
    ), f"Script should return position_query. Result: {json.dumps(demo_result, indent=2)}"

    # Extract the position query response
    position_query = demo_result["position_query"]

    # Verify the query response structure
    assert isinstance(position_query, dict), f"Position query should return dict, got {type(position_query)}"
    assert "position" in position_query, f"Position query missing 'position' key. Keys: {list(position_query.keys())}"
    assert "health_status" in position_query, f"Position query missing 'health_status' key. Keys: {list(position_query.keys())}"
    assert "current_collateral_ratio" in position_query, f"Position query missing 'current_collateral_ratio' key. Keys: {list(position_query.keys())}"
    assert "liquidation_threshold" in position_query, f"Position query missing 'liquidation_threshold' key. Keys: {list(position_query.keys())}"
    assert "collateral_value" in position_query, f"Position query missing 'collateral_value' key. Keys: {list(position_query.keys())}"
    assert "debt_with_interest" in position_query, f"Position query missing 'debt_with_interest' key. Keys: {list(position_query.keys())}"
    assert "can_close_by_owner" in position_query, f"Position query missing 'can_close_by_owner' key. Keys: {list(position_query.keys())}"
    assert "blocks_until_closeable" in position_query, f"Position query missing 'blocks_until_closeable' key. Keys: {list(position_query.keys())}"
    assert "can_initialize_liquidation" in position_query, f"Position query missing 'can_initialize_liquidation' key. Keys: {list(position_query.keys())}"
    assert "can_finalize_liquidation" in position_query, f"Position query missing 'can_finalize_liquidation' key. Keys: {list(position_query.keys())}"
    assert "borrowed" in position_query, f"Position query missing 'borrowed' key. Keys: {list(position_query.keys())}"
    assert "accrued_interest" in position_query, f"Position query missing 'accrued_interest' key. Keys: {list(position_query.keys())}"
    assert "total_repayment" in position_query, f"Position query missing 'total_repayment' key. Keys: {list(position_query.keys())}"
    assert "time_elapsed" in position_query, f"Position query missing 'time_elapsed' key. Keys: {list(position_query.keys())}"
    assert "annual_rate" in position_query, f"Position query missing 'annual_rate' key. Keys: {list(position_query.keys())}"

    # Verify position details
    position = position_query["position"]
    assert isinstance(position, dict), f"Position should be dict, got {type(position)}"
    assert int(position["position_id"]) == int(demo_result["position_id"]), f"Position ID mismatch: expected {demo_result['position_id']}, got {position['position_id']}"
    assert position["pool_id"] == demo_result["pool_id"], f"Pool ID mismatch: expected {demo_result['pool_id']}, got {position['pool_id']}"
    assert position["user"] == alice_addr, f"User address mismatch: expected {alice_addr}, got {position['user']}"

    # Verify collateral
    assert "collateral" in position, f"Position missing 'collateral' key. Keys: {list(position.keys())}"
    collateral = position["collateral"]
    assert collateral["denom"] == bar_name, f"Collateral denom mismatch: expected {bar_name}, got {collateral['denom']}"
    assert collateral["amount"] == "750", f"Collateral amount mismatch: expected '750', got {collateral['amount']}"

    # Verify borrowed amount
    borrowed = position_query["borrowed"]
    assert borrowed["denom"] == foo_name, f"Borrowed denom mismatch: expected {foo_name}, got {borrowed['denom']}"
    assert borrowed["amount"] == "500", f"Borrowed amount mismatch: expected '500', got {borrowed['amount']}"

    # Verify health status is a string (enum)
    health_status = position_query["health_status"]
    assert isinstance(health_status, str), f"Health status should be string, got {type(health_status)}"

    # Verify numeric fields are strings (cosmos.Dec format)
    assert isinstance(position_query["current_collateral_ratio"], str), f"Current collateral ratio should be string, got {type(position_query['current_collateral_ratio'])}"
    assert isinstance(position_query["liquidation_threshold"], str), f"Liquidation threshold should be string, got {type(position_query['liquidation_threshold'])}"
    assert isinstance(position_query["collateral_value"], str), f"Collateral value should be string, got {type(position_query['collateral_value'])}"
    assert isinstance(position_query["debt_with_interest"], str), f"Debt with interest should be string, got {type(position_query['debt_with_interest'])}"

    # Verify boolean fields
    assert isinstance(position_query["can_close_by_owner"], bool), f"Can close by owner should be bool, got {type(position_query['can_close_by_owner'])}"
    assert isinstance(position_query["can_initialize_liquidation"], bool), f"Can initialize liquidation should be bool, got {type(position_query['can_initialize_liquidation'])}"
    assert isinstance(position_query["can_finalize_liquidation"], bool), f"Can finalize liquidation should be bool, got {type(position_query['can_finalize_liquidation'])}"

    # Verify integer fields (may be strings in JSON response)
    assert isinstance(position_query["blocks_until_closeable"], (int, str)), f"Blocks until closeable should be int or str, got {type(position_query['blocks_until_closeable'])}"
    assert isinstance(position_query["time_elapsed"], (int, str)), f"Time elapsed should be int or str, got {type(position_query['time_elapsed'])}"

    # Verify coin structures
    total_repayment = position_query["total_repayment"]
    assert isinstance(total_repayment, dict), f"Total repayment should be dict, got {type(total_repayment)}"
    assert "denom" in total_repayment, f"Total repayment missing 'denom' key"
    assert "amount" in total_repayment, f"Total repayment missing 'amount' key"
    assert total_repayment["denom"] == foo_name, f"Total repayment denom mismatch: expected {foo_name}, got {total_repayment['denom']}"

    # Verify accrued interest is a string (cosmos.Int format)
    assert isinstance(position_query["accrued_interest"], str), f"Accrued interest should be string, got {type(position_query['accrued_interest'])}"

    # Verify annual rate is a string (cosmos.Dec format)
    assert isinstance(position_query["annual_rate"], str), f"Annual rate should be string, got {type(position_query['annual_rate'])}"
