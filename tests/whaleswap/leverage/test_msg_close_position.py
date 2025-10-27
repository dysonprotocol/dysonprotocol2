"""
Test coverage for MsgClosePosition keeper method.

ClosePosition closes leveraged positions and settles collateral/profit.
Tests cover both happy path and all error validation paths.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_close_position_happy_path_long(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Happy path: Close a LONG position and verify profit settlement.

    Uses CLI transactions (not query/sudo) so blocks advance naturally between operations.
    Uses charlie to avoid depleting alice/bob's tokens from other tests.
    """
    dysond = chainnet[0]
    charlie_name = leverage_accounts["charlie"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool via CLI (smaller amounts to avoid token depletion from session-scoped fixtures)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"5000{foo_name}",
        "--coins",
        f"5000{bar_name}",
        "--fee-pct",
        "0.003",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "20.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        charlie_name,
    )

    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"

    # Extract pool_id
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = pool_id_attrs[0].strip('"')

    # Open LONG position (borrow foo, hold bar)
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"400{bar_name}",
        "--borrow",
        f"250{foo_name}",
        "--from",
        charlie_name,
    )

    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"

    # Extract position_id
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = position_id_attrs[0].strip('"')

    # Close position (blocks have advanced, CanCloseBefore passes)
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--from",
        charlie_name,
    )

    assert close_result.get("code", 1) == 0, f"Close position failed: {close_result}"

    # Verify EventLeveragePositionClosed was emitted
    close_events = [
        event
        for event in close_result.get("events", [])
        if event.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
    ]
    assert len(close_events) > 0, "EventLeveragePositionClosed not found"

    # Verify profit attribute exists
    profit_attrs = [
        attr
        for attr in close_events[0].get("attributes", [])
        if attr.get("key") == "profit"
    ]
    assert len(profit_attrs) > 0, "profit attribute not found"

    # Verify accrued_interest attribute exists
    interest_attrs = [
        attr
        for attr in close_events[0].get("attributes", [])
        if attr.get("key") == "accrued_interest"
    ]
    assert len(interest_attrs) > 0, "accrued_interest attribute not found"


def test_close_position_block_delay_enforced(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition enforces block delay (can't close in same block as creation).

    In query mode, all _sudo calls execute at same blockHeight, so CanCloseBefore
    returns false and triggers ErrBlockDelayNotPassed. This validates the check exists.
    Uses bob to avoid token depletion from alice's happy path test.
    """
    dysond = chainnet[0]
    bob_addr = leverage_accounts["bob"]["addr"]
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

def demo_block_delay_enforced(bob_addr, foo_name, bar_name):
    # Create pool (minimal amounts)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": bob_addr,
        "coins": [
            {"denom": foo_name, "amount": "500"},
            {"denom": bar_name, "amount": "500"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Open position
    sudo_open_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": bob_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "30"},
        "borrow": {"denom": foo_name, "amount": "20"}
    })
    position_id = sudo_open_result["results"][0]["position_id"]
    
    # Try to close at same block height - should fail
    sudo_close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": bob_addr,
        "position_id": position_id
    })
    
    return {"unexpected": "should have failed"}
"""
    kwargs = json.dumps(
        {"bob_addr": bob_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_block_delay_enforced",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for block delay. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert "block" in exception_msg, f"Expected 'block' in error, got: {exception_msg}"
    assert (
        "locked" in exception_msg
    ), f"Expected 'locked' in error, got: {exception_msg}"


def test_close_position_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition fails when position doesn't exist."""
    dysond = chainnet[0]
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

def demo_position_not_found(alice_addr):
    # Try to close non-existent position
    sudo_close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": "99999"
    })
    return {"unexpected": "should have failed"}
"""
    kwargs = json.dumps({"alice_addr": alice_addr})
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

    assert (
        "exception" in query_result
    ), f"Expected exception for non-existent position. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "position" in exception_msg
    ), f"Expected 'position' in error, got: {exception_msg}"
    assert (
        "not found" in exception_msg
    ), f"Expected 'not found' in error, got: {exception_msg}"


def test_close_position_not_owner(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition fails when caller is not the position owner."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
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

def demo_not_owner(alice_addr, bob_addr, foo_name, bar_name):
    # Create pool (minimal amounts to avoid token depletion)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "500"},
            {"denom": bar_name, "amount": "500"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Alice opens position
    sudo_open_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "30"},
        "borrow": {"denom": foo_name, "amount": "20"}
    })
    position_id = sudo_open_result["results"][0]["position_id"]
    
    # Bob tries to close Alice's position
    sudo_close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": bob_addr,
        "position_id": position_id
    })
    return {"unexpected": "should have failed"}
"""
    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
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
        "demo_not_owner",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for unauthorized close. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "unauthorized" in exception_msg
    ), f"Expected 'unauthorized' in error, got: {exception_msg}"


def test_close_position_invalid_user_address(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition fails with invalid/malformed user address."""
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

def demo_invalid_address(alice_addr, foo_name, bar_name):
    # Create pool (minimal amounts to avoid token depletion)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "500"},
            {"denom": bar_name, "amount": "500"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Open position
    sudo_open_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "30"},
        "borrow": {"denom": foo_name, "amount": "20"}
    })
    position_id = sudo_open_result["results"][0]["position_id"]
    
    # Try to close with invalid address format
    sudo_close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": "invalid_address_format",
        "position_id": position_id
    })
    return {"unexpected": "should have failed"}
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
        "demo_invalid_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for invalid address. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "address" in exception_msg
    ), f"Expected 'address' in error, got: {exception_msg}"
