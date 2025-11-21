"""
Test ClosePosition keeper function for leverage positions.

Tests the ClosePosition message handler which closes leveraged positions by swapping
held assets back to borrowed denomination, repaying principal plus accrued interest,
and returning remaining collateral and profit to the user.

Covers happy paths for ClosePosition function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_close_position_full_close_profitable_same_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test full close (fraction=1) with profitable position, same-denom collateral (happy path)."""
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

def demo_close_full_profitable_same_denom(alice_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])
    
    # Set block delay to 0 for testing (allows immediate close)
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
    
    # Open position: borrow foo, collateral in foo (same denom)
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Manipulate price to make position profitable: swap large amount foo -> bar
    # This makes bar scarcer, so held (bar) appreciates relative to borrowed (foo)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": foo_name, "amount": "8000"}],
        "min_output": [{"denom": bar_name, "amount": "1"}],
        "operations": [{
            "swap": {
                "pool_id": int(pool_id),
                "swap_in": {"denom": foo_name, "amount": "8000"}
            }
        }]
    })
    
    # Close position (full close, fraction=1)
    close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "fraction": "1.0"
    })
    
    # Query position to verify it's closed
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "close_result": close_result["results"][0],
        "position_query": position_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_close_full_profitable_same_denom",
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
    close_result = demo_result["close_result"]
    position_query = demo_result["position_query"]

    # Verify position is closed
    assert "position" in position_query, f"Missing position: {position_query}"
    position = position_query["position"]
    assert (
        position["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be closed, got: {position['status']}"

    # Verify response fields
    assert "closed" in close_result, f"Missing closed field: {close_result}"
    assert (
        close_result["closed"] == True
    ), f"Closed should be True, got: {close_result['closed']}"
    assert "interest_paid" in close_result, f"Missing interest_paid: {close_result}"
    assert "principal_paid" in close_result, f"Missing principal_paid: {close_result}"
    assert "profit" in close_result, f"Missing profit: {close_result}"


def test_close_position_full_close_profitable_cross_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test full close (fraction=1) with profitable position, cross-denom collateral (happy path)."""
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

def demo_close_full_profitable_cross_denom(alice_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])
    
    # Set block delay to 0 for testing (allows immediate close)
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
    
    # Open position: borrow foo, collateral in bar (cross denom)
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Manipulate price to make position profitable: swap large amount foo -> bar
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": foo_name, "amount": "8000"}],
        "min_output": [{"denom": bar_name, "amount": "1"}],
        "operations": [{
            "swap": {
                "pool_id": int(pool_id),
                "swap_in": {"denom": foo_name, "amount": "8000"}
            }
        }]
    })
    
    # Close position (full close, fraction=1)
    close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "fraction": "1.0"
    })
    
    # Query position to verify it's closed
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "close_result": close_result["results"][0],
        "position_query": position_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_close_full_profitable_cross_denom",
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
    close_result = demo_result["close_result"]
    position_query = demo_result["position_query"]

    # Verify position is closed
    assert "position" in position_query, f"Missing position: {position_query}"
    position = position_query["position"]
    assert (
        position["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be closed, got: {position['status']}"

    # Verify response fields
    assert "closed" in close_result, f"Missing closed field: {close_result}"
    assert (
        close_result["closed"] == True
    ), f"Closed should be True, got: {close_result['closed']}"
    assert "interest_paid" in close_result, f"Missing interest_paid: {close_result}"
    assert "principal_paid" in close_result, f"Missing principal_paid: {close_result}"
    assert "profit" in close_result, f"Missing profit: {close_result}"


def test_close_position_partial_close_profitable(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test partial close (fraction=0.5) with profitable position (happy path)."""
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

def demo_close_partial_profitable(alice_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])
    
    # Set block delay to 0 for testing (allows immediate close)
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
    
    # Open position: borrow foo, collateral in bar
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "1500"},
        "borrow": {"denom": foo_name, "amount": "1000"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Manipulate price to make position profitable
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": foo_name, "amount": "8000"}],
        "min_output": [{"denom": bar_name, "amount": "1"}],
        "operations": [{
            "swap": {
                "pool_id": int(pool_id),
                "swap_in": {"denom": foo_name, "amount": "8000"}
            }
        }]
    })
    
    # Query position before close
    position_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    # Partial close (fraction=0.5)
    close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "fraction": "0.5"
    })
    
    # Query position after close
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "close_result": close_result["results"][0],
        "position_before": position_before,
        "position_after": position_after
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_close_partial_profitable",
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
    close_result = demo_result["close_result"]
    position_before = demo_result["position_before"]
    position_after = demo_result["position_after"]

    # Verify position is still open (partial close)
    assert "position" in position_after, f"Missing position: {position_after}"
    position = position_after["position"]
    assert (
        position["status"] == "POSITION_STATUS_OPEN"
    ), f"Position should still be open after partial close, got: {position['status']}"

    # Verify response fields
    assert "closed" in close_result, f"Missing closed field: {close_result}"
    assert (
        close_result["closed"] == False
    ), f"Closed should be False for partial close, got: {close_result['closed']}"
    assert "interest_paid" in close_result, f"Missing interest_paid: {close_result}"
    assert "principal_paid" in close_result, f"Missing principal_paid: {close_result}"
    assert "new_borrowed" in close_result, f"Missing new_borrowed: {close_result}"
    assert "new_held" in close_result, f"Missing new_held: {close_result}"
    assert "new_collateral" in close_result, f"Missing new_collateral: {close_result}"

    # Verify position amounts reduced approximately by 50%
    pos_before = position_before["position"]
    pos_after = position_after["position"]
    borrowed_before = int(pos_before["borrowed"]["amount"])
    borrowed_after = int(pos_after["borrowed"]["amount"])
    held_before = int(pos_before["held"]["amount"])
    held_after = int(pos_after["held"]["amount"])
    collateral_before = int(pos_before["collateral"]["amount"])
    collateral_after = int(pos_after["collateral"]["amount"])

    # Allow for small rounding differences
    assert abs(borrowed_after - borrowed_before // 2) <= 1, (
        f"Borrowed should be ~50% of original: "
        f"before={borrowed_before}, after={borrowed_after}"
    )
    assert abs(held_after - held_before // 2) <= 1, (
        f"Held should be ~50% of original: " f"before={held_before}, after={held_after}"
    )
    assert abs(collateral_after - collateral_before // 2) <= 1, (
        f"Collateral should be ~50% of original: "
        f"before={collateral_before}, after={collateral_after}"
    )


