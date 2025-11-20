"""
Pools query handler coverage tests.

Tests the Pools query endpoint which lists all AMM pools with pagination.
Covers empty store, with pools, and nil request handling.
"""

import json
import pytest
from deep_parse import deep_parse


def test_pools_nil_request(chainnet):
    """Test Pools query with nil request (defaults handled internally)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_pools_nil_request():
    # Query with nil request (empty dict simulates nil)
    pools_resp = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsRequest"
    })
    return pools_resp
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
        "demo_pools_nil_request",
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

    pools_resp = demo_result

    # Validate response structure (Type)
    assert isinstance(
        pools_resp, dict
    ), f"Pools response should be dict, got {type(pools_resp)}. Full response: {json.dumps(pools_resp, indent=2)}"

    # Validate response structure (Shape)
    assert (
        "pagination" in pools_resp
    ), f"Pools response missing 'pagination' key. Keys: {list(pools_resp.keys())}"

    # Validate pools list (Type) - may be empty or contain pools depending on chain state
    pools_list = pools_resp.get("pools", [])
    assert isinstance(
        pools_list, list
    ), f"Pools should be list, got {type(pools_list)}. Full response: {json.dumps(pools_resp, indent=2)}"

    # Validate pagination structure
    pagination = pools_resp["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"
    assert "total" in pagination, f"Pagination missing 'total' key. Keys: {list(pagination.keys())}"


def test_pools_with_pools(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Pools query with existing pools."""
    dysond = chainnet[0]
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

    extra_code = """
from dys import _query

def demo_pools_with_pools():
    pools_resp = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsRequest"
    })
    return pools_resp
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
        "demo_pools_with_pools",
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

    pools_resp = demo_result

    # Validate response structure (Type)
    assert isinstance(
        pools_resp, dict
    ), f"Pools response should be dict, got {type(pools_resp)}. Full response: {json.dumps(pools_resp, indent=2)}"

    # Validate response structure (Shape)
    assert (
        "pagination" in pools_resp
    ), f"Pools response missing 'pagination' key. Keys: {list(pools_resp.keys())}"

    # Validate pools list (Type + Shape)
    pools_list = pools_resp.get("pools", [])
    assert isinstance(
        pools_list, list
    ), f"Pools should be list, got {type(pools_list)}. Full response: {json.dumps(pools_resp, indent=2)}"
    assert len(pools_list) > 0, f"Expected at least one pool. Got: {json.dumps(pools_resp, indent=2)}"

    # Validate pool structure
    pool = pools_list[0]
    assert isinstance(pool, dict), f"Pool should be dict, got {type(pool)}"
    assert "pool_id" in pool, f"Pool missing 'pool_id' key. Keys: {list(pool.keys())}"
    assert "coins" in pool, f"Pool missing 'coins' key. Keys: {list(pool.keys())}"

    # Verify the created pool is in the list
    pool_ids = [int(p["pool_id"]) for p in pools_list]
    assert int(pool_id) in pool_ids, f"Created pool {pool_id} not found in pools list. Pool IDs: {pool_ids}"

