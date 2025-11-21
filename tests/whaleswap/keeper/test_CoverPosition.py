"""
Test CoverPosition keeper function for leverage positions.

Tests the CoverPosition message handler which repays accrued interest (must be fully covered)
and optionally reduces principal for a leveraged position. Can auto-close if payment >= total
repayment, or partially cover if payment < total repayment but >= interest.

Covers happy paths for CoverPosition function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_cover_position_auto_close_full_repayment(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test auto-close path when payment >= principal + interest (covers lines 116-293)."""
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

def demo_cover_auto_close(alice_addr, foo_name, bar_name, gov_addr):
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
    
    # Open position: borrow foo, collateral in bar
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Query position to get current borrowed amount (for calculating total repayment)
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    # Calculate total repayment: borrowed + interest
    # Use a payment that's >= total repayment to trigger auto-close
    position = position_query["position"]
    borrowed_amount = int(position["borrowed"]["amount"])
    # Payment should be >= borrowed + interest (use generous amount)
    payment_amount = borrowed_amount + 100
    
    # Cover position with payment >= total repayment (auto-close)
    cover_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCoverPosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "payment": {"denom": foo_name, "amount": str(payment_amount)}
    })
    
    # Query position to verify it's closed
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "cover_result": cover_result["results"][0],
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
        "demo_cover_auto_close",
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
    cover_result = demo_result["cover_result"]
    position_after = demo_result["position_after"]

    # Verify position is closed
    assert "position" in position_after, f"Missing position: {position_after}"
    position = position_after["position"]
    assert (
        position["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be closed, got: {position['status']}"

    # Verify response fields
    assert "closed" in cover_result, f"Missing closed field: {cover_result}"
    assert (
        cover_result["closed"] == True
    ), f"Closed should be True for auto-close, got: {cover_result['closed']}"
    assert "interest_paid" in cover_result, f"Missing interest_paid: {cover_result}"
    assert "principal_paid" in cover_result, f"Missing principal_paid: {cover_result}"
    assert "new_borrowed" in cover_result, f"Missing new_borrowed: {cover_result}"
    assert "refunded" in cover_result, f"Missing refunded: {cover_result}"
    assert "profit" in cover_result, f"Missing profit: {cover_result}"


def test_cover_position_partial_cover(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test partial cover path when payment < total repayment but >= interest (covers lines 295-391)."""
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

def demo_cover_partial(alice_addr, foo_name, bar_name, gov_addr):
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
    
    # Open position: borrow foo, collateral in bar
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "1500"},
        "borrow": {"denom": foo_name, "amount": "1000"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Query position before cover
    position_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    # Partial cover: pay interest + some principal (but less than total repayment)
    # Payment should be >= interest but < total repayment
    position = position_before["position"]
    borrowed_amount = int(position["borrowed"]["amount"])
    # Use payment that covers interest + 200 of principal (total repayment would be ~1000 + interest)
    payment_amount = 250
    
    # Cover position with partial payment
    cover_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCoverPosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "payment": {"denom": foo_name, "amount": str(payment_amount)}
    })
    
    # Query position after cover
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "cover_result": cover_result["results"][0],
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
        "demo_cover_partial",
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
    cover_result = demo_result["cover_result"]
    position_before = demo_result["position_before"]
    position_after = demo_result["position_after"]

    # Verify position is still open (partial cover)
    assert "position" in position_after, f"Missing position: {position_after}"
    position = position_after["position"]
    assert (
        position["status"] == "POSITION_STATUS_OPEN"
    ), f"Position should still be open after partial cover, got: {position['status']}"

    # Verify response fields
    assert "closed" in cover_result, f"Missing closed field: {cover_result}"
    assert (
        cover_result["closed"] == False
    ), f"Closed should be False for partial cover, got: {cover_result['closed']}"
    assert "interest_paid" in cover_result, f"Missing interest_paid: {cover_result}"
    assert "principal_paid" in cover_result, f"Missing principal_paid: {cover_result}"
    assert "new_borrowed" in cover_result, f"Missing new_borrowed: {cover_result}"
    assert (
        "new_collateral_ratio" in cover_result
    ), f"Missing new_collateral_ratio: {cover_result}"

    # Verify principal was reduced
    pos_before = position_before["position"]
    pos_after = position_after["position"]
    borrowed_before = int(pos_before["borrowed"]["amount"])
    borrowed_after = int(pos_after["borrowed"]["amount"])
    assert borrowed_after < borrowed_before, (
        f"Principal should be reduced after partial cover. "
        f"Before: {borrowed_before}, After: {borrowed_after}"
    )


def test_cover_position_auto_close_proceeds_cover_all(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test auto-close when swap proceeds fully cover repayment (needFromPayment = 0, covers lines 156-157)."""
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

def demo_cover_proceeds_cover_all(alice_addr, foo_name, bar_name, gov_addr):
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
    
    # Open position: borrow foo, collateral in bar
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Manipulate price to make held appreciate relative to borrowed
    # This makes swap proceeds high enough to cover repayment
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
    
    # Query position to get borrowed amount
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    position = position_query["position"]
    borrowed_amount = int(position["borrowed"]["amount"])
    # Payment >= total repayment to trigger auto-close
    # With price manipulation, swap proceeds should cover most/all of repayment
    payment_amount = borrowed_amount + 50
    
    # Cover position
    cover_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCoverPosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "payment": {"denom": foo_name, "amount": str(payment_amount)}
    })
    
    # Query position to verify it's closed
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "cover_result": cover_result["results"][0],
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
        "demo_cover_proceeds_cover_all",
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
    cover_result = demo_result["cover_result"]
    position_after = demo_result["position_after"]

    # Verify position is closed
    assert "position" in position_after, f"Missing position: {position_after}"
    position = position_after["position"]
    assert (
        position["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be closed, got: {position['status']}"

    # Verify response fields
    assert "closed" in cover_result, f"Missing closed field: {cover_result}"
    assert (
        cover_result["closed"] == True
    ), f"Closed should be True for auto-close, got: {cover_result['closed']}"
    assert "refunded" in cover_result, f"Missing refunded: {cover_result}"
    assert "profit" in cover_result, f"Missing profit: {cover_result}"


def test_cover_position_auto_close_with_profit(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test auto-close when swap proceeds exceed repayment (profit path, covers lines 201-217)."""
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

def demo_cover_with_profit(alice_addr, foo_name, bar_name, gov_addr):
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
    
    # Open position: borrow foo, collateral in bar
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Manipulate price aggressively to make held appreciate significantly
    # This makes swap proceeds exceed repayment, generating profit
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": foo_name, "amount": "10000"}],
        "min_output": [{"denom": bar_name, "amount": "1"}],
        "operations": [{
            "swap": {
                "pool_id": int(pool_id),
                "swap_in": {"denom": foo_name, "amount": "10000"}
            }
        }]
    })
    
    # Query position to get borrowed amount
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    position = position_query["position"]
    borrowed_amount = int(position["borrowed"]["amount"])
    # Payment >= total repayment to trigger auto-close
    payment_amount = borrowed_amount + 100
    
    # Cover position
    cover_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCoverPosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "payment": {"denom": foo_name, "amount": str(payment_amount)}
    })
    
    # Query position to verify it's closed
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "cover_result": cover_result["results"][0],
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
        "demo_cover_with_profit",
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
    cover_result = demo_result["cover_result"]
    position_after = demo_result["position_after"]

    # Verify position is closed
    assert "position" in position_after, f"Missing position: {position_after}"
    position = position_after["position"]
    assert (
        position["status"] == "POSITION_STATUS_CLOSED"
    ), f"Position should be closed, got: {position['status']}"

    # Verify response fields
    assert "closed" in cover_result, f"Missing closed field: {cover_result}"
    assert (
        cover_result["closed"] == True
    ), f"Closed should be True for auto-close, got: {cover_result['closed']}"
    assert "profit" in cover_result, f"Missing profit: {cover_result}"
    # Profit should be positive when proceeds exceed repayment (covers lines 212-217)
    profit_amount = int(cover_result["profit"]["amount"])
    assert profit_amount > 0, (
        f"Profit should be positive when proceeds exceed repayment. "
        f"Got: {profit_amount}, Full result: {json.dumps(cover_result, indent=2)}"
    )


def test_cover_position_partial_cover_cross_denom_collateral(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test partial cover with cross-denom collateral (covers lines 347-348 for collateral value calculation)."""
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

def demo_cover_partial_cross_denom_collateral(alice_addr, foo_name, bar_name, gov_addr):
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
    
    # Open position: borrow foo, collateral in bar (cross-denom)
    # This ensures collateral denom == held denom for the CR calculation path
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "1500"},
        "borrow": {"denom": foo_name, "amount": "1000"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Query position before cover
    position_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    # Partial cover: pay interest + some principal
    payment_amount = 250
    
    # Cover position with partial payment
    cover_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCoverPosition",
        "user": alice_addr,
        "position_id": int(position_id),
        "payment": {"denom": foo_name, "amount": str(payment_amount)}
    })
    
    # Query position after cover
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "cover_result": cover_result["results"][0],
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
        "demo_cover_partial_cross_denom_collateral",
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
    cover_result = demo_result["cover_result"]
    position_after = demo_result["position_after"]

    # Verify position is still open (partial cover)
    assert "position" in position_after, f"Missing position: {position_after}"
    position = position_after["position"]
    assert (
        position["status"] == "POSITION_STATUS_OPEN"
    ), f"Position should still be open after partial cover, got: {position['status']}"

    # Verify response fields
    assert "closed" in cover_result, f"Missing closed field: {cover_result}"
    assert (
        cover_result["closed"] == False
    ), f"Closed should be False for partial cover, got: {cover_result['closed']}"
    assert (
        "new_collateral_ratio" in cover_result
    ), f"Missing new_collateral_ratio: {cover_result}"
    # Verify collateral ratio is calculated (should be a string)
    assert isinstance(
        cover_result["new_collateral_ratio"], str
    ), f"New collateral ratio should be string. Got: {type(cover_result['new_collateral_ratio'])}"
