"""
Test PoolsByPairPriceRange query for whaleswap pools.

Tests the QueryPoolsByPairPriceRange endpoint which retrieves pools for a denom pair
whose instantaneous price falls within optional bounds.
Covers happy paths and error cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_pools_by_pair_price_range_no_bounds(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByPairPriceRange query without price bounds."""
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

def demo_pools_by_pair_no_bounds(alice_addr, foo_name, bar_name):
    # Create pool
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "20000"}
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

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Query pools by pair without price bounds
    pools_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairPriceRangeRequest",
        "base_denom": foo_name,
        "quote_denom": bar_name
    })
    
    return {
        "pool_id": pool_id,
        "pools_query": pools_query
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
        "demo_pools_by_pair_no_bounds",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    # Extract nested result
    demo_result = result["result"]["result"]
    
    # Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # Validate script returned expected structure
    assert demo_result.get("pool_id") is not None, f"Script should return pool_id. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result.get("pools_query") is not None, f"Script should return pools_query. Result: {json.dumps(demo_result, indent=2)}"
    
    # Extract the pools query response
    pools_query = demo_result["pools_query"]
    
    # Verify the query response structure (Type + Shape)
    assert isinstance(pools_query, dict), f"Pools query should return dict, got {type(pools_query)}"
    assert "pools" in pools_query, f"Pools query missing 'pools' key. Keys: {list(pools_query.keys())}"
    assert "pagination" in pools_query, f"Pools query missing 'pagination' key. Keys: {list(pools_query.keys())}"
    
    # Verify pools list
    pools = pools_query["pools"]
    assert isinstance(pools, list), f"Pools should be list, got {type(pools)}"
    assert len(pools) >= 1, f"Should have at least 1 pool, got {len(pools)}"
    
    # Verify the created pool is in results
    pool_ids = [str(pool["pool_id"]) for pool in pools]
    assert str(demo_result["pool_id"]) in pool_ids, f"Created pool {demo_result['pool_id']} should be in results. Pool IDs: {pool_ids}, Pools: {json.dumps(pools, indent=2)}"
    
    # Verify pool structure - get the pool by index
    pool_index = pool_ids.index(str(demo_result["pool_id"]))
    found_pool = pools[pool_index]
    assert "coins" in found_pool, f"Pool missing 'coins' key. Keys: {list(found_pool.keys())}"
    assert len(found_pool["coins"]) == 2, f"Pool should have 2 coins, got {len(found_pool['coins'])}"


def test_pools_by_pair_price_range_with_min_price(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByPairPriceRange query with min_price bound."""
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

def demo_pools_by_pair_min_price(alice_addr, foo_name, bar_name):
    # Create pool with reserves: 10000 foo, 20000 bar
    # Price = bar/foo = 20000/10000 = 2.0
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "20000"}
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

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Query pools by pair with min_price = 1.5 (should include pool with price 2.0)
    pools_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairPriceRangeRequest",
        "base_denom": foo_name,
        "quote_denom": bar_name,
        "min_price": "1.5"
    })
    
    return {
        "pool_id": pool_id,
        "pools_query": pools_query
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
        "demo_pools_by_pair_min_price",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    demo_result = result["result"]["result"]
    
    # Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # Verify pools query response
    pools_query = demo_result["pools_query"]
    assert isinstance(pools_query, dict), f"Pools query should return dict, got {type(pools_query)}"
    assert "pools" in pools_query, f"Pools query missing 'pools' key. Keys: {list(pools_query.keys())}"
    
    pools = pools_query["pools"]
    assert isinstance(pools, list), f"Pools should be list, got {type(pools)}"
    assert len(pools) >= 1, f"Should have at least 1 pool matching min_price, got {len(pools)}"
    
    # Verify created pool is in results
    pool_ids = [str(pool["pool_id"]) for pool in pools]
    assert str(demo_result["pool_id"]) in pool_ids, f"Created pool {demo_result['pool_id']} should be in results with min_price filter. Pool IDs: {pool_ids}, Pools: {json.dumps(pools, indent=2)}"


def test_pools_by_pair_price_range_with_max_price(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByPairPriceRange query with max_price bound."""
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

def demo_pools_by_pair_max_price(alice_addr, foo_name, bar_name):
    # Create pool with reserves: 10000 foo, 20000 bar
    # Price = bar/foo = 20000/10000 = 2.0
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "20000"}
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

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Query pools by pair with max_price = 2.5 (should include pool with price 2.0)
    pools_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairPriceRangeRequest",
        "base_denom": foo_name,
        "quote_denom": bar_name,
        "max_price": "2.5"
    })
    
    return {
        "pool_id": pool_id,
        "pools_query": pools_query
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
        "demo_pools_by_pair_max_price",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    demo_result = result["result"]["result"]
    
    # Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # Verify pools query response
    pools_query = demo_result["pools_query"]
    assert isinstance(pools_query, dict), f"Pools query should return dict, got {type(pools_query)}"
    assert "pools" in pools_query, f"Pools query missing 'pools' key. Keys: {list(pools_query.keys())}"
    
    pools = pools_query["pools"]
    assert isinstance(pools, list), f"Pools should be list, got {type(pools)}"
    assert len(pools) >= 1, f"Should have at least 1 pool matching max_price, got {len(pools)}"
    
    # Verify created pool is in results
    pool_ids = [str(pool["pool_id"]) for pool in pools]
    assert str(demo_result["pool_id"]) in pool_ids, f"Created pool {demo_result['pool_id']} should be in results with max_price filter. Pool IDs: {pool_ids}, Pools: {json.dumps(pools, indent=2)}"


def test_pools_by_pair_price_range_with_both_bounds(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByPairPriceRange query with both min_price and max_price bounds."""
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

def demo_pools_by_pair_both_bounds(alice_addr, foo_name, bar_name):
    # Create pool with reserves: 10000 foo, 20000 bar
    # Price = bar/foo = 20000/10000 = 2.0
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "20000"}
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

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Query pools by pair with both bounds: min_price = 1.5, max_price = 2.5
    pools_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairPriceRangeRequest",
        "base_denom": foo_name,
        "quote_denom": bar_name,
        "min_price": "1.5",
        "max_price": "2.5"
    })
    
    return {
        "pool_id": pool_id,
        "pools_query": pools_query
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
        "demo_pools_by_pair_both_bounds",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    demo_result = result["result"]["result"]
    
    # Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # Verify pools query response
    pools_query = demo_result["pools_query"]
    assert isinstance(pools_query, dict), f"Pools query should return dict, got {type(pools_query)}"
    assert "pools" in pools_query, f"Pools query missing 'pools' key. Keys: {list(pools_query.keys())}"
    
    pools = pools_query["pools"]
    assert isinstance(pools, list), f"Pools should be list, got {type(pools)}"
    assert len(pools) >= 1, f"Should have at least 1 pool matching both bounds, got {len(pools)}"
    
    # Verify created pool is in results
    pool_ids = [str(pool["pool_id"]) for pool in pools]
    assert str(demo_result["pool_id"]) in pool_ids, f"Created pool {demo_result['pool_id']} should be in results with both bounds. Pool IDs: {pool_ids}, Pools: {json.dumps(pools, indent=2)}"


def test_pools_by_pair_price_range_empty_base_denom(chainnet):
    """Test PoolsByPairPriceRange query with empty base_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_base_denom():
    # Query with empty base_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairPriceRangeRequest",
        "base_denom": "",
        "quote_denom": "some.denom"
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
    assert query_result.get("exception") is not None, f"Query with empty base_denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert "base_denom and quote_denom required" in exception_str.lower(), f"Error should mention base_denom and quote_denom required. Exception: {exception_str}"


def test_pools_by_pair_price_range_empty_quote_denom(chainnet):
    """Test PoolsByPairPriceRange query with empty quote_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_quote_denom():
    # Query with empty quote_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairPriceRangeRequest",
        "base_denom": "some.denom",
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
    assert query_result.get("exception") is not None, f"Query with empty quote_denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert "base_denom and quote_denom required" in exception_str.lower(), f"Error should mention base_denom and quote_denom required. Exception: {exception_str}"


def test_pools_by_pair_price_range_invalid_min_price(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByPairPriceRange query with invalid min_price format."""
    dysond = chainnet[0]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_invalid_min_price(foo_name, bar_name):
    # Query with invalid min_price should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairPriceRangeRequest",
        "base_denom": foo_name,
        "quote_denom": bar_name,
        "min_price": "not_a_number"
    })
    return {"result": result}
"""
    
    kwargs = json.dumps({"foo_name": foo_name, "bar_name": bar_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_invalid_min_price",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Query with invalid min_price should fail
    assert query_result.get("exception") is not None, f"Query with invalid min_price should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert "invalid min_price" in exception_str.lower(), f"Error should mention invalid min_price. Exception: {exception_str}"


def test_pools_by_pair_price_range_invalid_max_price(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByPairPriceRange query with invalid max_price format."""
    dysond = chainnet[0]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_invalid_max_price(foo_name, bar_name):
    # Query with invalid max_price should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairPriceRangeRequest",
        "base_denom": foo_name,
        "quote_denom": bar_name,
        "max_price": "not_a_number"
    })
    return {"result": result}
"""
    
    kwargs = json.dumps({"foo_name": foo_name, "bar_name": bar_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_invalid_max_price",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Query with invalid max_price should fail
    assert query_result.get("exception") is not None, f"Query with invalid max_price should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert "invalid max_price" in exception_str.lower(), f"Error should mention invalid max_price. Exception: {exception_str}"