def test_close_position_full_close_underwater_same_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test full close (fraction=1) with underwater position, same-denom collateral (covers lines 189-212)."""
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

def demo_close_underwater_same_denom(alice_addr, foo_name, bar_name, gov_addr):
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
    
    # Open position: borrow foo, collateral in foo (same denom)
    # Borrow more relative to collateral to make it easier to go underwater
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "1500"},
        "borrow": {"denom": foo_name, "amount": "1000"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Manipulate price aggressively to make position underwater: swap massive amount bar -> foo
    # This makes foo much scarcer, so held (bar) depreciates significantly relative to borrowed (foo)
    # This will make the swap proceeds less than repayment
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": bar_name, "amount": "15000"}],
        "min_output": [{"denom": foo_name, "amount": "1"}],
        "operations": [{
            "swap": {
                "pool_id": int(pool_id),
                "swap_in": {"denom": bar_name, "amount": "15000"}
            }
        }]
    })
    
    # Close position (full close, fraction=1)
    # Should use collateral to cover shortfall
    close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "fraction": "1.0"
    })
    
    # Query position to verify it's closed
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "close_result": close_result["results"][0],
        "position_query": position_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_close_underwater_same_denom",
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
    close_result = demo_result["close_result"]
    position_query = demo_result["position_query"]

    # Verify position is closed
    assert "position" in position_query, f"Missing position: {position_query}"
    position = position_query["position"]
    assert (
        position["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be closed, got: {position['status']}"

    # Verify response fields
    assert "closed" in close_result, f"Missing closed field: {close_result}"
    assert (
        close_result["closed"] == True
    ), f"Closed should be True, got: {close_result['closed']}"
    assert "interest_paid" in close_result, f"Missing interest_paid: {close_result}"
    assert "principal_paid" in close_result, f"Missing principal_paid: {close_result}"
    # Underwater positions: verify collateral was used (collateral_returned < initial collateral)
    # Initial collateral was 1500, so collateral_returned should be less
    assert (
        "collateral_returned" in close_result
    ), f"Missing collateral_returned: {close_result}"
    collateral_returned = int(close_result["collateral_returned"]["amount"])
    assert collateral_returned < 1500, (
        f"Underwater position should use collateral. "
        f"Expected collateral_returned < 1500, got: {collateral_returned}"
    )
    assert (
        close_result.get("profit", {}).get("amount", "0") == "0"
    ), f"Underwater position should have zero profit. Got: {close_result.get('profit')}"


def test_close_position_full_close_underwater_cross_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test full close (fraction=1) with underwater position, cross-denom collateral (covers lines 213-320)."""
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

