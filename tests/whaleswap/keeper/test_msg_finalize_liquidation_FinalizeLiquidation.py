"""
Test FinalizeLiquidation keeper function for leverage positions.

Tests the FinalizeLiquidation message handler which completes leveraged position liquidation.
This is a permissionless operation where any liquidator can finalize an initialized liquidation.

Covers happy paths for FinalizeLiquidation function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_finalize_liquidation_basic_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test basic liquidation finalization (covers main happy path)."""
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

def demo_finalize_liquidation_basic(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
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
    
    # Create pool with sufficient size to allow borrowing
    # Pool: 20 foo, 20 bar
    # max_borrow_percent = 0.8, so max borrow = 20 * 0.8 = 16
    # We'll borrow 10, which is within the cap
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "20"},
            {"denom": bar_name, "amount": "20"}
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
    # Note: amounts must be integers (coin amounts are big.Int)
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
    position_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    # Finalize liquidation
    finalize_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgFinalizeLiquidation",
        "liquidator": bob_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })
    
    # Query position after finalization
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "pool_id": pool_id,
        "finalize_result": finalize_result["results"][0],
        "position_before": position_before,
        "position_after": position_after
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
        "demo_finalize_liquidation_basic",
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
    finalize_result = demo_result["finalize_result"]
    position_after = demo_result["position_after"]

    # Verify position is liquidated
    assert "position" in position_after, f"Missing position: {position_after}"
    position = position_after["position"]
    assert (
        position["status"] == "POSITION_STATUS_LIQUIDATED"
    ), f"Position should be liquidated, got: {position['status']}"

    # Verify response fields
    assert (
        "collateral_received" in finalize_result
    ), f"Missing collateral_received: {finalize_result}"
    assert (
        "repayment_amount" in finalize_result
    ), f"Missing repayment_amount: {finalize_result}"
    assert (
        "accrued_interest" in finalize_result
    ), f"Missing accrued_interest: {finalize_result}"

    # Verify collateral was sent to liquidator
    collateral = finalize_result["collateral_received"]
    assert isinstance(
        collateral, dict
    ), f"Collateral should be dict, got {type(collateral)}"
    assert "denom" in collateral, f"Missing denom in collateral: {collateral}"
    assert "amount" in collateral, f"Missing amount in collateral: {collateral}"
    assert (
        collateral["denom"] == foo_name
    ), f"Collateral denom should be {foo_name}, got {collateral['denom']}"

    # Verify repayment amount
    repayment = finalize_result["repayment_amount"]
    assert isinstance(
        repayment, dict
    ), f"Repayment should be dict, got {type(repayment)}"
    assert "denom" in repayment, f"Missing denom in repayment: {repayment}"
    assert "amount" in repayment, f"Missing amount in repayment: {repayment}"
    assert (
        repayment["denom"] == foo_name
    ), f"Repayment denom should be {foo_name}, got {repayment['denom']}"


def test_finalize_liquidation_with_interest(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test liquidation finalization with accrued interest (covers interest calculation path)."""
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

def demo_finalize_liquidation_with_interest(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
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
    # Using same-denom avoids price conversion complexity in InitializeLiquidation
    position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "11"},
        "borrow": {"denom": foo_name, "amount": "10"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    # Query position to get initial borrowed amount
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    # Initialize liquidation
    init_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": bob_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })
    
    # Finalize liquidation
    finalize_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgFinalizeLiquidation",
        "liquidator": bob_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })
    
    return {
        "position_id": position_id,
        "pool_id": pool_id,
        "finalize_result": finalize_result["results"][0],
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
        "demo_finalize_liquidation_with_interest",
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
    finalize_result = demo_result["finalize_result"]

    # Verify response fields
    assert (
        "collateral_received" in finalize_result
    ), f"Missing collateral_received: {finalize_result}"
    assert (
        "repayment_amount" in finalize_result
    ), f"Missing repayment_amount: {finalize_result}"
    assert (
        "accrued_interest" in finalize_result
    ), f"Missing accrued_interest: {finalize_result}"

    # Verify accrued interest is present (may be small but should be calculated)
    accrued_interest = finalize_result["accrued_interest"]
    assert isinstance(
        accrued_interest, dict
    ), f"Accrued interest should be dict, got {type(accrued_interest)}"
    assert (
        "amount" in accrued_interest
    ), f"Missing amount in accrued_interest: {accrued_interest}"
    assert (
        "denom" in accrued_interest
    ), f"Missing denom in accrued_interest: {accrued_interest}"

    # Verify repayment includes principal + interest
    repayment = finalize_result["repayment_amount"]
    repayment_amount = int(repayment["amount"])
    accrued_amount = int(accrued_interest["amount"])

    # Repayment should be >= borrowed amount (principal + interest)
    assert (
        repayment_amount >= 10
    ), f"Repayment should be at least 10 (borrowed), got {repayment_amount}"
