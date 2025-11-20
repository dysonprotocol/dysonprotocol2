"""
Pool query handler coverage tests.

Tests the Pool query endpoint which retrieves a single AMM pool by ID.
Covers success path, zero ID validation, and not found error.
"""

import json
import pytest
from deep_parse import deep_parse


def test_pool_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Pool query with valid pool ID."""
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

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = f"""
from dys import _query

def demo_pool_success():
    pool_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": {pool_id}
    }})
    return pool_resp["pool"]
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
        "demo_pool_success",
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

    pool = demo_result

    # Validate response structure (Type)
    assert isinstance(
        pool, dict
    ), f"Pool should be dict, got {type(pool)}. Full response: {json.dumps(pool, indent=2)}"

    # Validate pool structure (Shape)
    assert "pool_id" in pool, f"Pool missing 'pool_id' key. Keys: {list(pool.keys())}"
    assert "coins" in pool, f"Pool missing 'coins' key. Keys: {list(pool.keys())}"
    assert "shares_denom" in pool, f"Pool missing 'shares_denom' key. Keys: {list(pool.keys())}"

    # Validate values
    assert int(pool["pool_id"]) == int(pool_id), f"Pool ID mismatch: expected {pool_id}, got {pool['pool_id']}"


def test_pool_zero_id(chainnet):
    """Test Pool query with zero pool ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_pool_zero_id():
    try:
        pool_resp = _query({
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
            "pool_id": 0
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
        "demo_pool_zero_id",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    assert demo_result.get("expected") is True, f"Expected error for zero pool_id. Result: {json.dumps(demo_result, indent=2)}"


def test_pool_not_found(chainnet):
    """Test Pool query with non-existent pool ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_pool_not_found():
    try:
        pool_resp = _query({
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
            "pool_id": 99999
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
        "demo_pool_not_found",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    assert demo_result.get("expected") is True, f"Expected error for non-existent pool. Result: {json.dumps(demo_result, indent=2)}"

