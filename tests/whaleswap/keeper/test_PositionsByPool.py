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

def demo_positions_by_pool_success(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    pool_result = _sudo({
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
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.0"},
            {"denom": quote, "amount": "0.0"}
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
    pool_id = pool_result["results"][0]["pool_id"]

    pos_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    position_id = pos_result["results"][0]["position_id"]

    positions_response = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionsByPoolRequest",
        "pool_id": int(pool_id)
    })

    return {
        "pool_id": pool_id,
        "position_id": position_id,
        "positions_response": positions_response
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
        "demo_positions_by_pool_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    positions_response = demo_result["positions_response"]
    pool_id = demo_result["pool_id"]
    position_id = demo_result["position_id"]

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

def demo_positions_by_pool_no_positions(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    pool_result = _sudo({
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
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.0"},
            {"denom": quote, "amount": "0.0"}
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
    pool_id = pool_result["results"][0]["pool_id"]

    positions_response = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionsByPoolRequest",
        "pool_id": int(pool_id)
    })

    return {"pool_id": pool_id, "positions_response": positions_response}
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
        "demo_positions_by_pool_no_positions",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    pool_id = demo_result["pool_id"]
    positions_response = demo_result["positions_response"]

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

def demo_positions_by_pool_status(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    pool_result = _sudo({
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
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.0"},
            {"denom": quote, "amount": "0.0"}
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
    pool_id = pool_result["results"][0]["pool_id"]

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })

    positions_response = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionsByPoolRequest",
        "pool_id": int(pool_id),
        "status": "POSITION_STATUS_OPEN"
    })

    return {"positions_response": positions_response}
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
        "demo_positions_by_pool_status",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    positions_response = demo_result["positions_response"]

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
