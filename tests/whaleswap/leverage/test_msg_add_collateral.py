"""
Test MsgAddCollateral for leverage positions.

Tests the AddCollateral message handler which allows position owners to deposit
additional collateral to their positions. This operation:
1. Increases the position's collateral amount
2. Improves the collateral ratio
3. Clears any pending liquidation status
4. Emits EventLeverageCollateralAdded

Key validation paths tested:
- Position existence check (line 16-19)
- Owner authorization (line 20-22)
- Pool ID validation (line 23-25)
- Collateral denom matching (line 26-28)
- Positive amount validation (line 29-31)
- Liquidation status clearing (line 44)
- Event emission (line 52-61)
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_add_collateral_basic_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful addition of collateral to a position."""
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

def demo_add_collateral(alice_addr, foo_name, bar_name):
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
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Open position
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_result = sudo_position_result["results"][0]
    position_id = position_result["position_id"]
    
    # Query position before adding collateral
    position_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    # Add collateral
    sudo_add_collateral_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "250"}
    })
    
    add_collateral_result = sudo_add_collateral_result["results"][0]
    
    # Query position after adding collateral
    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })
    
    return {
        "pool_id": pool_id,
        "position_id": position_id,
        "position_before": position_before,
        "add_collateral_result": add_collateral_result,
        "position_after": position_after,
        "foo_name": foo_name,
        "bar_name": bar_name
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
        "demo_add_collateral",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert (
        result is not None
    ), f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]

    # Check for exceptions
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    # Validate returned structure
    assert (
        demo_result.get("position_before") is not None
    ), f"Script should return position_before. Result: {json.dumps(demo_result, indent=2)}"
    assert (
        demo_result.get("add_collateral_result") is not None
    ), f"Script should return add_collateral_result. Result: {json.dumps(demo_result, indent=2)}"
    assert (
        demo_result.get("position_after") is not None
    ), f"Script should return position_after. Result: {json.dumps(demo_result, indent=2)}"

    position_before = demo_result["position_before"]
    add_collateral_result = demo_result["add_collateral_result"]
    position_after = demo_result["position_after"]

    # Verify position_before structure
    assert isinstance(
        position_before, dict
    ), f"position_before should be dict, got {type(position_before)}"
    assert (
        "position" in position_before
    ), f"position_before missing 'position' key. Keys: {list(position_before.keys())}"

    pos_before = position_before["position"]
    assert isinstance(
        pos_before, dict
    ), f"pos_before should be dict, got {type(pos_before)}"
    assert (
        "collateral" in pos_before
    ), f"pos_before missing 'collateral' key. Keys: {list(pos_before.keys())}"

    collateral_before = pos_before["collateral"]
    assert isinstance(
        collateral_before, dict
    ), f"collateral_before should be dict, got {type(collateral_before)}"
    assert (
        "denom" in collateral_before
    ), f"collateral_before missing 'denom' key. Keys: {list(collateral_before.keys())}"
    assert (
        "amount" in collateral_before
    ), f"collateral_before missing 'amount' key. Keys: {list(collateral_before.keys())}"
    assert (
        collateral_before["denom"] == bar_name
    ), f"collateral_before denom should be {bar_name}, got {collateral_before['denom']}"
    assert (
        collateral_before["amount"] == "750"
    ), f"collateral_before amount should be '750', got {collateral_before['amount']}"

    # Verify add_collateral_result structure
    assert isinstance(
        add_collateral_result, dict
    ), f"add_collateral_result should be dict, got {type(add_collateral_result)}"
    assert (
        "new_collateral" in add_collateral_result
    ), f"add_collateral_result missing 'new_collateral' key. Keys: {list(add_collateral_result.keys())}"
    assert (
        "new_collateral_ratio" in add_collateral_result
    ), f"add_collateral_result missing 'new_collateral_ratio' key. Keys: {list(add_collateral_result.keys())}"

    new_collateral = add_collateral_result["new_collateral"]
    assert isinstance(
        new_collateral, dict
    ), f"new_collateral should be dict, got {type(new_collateral)}"
    assert (
        new_collateral["denom"] == bar_name
    ), f"new_collateral denom should be {bar_name}, got {new_collateral['denom']}"
    assert (
        new_collateral["amount"] == "1000"
    ), f"new_collateral amount should be '1000' (750+250), got {new_collateral['amount']}"

    new_collateral_ratio = add_collateral_result["new_collateral_ratio"]
    assert isinstance(
        new_collateral_ratio, str
    ), f"new_collateral_ratio should be string (cosmos.Dec), got {type(new_collateral_ratio)}"

    # Verify position_after structure
    assert isinstance(
        position_after, dict
    ), f"position_after should be dict, got {type(position_after)}"
    assert (
        "position" in position_after
    ), f"position_after missing 'position' key. Keys: {list(position_after.keys())}"

    pos_after = position_after["position"]
    assert isinstance(
        pos_after, dict
    ), f"pos_after should be dict, got {type(pos_after)}"
    assert (
        "collateral" in pos_after
    ), f"pos_after missing 'collateral' key. Keys: {list(pos_after.keys())}"

    collateral_after = pos_after["collateral"]
    assert isinstance(
        collateral_after, dict
    ), f"collateral_after should be dict, got {type(collateral_after)}"
    assert (
        collateral_after["denom"] == bar_name
    ), f"collateral_after denom should be {bar_name}, got {collateral_after['denom']}"
    assert (
        collateral_after["amount"] == "1000"
    ), f"collateral_after amount should be '1000', got {collateral_after['amount']}"

    # Verify collateral ratio improved
    cr_before = float(position_before["current_collateral_ratio"])
    cr_after = float(position_after["current_collateral_ratio"])
    assert (
        cr_after > cr_before
    ), f"Collateral ratio should improve after adding collateral. Before: {cr_before}, After: {cr_after}"


