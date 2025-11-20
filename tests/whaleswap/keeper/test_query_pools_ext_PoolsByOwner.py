"""
Test PoolsByOwner query for whaleswap pools.

Tests the QueryPoolsByOwner endpoint which retrieves pools where the owner
holds non-zero shares balance.
Covers happy paths and error cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_pools_by_owner_happy_path(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolsByOwner query with owner who created a pool."""
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

def demo_pools_by_owner(alice_addr, foo_name, bar_name):
    # Create pool - creator receives initial shares
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
    
    # Query pools by owner (alice created the pool, so she has shares)
    pools_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByOwnerRequest",
        "owner": alice_addr
    })
    
    return {
        "pool_id": pool_id,
        "alice_addr": alice_addr,
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
        "demo_pools_by_owner",
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
    assert demo_result.get("alice_addr") is not None, f"Script should return alice_addr. Result: {json.dumps(demo_result, indent=2)}"
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
    assert len(pools) >= 1, f"Should have at least 1 pool for owner, got {len(pools)}"
    
    # Verify the created pool is in results
    pool_ids = [str(pool["pool_id"]) for pool in pools]
    assert str(demo_result["pool_id"]) in pool_ids, f"Created pool {demo_result['pool_id']} should be in results for owner {demo_result['alice_addr']}. Pool IDs: {pool_ids}, Pools: {json.dumps(pools, indent=2)}"
    
    # Verify pool structure
    pool_index = pool_ids.index(str(demo_result["pool_id"]))
    found_pool = pools[pool_index]
    assert "coins" in found_pool, f"Pool missing 'coins' key. Keys: {list(found_pool.keys())}"
    assert len(found_pool["coins"]) == 2, f"Pool should have 2 coins, got {len(found_pool['coins'])}"
    assert "shares_denom" in found_pool, f"Pool missing 'shares_denom' key. Keys: {list(found_pool.keys())}"


def test_pools_by_owner_empty(chainnet):
    """Test PoolsByOwner query with empty owner."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_owner():
    # Query with empty owner should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByOwnerRequest",
        "owner": ""
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
        "demo_empty_owner",
        "--extra-code",
        extra_code,
    )
    
    # Query with empty owner should fail
    assert query_result.get("exception") is not None, f"Query with empty owner should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert "owner required" in exception_str.lower(), f"Error should mention owner required. Exception: {exception_str}"


def test_pools_by_owner_invalid_address(chainnet):
    """Test PoolsByOwner query with invalid owner address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_invalid_owner():
    # Query with invalid owner address should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByOwnerRequest",
        "owner": "not_a_valid_address"
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
        "demo_invalid_owner",
        "--extra-code",
        extra_code,
    )
    
    # Query with invalid owner address should fail
    assert query_result.get("exception") is not None, f"Query with invalid owner address should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert "invalid owner" in exception_str.lower(), f"Error should mention invalid owner. Exception: {exception_str}"

