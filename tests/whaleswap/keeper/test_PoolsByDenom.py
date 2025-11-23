"""
PoolsByDenom query handler coverage tests.

Tests the PoolsByDenom query endpoint which queries all pools containing a specific denom.
Covers success paths, validation errors, and denom matching in both coin positions.
"""

import json
import pytest
from deep_parse import deep_parse


def test_pools_by_denom_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByDenom query with denom in pools."""
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

    extra_code = f"""
from dys import _query

def demo_pools_by_denom():
    pools_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
        "denom": "{foo_name}"
    }})
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
        "demo_pools_by_denom",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert (
        result is not None
    ), f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    pools_resp = demo_result

    # Validate response structure (Type)
    assert isinstance(
        pools_resp, dict
    ), f"PoolsByDenom response should be dict, got {type(pools_resp)}. Full response: {json.dumps(pools_resp, indent=2)}"

    # Validate response structure (Shape)
    assert (
        "pagination" in pools_resp
    ), f"PoolsByDenom response missing 'pagination' key. Keys: {list(pools_resp.keys())}"

    # Validate pools list (Type + Shape)
    pools_list = pools_resp.get("pools", [])
    assert isinstance(
        pools_list, list
    ), f"Pools should be list, got {type(pools_list)}. Full response: {json.dumps(pools_resp, indent=2)}"
    assert (
        len(pools_list) > 0
    ), f"Expected at least one pool. Got: {json.dumps(pools_resp, indent=2)}"

    # Verify the created pool is in the list
    pool_ids = [int(p["pool_id"]) for p in pools_list]
    assert (
        int(pool_id) in pool_ids
    ), f"Created pool {pool_id} not found in pools list. Pool IDs: {pool_ids}"

    # Verify pool contains the queried denom
    pool = next(p for p in pools_list if int(p["pool_id"]) == int(pool_id))
    pool_denoms = [c["denom"] for c in pool["coins"]]
    assert (
        foo_name in pool_denoms
    ), f"Pool missing queried denom {foo_name}. Denoms: {pool_denoms}"


def test_pools_by_denom_no_match(chainnet):
    """Test PoolsByDenom query with denom not in any pools."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use a denom that definitely doesn't exist in any pool
    unused_name = "nonexistent.dys"

    extra_code = f"""
from dys import _query

def demo_pools_by_denom_no_match():
    pools_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
        "denom": "{unused_name}"
    }})
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
        "demo_pools_by_denom_no_match",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    pools_resp = demo_result

    # Validate response structure
    assert isinstance(
        pools_resp, dict
    ), f"PoolsByDenom response should be dict, got {type(pools_resp)}"
    assert "pagination" in pools_resp, f"PoolsByDenom response missing 'pagination' key"

    # Validate empty pools list
    pools_list = pools_resp.get("pools", [])
    assert isinstance(pools_list, list), f"Pools should be list, got {type(pools_list)}"
    assert (
        len(pools_list) == 0
    ), f"Expected empty pools list. Got: {json.dumps(pools_resp, indent=2)}"


def test_pools_by_denom_empty_denom(chainnet):
    """Test PoolsByDenom query with empty denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_denom():
    # Query with empty denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
        "denom": ""
    })
    return {"result": result}
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
        "demo_empty_denom",
        "--extra-code",
        extra_code,
    )

    # Query with empty denom should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with empty denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "denom required" in exception_str.lower()
    ), f"Error should mention denom required. Exception: {exception_str}"


def test_pools_by_denom_first_position(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test PoolsByDenom matches denom in first coin position."""
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool (foo_name will be first if lexicographically first)
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

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Query for first denom (lexicographically)
    first_denom = sorted([foo_name, bar_name])[0]

    extra_code = f"""
from dys import _query

def demo_pools_by_denom_first():
    pools_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
        "denom": "{first_denom}"
    }})
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
        "demo_pools_by_denom_first",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    pools_resp = demo_result
    pools_list = pools_resp.get("pools", [])

    # Should find the pool
    assert (
        len(pools_list) > 0
    ), f"Expected pool with denom {first_denom} in first position. Got: {json.dumps(pools_resp, indent=2)}"


def test_pools_by_denom_second_position(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test PoolsByDenom matches denom in second coin position."""
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool
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

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Query for second denom (lexicographically)
    second_denom = sorted([foo_name, bar_name])[1]

    extra_code = f"""
from dys import _query

def demo_pools_by_denom_second():
    pools_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
        "denom": "{second_denom}"
    }})
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
        "demo_pools_by_denom_second",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    pools_resp = demo_result
    pools_list = pools_resp.get("pools", [])

    # Should find the pool
    assert (
        len(pools_list) > 0
    ), f"Expected pool with denom {second_denom} in second position. Got: {json.dumps(pools_resp, indent=2)}"
