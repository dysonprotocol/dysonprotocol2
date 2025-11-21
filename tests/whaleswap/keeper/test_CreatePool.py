"""
Test CreatePool keeper function for whaleswap pools.

Tests the CreatePool message handler which creates a two-asset pool with per-denom
fee/interest/leverage parameters and optional directional bound_percent limits.

Covers happy paths for CreatePool function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_create_pool_basic_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test basic pool creation with all required fields (covers main happy path)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import json

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_pool_basic(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool with all required fields
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
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"]
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
        "demo_create_pool_basic",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    pool_id = demo_result["pool_id"]
    pool = demo_result["pool"]

    # Verify pool was created
    assert isinstance(pool_id, (int, str)), f"Pool ID should be int or str, got {type(pool_id)}"
    assert "pool_id" in pool, f"Missing pool_id in pool: {pool}"
    assert pool["pool_id"] == pool_id, f"Pool ID mismatch: {pool['pool_id']} != {pool_id}"

    # Verify pool structure
    assert "coins" in pool, f"Missing coins: {pool}"
    assert isinstance(pool["coins"], list), f"Coins should be list, got {type(pool['coins'])}"
    assert len(pool["coins"]) == 2, f"Pool should have 2 coins, got {len(pool['coins'])}"

    # Verify coins are canonicalized (sorted by denom)
    coin_denoms = [c["denom"] for c in pool["coins"]]
    assert coin_denoms == sorted(coin_denoms), (
        f"Coins should be canonicalized. Got: {coin_denoms}"
    )

    # Verify shares denom
    assert "shares_denom" in pool, f"Missing shares_denom: {pool}"
    assert isinstance(pool["shares_denom"], str), (
        f"Shares denom should be string, got {type(pool['shares_denom'])}"
    )

    # Verify fee_rate
    assert "fee_rate" in pool, f"Missing fee_rate: {pool}"
    assert isinstance(pool["fee_rate"], list), (
        f"Fee rate should be list, got {type(pool['fee_rate'])}"
    )
    assert len(pool["fee_rate"]) == 2, (
        f"Fee rate should have 2 entries, got {len(pool['fee_rate'])}"
    )


def test_create_pool_with_bound_percent(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test pool creation with optional bound_percent (covers lines 90-122)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import json

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_pool_with_bound_percent(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool with bound_percent
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
        "bound_percent": [
            {"denom": base, "amount": "0.5"},
            {"denom": quote, "amount": "0.8"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"]
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
        "demo_create_pool_with_bound_percent",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    pool = demo_result["pool"]

    # Verify bound_percent was set
    assert "bound_percent" in pool, f"Missing bound_percent: {pool}"
    assert isinstance(pool["bound_percent"], list), (
        f"Bound percent should be list, got {type(pool['bound_percent'])}"
    )
    assert len(pool["bound_percent"]) == 2, (
        f"Bound percent should have 2 entries, got {len(pool['bound_percent'])}"
    )


def test_create_pool_default_bound_percent(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test pool creation without bound_percent (defaults to 1, covers lines 113-118)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import json

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_pool_default_bound_percent(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool without bound_percent (should default to 1 for both)
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
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"]
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
        "demo_create_pool_default_bound_percent",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    pool = demo_result["pool"]

    # Verify bound_percent defaults to 1 for both denoms
    assert "bound_percent" in pool, f"Missing bound_percent: {pool}"
    assert isinstance(pool["bound_percent"], list), (
        f"Bound percent should be list, got {type(pool['bound_percent'])}"
    )
    assert len(pool["bound_percent"]) == 2, (
        f"Bound percent should have 2 entries, got {len(pool['bound_percent'])}"
    )
    # Both should be 1 (unbounded) - may be formatted as "1" or "1.000000000000000000"
    for bp in pool["bound_percent"]:
        bp_amount = bp["amount"]
        # Convert to float to handle both "1" and "1.000000000000000000" formats
        bp_value = float(bp_amount)
        assert bp_value == 1.0, (
            f"Default bound_percent should be 1, got {bp_amount} (parsed as {bp_value})"
        )


def test_create_pool_zero_fee_rate(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test pool creation with zero fee_rate (covers lines 124-136)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import json

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_pool_zero_fee_rate(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool with zero fee_rate (omitted, defaults to 0)
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"]
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
        "demo_create_pool_zero_fee_rate",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    pool = demo_result["pool"]

    # Verify fee_rate defaults to 0
    assert "fee_rate" in pool, f"Missing fee_rate: {pool}"
    assert isinstance(pool["fee_rate"], list), (
        f"Fee rate should be list, got {type(pool['fee_rate'])}"
    )
    assert len(pool["fee_rate"]) == 2, (
        f"Fee rate should have 2 entries, got {len(pool['fee_rate'])}"
    )
    # Both should be 0 when omitted - may be formatted as "0" or "0.000000000000000000"
    for fr in pool["fee_rate"]:
        fr_value = float(fr["amount"])
        assert fr_value == 0.0, (
            f"Default fee_rate should be 0, got {fr['amount']} (parsed as {fr_value})"
        )


def test_create_pool_zero_interest_rate(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test pool creation with zero interest_rate (covers lines 158-168)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import json

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_pool_zero_interest_rate(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool with zero interest_rate (omitted, defaults to 0)
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"]
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
        "demo_create_pool_zero_interest_rate",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    pool = demo_result["pool"]

    # Verify interest_rate defaults to 0
    assert "interest_rate" in pool, f"Missing interest_rate: {pool}"
    assert isinstance(pool["interest_rate"], list), (
        f"Interest rate should be list, got {type(pool['interest_rate'])}"
    )
    assert len(pool["interest_rate"]) == 2, (
        f"Interest rate should have 2 entries, got {len(pool['interest_rate'])}"
    )
    # Both should be 0 when omitted - may be formatted as "0" or "0.000000000000000000"
    for ir in pool["interest_rate"]:
        ir_value = float(ir["amount"])
        assert ir_value == 0.0, (
            f"Default interest_rate should be 0, got {ir['amount']} (parsed as {ir_value})"
        )


def test_create_pool_minimum_shares(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test pool creation with very small amounts to trigger minimum shares adjustment (covers lines 241-244)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import json

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_pool_minimum_shares(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool with very small amounts (1 each) to test minimum shares
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "1"},
            {"denom": bar_name, "amount": "1"}
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
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"]
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
        "demo_create_pool_minimum_shares",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    pool = demo_result["pool"]

    # Verify pool was created successfully
    assert "pool_id" in pool, f"Missing pool_id: {pool}"
    assert "shares_denom" in pool, f"Missing shares_denom: {pool}"
    # With 1x1, sqrt(1) = 1, so shares should be at least 1
    # The minimum shares adjustment ensures at least 1 share is minted

