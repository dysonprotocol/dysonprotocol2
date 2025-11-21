"""
Test InitializeLiquidation keeper function for leverage positions.

Tests the InitializeLiquidation message handler which marks a leveraged position
for liquidation when its collateral ratio falls below the liquidation threshold.

Covers happy paths and error conditions for InitializeLiquidation function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_initialize_liquidation_basic_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test basic liquidation initialization (covers main happy path)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
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

def demo_initialize_liquidation_basic(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool
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
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.05"},
            {"denom": quote, "amount": "1.05"}
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
    
    # Open position with CR between min_initial_collateral_ratio (1.05) and liquidation_threshold (1.2)
    # With collateral=11 foo and borrow=10 foo, CR = 11/10 = 1.1 (liquidatable, meets min requirement)
    # Using same-denom avoids price conversion complexity in InitializeLiquidation
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "11"},
        "borrow": {"denom": foo_name, "amount": "10"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Initialize liquidation
    init_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": bob_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })
    
    # Query position to verify liquidation is initialized
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "pool_id": pool_id,
        "init_result": init_result["results"][0],
        "position_query": position_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "gov_addr": gov_addr,
        }
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
        "demo_initialize_liquidation_basic",
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
    init_result = demo_result["init_result"]
    position_query = demo_result["position_query"]

    # Verify position liquidation is initialized
    assert "position" in position_query, f"Missing position: {position_query}"
    position = position_query["position"]
    assert (
        position["liquidation_status"] == "LIQUIDATION_STATUS_INITIALIZED"
    ), f"Liquidation should be initialized, got: {position['liquidation_status']}"
    assert (
        int(position["liquidation_initialized_block_height"]) > 0
    ), f"Initialization block height must be > 0, got: {position['liquidation_initialized_block_height']}"

    # Verify response fields
    assert (
        "collateral_ratio" in init_result
    ), f"Missing collateral_ratio: {init_result}"
    assert (
        "liquidation_threshold" in init_result
    ), f"Missing liquidation_threshold: {init_result}"

    # Verify collateral ratio is below threshold
    cr = float(init_result["collateral_ratio"])
    threshold = float(init_result["liquidation_threshold"])
    assert (
        cr < threshold
    ), f"Collateral ratio {cr} should be < threshold {threshold}"


def test_initialize_liquidation_position_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that InitializeLiquidation fails when position doesn't exist."""
    dysond = chainnet[0]
    bob_addr = leverage_accounts["bob"]["addr"]
    alice_addr = leverage_accounts["alice"]["addr"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_position_not_found(bob_addr, alice_addr):
    # Try to initialize liquidation for non-existent position
    return _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": bob_addr,
        "user": alice_addr,
        "pool_id": 999,
        "position_id": 99999
    })
"""

    kwargs = json.dumps({"bob_addr": bob_addr, "alice_addr": alice_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_position_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Expected exception for non-existent position"
    exception_msg = str(exception.get("msg", ""))
    assert (
        "not found" in exception_msg.lower()
    ), f"Exception should mention 'not found'. Got: {exception_msg}"


def test_initialize_liquidation_position_not_active(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that InitializeLiquidation fails when position is CLOSED or LIQUIDATED."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
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

def demo_position_not_active(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])
    
    # Set block delay to 0 for testing
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "pfand_per_offer": {"denom": "udys", "amount": "0"},
            "valuation_fee_pct": "0",
            "valuation_period": "3600s",
            "bid_timeout": "5s",
            "minimum_bid_percent_increase": "0",
            "max_note_length": 128,
            "block_delay_before_close": 0,
            "block_delay_before_liquidation": 0
        }
    })
    
    # Create pool
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
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.05"},
            {"denom": quote, "amount": "1.05"}
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
    
    # Open position
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "11"},
        "borrow": {"denom": foo_name, "amount": "10"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Close position (full close)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "fraction": "1"
    })
    
    # Try to initialize liquidation on closed position
    return _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": bob_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "gov_addr": gov_addr,
        }
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
        "demo_position_not_active",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Expected exception for closed position"
    exception_msg = str(exception.get("msg", ""))
    assert (
        "not active" in exception_msg.lower()
    ), f"Exception should mention 'not active'. Got: {exception_msg}"


def test_initialize_liquidation_position_not_liquidatable(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that InitializeLiquidation fails when CR >= liquidation_threshold."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_position_not_liquidatable(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool
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
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.05"},
            {"denom": quote, "amount": "1.05"}
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
    
    # Open position with CR >= liquidation_threshold
    # With collateral=12 foo and borrow=10 foo, CR = 12/10 = 1.2 (equals threshold, not liquidatable)
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "12"},
        "borrow": {"denom": foo_name, "amount": "10"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Try to initialize liquidation (should fail)
    return _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": bob_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "gov_addr": gov_addr,
        }
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
        "demo_position_not_liquidatable",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Expected exception for non-liquidatable position"
    exception_msg = str(exception.get("msg", ""))
    exception_msg_lower = exception_msg.lower()
    assert (
        "not liquidatable" in exception_msg_lower
    ), f"Exception should mention 'not liquidatable'. Got: {exception_msg}"
    assert (
        "collateral ratio" in exception_msg_lower
    ), f"Exception should mention 'collateral ratio'. Got: {exception_msg}"


def test_initialize_liquidation_with_interest(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test liquidation initialization with accrued interest (covers interest calculation path)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
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

def demo_initialize_liquidation_with_interest(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool with higher interest rate to generate interest
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
        "interest_rate": [
            {"denom": base, "amount": "0.1"},
            {"denom": quote, "amount": "0.1"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.05"},
            {"denom": quote, "amount": "1.05"}
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
    
    # Open position with CR between min_initial_collateral_ratio (1.05) and liquidation_threshold (1.2)
    # With collateral=11 foo and borrow=10 foo, CR = 11/10 = 1.1 (liquidatable, meets min requirement)
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "11"},
        "borrow": {"denom": foo_name, "amount": "10"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Query position to get initial borrowed amount
    position_query_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    # Initialize liquidation (interest will be accrued)
    init_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": bob_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "pool_id": pool_id,
        "init_result": init_result["results"][0],
        "position_query_before": position_query_before
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "gov_addr": gov_addr,
        }
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
        "demo_initialize_liquidation_with_interest",
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
    init_result = demo_result["init_result"]

    # Verify response fields
    assert (
        "collateral_ratio" in init_result
    ), f"Missing collateral_ratio: {init_result}"
    assert (
        "liquidation_threshold" in init_result
    ), f"Missing liquidation_threshold: {init_result}"

    # Verify collateral ratio is below threshold (interest increases debt, lowering CR)
    cr = float(init_result["collateral_ratio"])
    threshold = float(init_result["liquidation_threshold"])
    assert (
        cr < threshold
    ), f"Collateral ratio {cr} should be < threshold {threshold}"

