"""
Test PoolBySharesDenom query for whaleswap pools.

Tests the QueryPoolBySharesDenom endpoint which retrieves a pool by its shares denom.
Covers happy path and error cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_pool_by_shares_denom_happy_path(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test PoolBySharesDenom query with valid shares denom."""
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

def demo_pool_by_shares_denom(alice_addr, foo_name, bar_name):
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
    
    # Query pool to get shares_denom
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    shares_denom = pool_query["pool"]["shares_denom"]
    
    # Query by shares denom
    shares_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolBySharesDenomRequest",
        "shares_denom": shares_denom
    })
    
    return {
        "pool_id": pool_id,
        "shares_denom": shares_denom,
        "shares_query": shares_query
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
        "demo_pool_by_shares_denom",
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
    assert demo_result.get("shares_denom") is not None, f"Script should return shares_denom. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result.get("shares_query") is not None, f"Script should return shares_query. Result: {json.dumps(demo_result, indent=2)}"
    
    # Extract the shares query response
    shares_query = demo_result["shares_query"]
    
    # Verify the query response structure (Type + Shape)
    assert isinstance(shares_query, dict), f"Shares query should return dict, got {type(shares_query)}"
    assert "pool" in shares_query, f"Shares query missing 'pool' key. Keys: {list(shares_query.keys())}"
    
    # Verify pool details match
    pool = shares_query["pool"]
    assert isinstance(pool, dict), f"Pool should be dict, got {type(pool)}"
    assert str(pool["pool_id"]) == str(demo_result["pool_id"]), f"Pool ID mismatch: expected {demo_result['pool_id']}, got {pool['pool_id']}"
    assert pool["shares_denom"] == demo_result["shares_denom"], f"Shares denom mismatch: expected {demo_result['shares_denom']}, got {pool['shares_denom']}"
    
    # Verify shares_denom format
    assert pool["shares_denom"].startswith("whaleswap.dys/pools/"), f"Shares denom should start with 'whaleswap.dys/pools/', got {pool['shares_denom']}"
    
    # Verify pool coins
    assert "coins" in pool, f"Pool missing 'coins' key. Keys: {list(pool.keys())}"
    assert isinstance(pool["coins"], list), f"Pool coins should be list, got {type(pool['coins'])}"
    assert len(pool["coins"]) == 2, f"Pool should have 2 coins, got {len(pool['coins'])}"


def test_pool_by_shares_denom_empty(chainnet):
    """Test PoolBySharesDenom query with empty shares_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_shares_denom():
    # Query with empty shares_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolBySharesDenomRequest",
        "shares_denom": ""
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
        "demo_empty_shares_denom",
        "--extra-code",
        extra_code,
    )
    
    # Query with empty shares_denom should fail
    assert query_result.get("exception") is not None, f"Query with empty shares_denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert "shares_denom required" in exception_str.lower(), f"Error should mention shares_denom required. Exception: {exception_str}"


def test_pool_by_shares_denom_not_found(chainnet):
    """Test PoolBySharesDenom query with non-existent shares_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_nonexistent_shares_denom():
    # Query with non-existent shares_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolBySharesDenomRequest",
        "shares_denom": "whaleswap.dys/pools/999999"
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
        "demo_nonexistent_shares_denom",
        "--extra-code",
        extra_code,
    )
    
    # Query with non-existent shares_denom should fail
    assert query_result.get("exception") is not None, f"Query with non-existent shares_denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert "pool not found" in exception_str.lower(), f"Error should mention pool not found. Exception: {exception_str}"

