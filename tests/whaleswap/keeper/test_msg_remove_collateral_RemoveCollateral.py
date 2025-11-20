"""
Test RemoveCollateral keeper function for leverage positions.

Tests the RemoveCollateral message handler which allows position owners to withdraw
collateral from their positions while maintaining healthy collateral ratios.

Covers all validation paths and happy paths for RemoveCollateral function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_remove_collateral_basic_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful removal of collateral (happy path with debt)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
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

def demo_remove_collateral(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
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
        "collateral": {"denom": bar_name, "amount": "1000"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    remove_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "250"}
    })
    
    return {
        "position_id": position_id,
        "remove_result": remove_result["results"][0]
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
        "demo_remove_collateral",
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
    remove_result = demo_result["remove_result"]

    assert "collateral_removed" in remove_result, f"Missing collateral_removed: {remove_result}"
    assert "new_collateral" in remove_result, f"Missing new_collateral: {remove_result}"
    assert "new_collateral_ratio" in remove_result, f"Missing new_collateral_ratio: {remove_result}"
    assert (
        remove_result["collateral_removed"]["amount"] == "250"
    ), f"Expected 250, got {remove_result['collateral_removed']['amount']}"
    assert (
        remove_result["collateral_removed"]["denom"] == bar_name
    ), f"Expected {bar_name}, got {remove_result['collateral_removed']['denom']}"
    assert (
        remove_result["new_collateral"]["amount"] == "750"
    ), f"Expected 750, got {remove_result['new_collateral']['amount']}"
    assert (
        remove_result["new_collateral"]["denom"] == bar_name
    ), f"Expected {bar_name}, got {remove_result['new_collateral']['denom']}"


def test_remove_collateral_position_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveCollateral fails when position does not exist (line 21-24)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
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

def demo_remove_collateral_nonexistent(alice_addr, bar_name):
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": 99999,
        "position_id": 99999,
        "collateral": {"denom": bar_name, "amount": "100"}
    })
"""

    kwargs = json.dumps({"alice_addr": alice_addr, "bar_name": bar_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_remove_collateral_nonexistent",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for non-existent position: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "not found" in exception_msg
    ), f"Should mention 'not found', got: {exception_msg}"


def test_remove_collateral_unauthorized_user(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveCollateral fails when user is not position owner (line 28-30)."""
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

def demo_remove_collateral_unauthorized(alice_addr, bob_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
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
        "collateral": {"denom": bar_name, "amount": "1000"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": bob_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "250"}
    })
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
        "demo_remove_collateral_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for unauthorized user: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "unauthorized" in exception_msg
    ), f"Should mention unauthorized. Got: {exception_msg}"
    assert (
        "owner" in exception_msg
    ), f"Should mention owner. Got: {exception_msg}"


def test_remove_collateral_pool_id_mismatch(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveCollateral fails when pool_id doesn't match position's pool (line 31-33)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
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

def demo_remove_collateral_pool_mismatch(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
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
        "collateral": {"denom": bar_name, "amount": "1000"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": 99999,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "250"}
    })
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
        "demo_remove_collateral_pool_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for pool_id mismatch: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "pool_id mismatch" in exception_msg
    ), f"Should mention pool_id mismatch, got: {exception_msg}"


def test_remove_collateral_denom_mismatch(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveCollateral fails when collateral denom doesn't match position's collateral denom (line 34-36)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
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

def demo_remove_collateral_denom_mismatch(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
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
        "collateral": {"denom": bar_name, "amount": "1000"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": foo_name, "amount": "250"}
    })
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
        "demo_remove_collateral_denom_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for denom mismatch: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "denom mismatch" in exception_msg
    ), f"Should mention denom mismatch, got: {exception_msg}"


def test_remove_collateral_too_much(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveCollateral fails when removing more collateral than available (line 37-39)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
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

def demo_remove_collateral_too_much(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
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
        "collateral": {"denom": bar_name, "amount": "1000"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "1000"}
    })
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
        "demo_remove_collateral_too_much",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for removing too much: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "more collateral than available" in exception_msg
    ), f"Should mention 'more collateral than available', got: {exception_msg}"


def test_remove_collateral_non_positive_amount(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveCollateral fails when collateral amount is not positive (line 18-20)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
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

def demo_remove_collateral_zero_amount(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
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
        "collateral": {"denom": bar_name, "amount": "1000"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_id = position_result["results"][0]["position_id"]
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "0"}
    })
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
        "demo_remove_collateral_zero_amount",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for zero amount: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "must be positive" in exception_msg
    ), f"Should mention 'must be positive', got: {exception_msg}"