def demo_close_underwater_cross_denom(alice_addr, foo_name, bar_name, gov_addr):
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
    
    # Open position: borrow foo, collateral in bar (cross denom)
    # Use more collateral to ensure it can cover shortfall after swap
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "3000"},
        "borrow": {"denom": foo_name, "amount": "1000"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Manipulate price moderately to make position underwater: swap large amount bar -> foo
    # This makes foo scarcer, so held (bar) depreciates relative to borrowed (foo)
    # But keep shortfall manageable so collateral can cover it
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": bar_name, "amount": "8000"}],
        "min_output": [{"denom": foo_name, "amount": "1"}],
        "operations": [{
            "swap": {
                "pool_id": int(pool_id),
                "swap_in": {"denom": bar_name, "amount": "8000"}
            }
        }]
    })
    
    # Close position (full close, fraction=1)
    # Should swap collateral to cover shortfall
    close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "fraction": "1.0"
    })
    
    # Query position to verify it's closed
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "close_result": close_result["results"][0],
        "position_query": position_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_close_underwater_cross_denom",
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
    close_result = demo_result["close_result"]
    position_query = demo_result["position_query"]

    # Verify position is closed
    assert "position" in position_query, f"Missing position: {position_query}"
    position = position_query["position"]
    assert (
        position["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be closed, got: {position['status']}"

    # Verify response fields
    assert "closed" in close_result, f"Missing closed field: {close_result}"
    assert (
        close_result["closed"] == True
    ), f"Closed should be True, got: {close_result['closed']}"
    assert "interest_paid" in close_result, f"Missing interest_paid: {close_result}"
    assert "principal_paid" in close_result, f"Missing principal_paid: {close_result}"
    # Underwater positions: verify collateral was swapped (cross-denom path executed)
    # Initial collateral was 3000, so collateral_returned should be less (some used for swap)
    assert (
        "collateral_returned" in close_result
    ), f"Missing collateral_returned: {close_result}"
    collateral_returned = int(close_result["collateral_returned"]["amount"])
    assert collateral_returned < 3000, (
        f"Underwater position should use collateral for swap. "
        f"Expected collateral_returned < 3000, got: {collateral_returned}"
    )
    assert (
        close_result.get("profit", {}).get("amount", "0") == "0"
    ), f"Underwater position should have zero profit. Got: {close_result.get('profit')}"


def test_close_position_partial_close_underwater_same_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test partial close (fraction=0.5) with underwater position, same-denom collateral."""
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

def demo_partial_close_underwater_same_denom(alice_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])
    
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
    
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "2000"},
        "borrow": {"denom": foo_name, "amount": "1000"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": bar_name, "amount": "15000"}],
        "min_output": [{"denom": foo_name, "amount": "1"}],
        "operations": [{
            "swap": {
                "pool_id": int(pool_id),
                "swap_in": {"denom": bar_name, "amount": "15000"}
            }
        }]
    })
    
    position_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "fraction": "0.5"
    })
    
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "close_result": close_result["results"][0],
        "position_before": position_before,
        "position_after": position_after
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_partial_close_underwater_same_denom",
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
    close_result = demo_result["close_result"]
    position_after = demo_result["position_after"]

    assert "position" in position_after, f"Missing position: {position_after}"
    position = position_after["position"]
    assert (
        position["status"] == "POSITION_STATUS_OPEN"
    ), f"Position should still be open after partial close, got: {position['status']}"

    assert "closed" in close_result, f"Missing closed field: {close_result}"
    assert (
        close_result["closed"] == False
    ), f"Closed should be False for partial close, got: {close_result['closed']}"
    assert "interest_paid" in close_result, f"Missing interest_paid: {close_result}"
    assert "principal_paid" in close_result, f"Missing principal_paid: {close_result}"