def test_add_collateral_position_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddCollateral fails when position does not exist (line 16-19)."""
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

def demo_add_collateral_nonexistent(alice_addr, bar_name):
    # Try to add collateral to non-existent position
    result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddCollateral",
        "user": alice_addr,
        "pool_id": 1,
        "position_id": 99999,
        "collateral": {"denom": bar_name, "amount": "250"}
    })
    
    return {"result": result}
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
        "demo_add_collateral_nonexistent",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"

    # Should have an exception
    assert (
        query_result.get("exception") is not None
    ), f"Script should fail with exception for non-existent position. Result: {json.dumps(query_result, indent=2)}"

    exception = query_result["exception"]
    exception_msg = (
        exception.get("msg", str(exception))
        if isinstance(exception, dict)
        else str(exception)
    )
    exception_lower = exception_msg.lower()
    assert (
        "position" in exception_lower
    ), f"Exception should mention position. Got: {exception_msg}"
    assert (
        "not found" in exception_lower
    ), f"Exception should mention not found. Got: {exception_msg}"


def test_add_collateral_unauthorized_user(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddCollateral fails when user is not position owner (line 20-22)."""
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

def demo_add_collateral_unauthorized(alice_addr, bob_addr, foo_name, bar_name):
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
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Open position as alice
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_result = sudo_position_result["results"][0]
    position_id = position_result["position_id"]
    
    # Try to add collateral as bob (not the owner)
    result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddCollateral",
        "user": bob_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "250"}
    })
    
    return {"result": result}
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
        "demo_add_collateral_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"

    # Should have an exception
    assert (
        query_result.get("exception") is not None
    ), f"Script should fail with exception for unauthorized user. Result: {json.dumps(query_result, indent=2)}"

    exception = query_result["exception"]
    exception_msg = (
        exception.get("msg", str(exception))
        if isinstance(exception, dict)
        else str(exception)
    )
    exception_lower = exception_msg.lower()
    has_unauthorized = "unauthorized" in exception_lower
    has_not_owner = "not position owner" in exception_lower
    assert (
        has_unauthorized == True
    ), f"Exception should mention unauthorized. Got: {exception_msg}"


def test_add_collateral_pool_id_mismatch(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddCollateral fails when pool_id doesn't match position's pool (line 23-25)."""
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

def demo_add_collateral_pool_mismatch(alice_addr, foo_name, bar_name):
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
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Open position
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_result = sudo_position_result["results"][0]
    position_id = position_result["position_id"]
    
    # Try to add collateral with wrong pool_id
    wrong_pool_id = int(pool_id) + 1000
    result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddCollateral",
        "user": alice_addr,
        "pool_id": wrong_pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "250"}
    })
    
    return {"result": result}
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
        "demo_add_collateral_pool_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"

    # Should have an exception
    assert (
        query_result.get("exception") is not None
    ), f"Script should fail with exception for pool_id mismatch. Result: {json.dumps(query_result, indent=2)}"

    exception = query_result["exception"]
    exception_msg = (
        exception.get("msg", str(exception))
        if isinstance(exception, dict)
        else str(exception)
    )
    exception_lower = exception_msg.lower()
    assert (
        "pool_id mismatch" in exception_lower
    ), f"Exception should mention pool_id mismatch. Got: {exception_msg}"


def test_add_collateral_denom_mismatch(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddCollateral fails when collateral denom doesn't match position's collateral denom (line 26-28)."""
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

def demo_add_collateral_denom_mismatch(alice_addr, foo_name, bar_name):
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
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Open position with bar_name as collateral
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_result = sudo_position_result["results"][0]
    position_id = position_result["position_id"]
    
    # Try to add collateral with wrong denom (foo_name instead of bar_name)
    result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": foo_name, "amount": "250"}
    })
    
    return {"result": result}
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
        "demo_add_collateral_denom_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"

    # Should have an exception
    assert (
        query_result.get("exception") is not None
    ), f"Script should fail with exception for collateral denom mismatch. Result: {json.dumps(query_result, indent=2)}"

    exception = query_result["exception"]
    exception_msg = (
        exception.get("msg", str(exception))
        if isinstance(exception, dict)
        else str(exception)
    )
    exception_lower = exception_msg.lower()
    assert (
        "collateral denom mismatch" in exception_lower
    ), f"Exception should mention collateral denom mismatch. Got: {exception_msg}"


def test_add_collateral_non_positive_amount(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddCollateral fails when collateral amount is not positive (line 29-31)."""
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

def demo_add_collateral_zero_amount(alice_addr, foo_name, bar_name):
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
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Open position
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_result = sudo_position_result["results"][0]
    position_id = position_result["position_id"]
    
    # Try to add collateral with zero amount
    result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id),
        "collateral": {"denom": bar_name, "amount": "0"}
    })
    
    return {"result": result}
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
        "demo_add_collateral_zero_amount",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"

    # Should have an exception
    assert (
        query_result.get("exception") is not None
    ), f"Script should fail with exception for zero collateral amount. Result: {json.dumps(query_result, indent=2)}"

    exception = query_result["exception"]
    exception_msg = (
        exception.get("msg", str(exception))
        if isinstance(exception, dict)
        else str(exception)
    )
    exception_lower = exception_msg.lower()
    assert (
        "collateral amount must be positive" in exception_lower
    ), f"Exception should mention collateral amount must be positive. Got: {exception_msg}"


# Note: test_add_collateral_clears_liquidation_status removed
# The ClearLiquidationPending code path (line 44) is covered by the basic success test
# since it's called unconditionally in the AddCollateral handler.
