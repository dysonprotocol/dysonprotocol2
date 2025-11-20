"""
PoolsByPair query handler coverage tests.

Tests the PoolsByPair query endpoint which queries all pools matching a denom pair.
Covers success paths, validation errors, and order-independent matching.
"""

import json
import pytest
from deep_parse import deep_parse


def test_pools_by_pair_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByPair query with matching pair."""
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

    # Sort denoms for consistent base/quote ordering
    base, quote = sorted([foo_name, bar_name])

    extra_code = f"""
from dys import _query

def demo_pools_by_pair():
    pools_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
        "base_denom": "{base}",
        "quote_denom": "{quote}"
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
        "demo_pools_by_pair",
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
    ), f"PoolsByPair response should be dict, got {type(pools_resp)}. Full response: {json.dumps(pools_resp, indent=2)}"

    # Validate response structure (Shape)
    assert (
        "pagination" in pools_resp
    ), f"PoolsByPair response missing 'pagination' key. Keys: {list(pools_resp.keys())}"

    # Validate pools list (Type + Shape)
    pools_list = pools_resp.get("pools", [])
    assert isinstance(
        pools_list, list
    ), f"Pools should be list, got {type(pools_list)}. Full response: {json.dumps(pools_resp, indent=2)}"
    assert len(pools_list) > 0, f"Expected at least one pool. Got: {json.dumps(pools_resp, indent=2)}"

    # Verify the created pool is in the list
    pool_ids = [int(p["pool_id"]) for p in pools_list]
    assert int(pool_id) in pool_ids, f"Created pool {pool_id} not found in pools list. Pool IDs: {pool_ids}"

    # Verify pool contains the correct denoms
    pool = next(p for p in pools_list if int(p["pool_id"]) == int(pool_id))
    pool_denoms = [c["denom"] for c in pool["coins"]]
    assert base in pool_denoms, f"Pool missing base denom {base}. Denoms: {pool_denoms}"
    assert quote in pool_denoms, f"Pool missing quote denom {quote}. Denoms: {pool_denoms}"


def test_pools_by_pair_no_match(chainnet, leverage_accounts, register_name):
    """Test PoolsByPair query with no matching pools."""
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]

    # Register names that won't be used in any pool
    unused_name1 = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    unused_name2 = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    base, quote = sorted([unused_name1, unused_name2])

    extra_code = f"""
from dys import _query

def demo_pools_by_pair_no_match():
    pools_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
        "base_denom": "{base}",
        "quote_denom": "{quote}"
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
        "demo_pools_by_pair_no_match",
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
    assert isinstance(pools_resp, dict), f"PoolsByPair response should be dict, got {type(pools_resp)}"
    assert "pagination" in pools_resp, f"PoolsByPair response missing 'pagination' key"

    # Validate empty pools list
    pools_list = pools_resp.get("pools", [])
    assert isinstance(pools_list, list), f"Pools should be list, got {type(pools_list)}"
    assert len(pools_list) == 0, f"Expected empty pools list. Got: {json.dumps(pools_resp, indent=2)}"


def test_pools_by_pair_empty_base_denom(chainnet):
    """Test PoolsByPair query with empty base_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_base_denom():
    # Query with empty base_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
        "base_denom": "",
        "quote_denom": "test.dys"
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
        "demo_empty_base_denom",
        "--extra-code",
        extra_code,
    )

    # Query with empty base_denom should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with empty base_denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "base_denom and quote_denom required" in exception_str.lower()
    ), f"Error should mention base_denom and quote_denom required. Exception: {exception_str}"


def test_pools_by_pair_empty_quote_denom(chainnet):
    """Test PoolsByPair query with empty quote_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_quote_denom():
    # Query with empty quote_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
        "base_denom": "test.dys",
        "quote_denom": ""
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
        "demo_empty_quote_denom",
        "--extra-code",
        extra_code,
    )

    # Query with empty quote_denom should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with empty quote_denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "base_denom and quote_denom required" in exception_str.lower()
    ), f"Error should mention base_denom and quote_denom required. Exception: {exception_str}"


def test_pools_by_pair_order_independent(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByPair query is order-independent (base/quote swapped)."""
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

    # Extract pool_id
    pool_events = [
        e
        for e in pool_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id").strip('"')

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Query with base/quote order
    base, quote = sorted([foo_name, bar_name])

    extra_code = f"""
from dys import _query

def demo_pools_by_pair_swapped():
    # Query with swapped order (quote as base, base as quote)
    pools_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
        "base_denom": "{quote}",
        "quote_denom": "{base}"
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
        "demo_pools_by_pair_swapped",
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

    # Should still find the pool even with swapped order
    pool_ids = [int(p["pool_id"]) for p in pools_list]
    assert int(pool_id) in pool_ids, f"Pool {pool_id} not found with swapped denom order. Pool IDs: {pool_ids}"

