"""
WARNING: sdk.Coins ordering is canonicalized lexicographically by denom.

There is no inherent semantic meaning attached to coins[0] or coins[1]. The
array order is alphabetical and must never be used to infer roles such as
"base" or "quote". All business logic and assertions must key off the
denomination string (coin["denom"]) rather than the array index.

Test methodology below:
- We first query the pool and record the two denom strings returned.
- We then choose the borrow denom explicitly by name.
- We assert properties using denom values only, treating the held denom as the
  other pool denom relative to the chosen borrow denom.

The local variable names coin0_denom/coin1_denom in this file are labels that
mirror the current alphabetical ordering for readability only; they carry no
semantic significance and must not be used for decision-making outside these
controlled assertions.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_open_long_position_basic(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Integration test: Can create a LONG position with correct denom/amount calculation."""
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

def demo_long_position(alice_addr, foo_name, bar_name):
    # Create pool with two specific denoms (ordering is lexicographic/semanticless)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Query pool to inspect reserves (map by denom; ignore index order)
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    pool_coins = pool_query["pool"]["coins"]
    denom_to_amount = {c["denom"]: int(c["amount"]) for c in pool_coins}
    
    # LONG-like exposure: borrow foo_name; held denom is the other pool denom
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    position_result = sudo_position_result["results"][0]
    
    return {
        "position_id": position_result["position_id"],
        "held_denom": position_result["held"]["denom"],
        "held_amount": position_result["held"]["amount"],
        "reserves": denom_to_amount,
        "foo_name": foo_name,
        "bar_name": bar_name,
        "success": True
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
        "demo_long_position",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    result = deep_parse(query_result)

    print(f"Full query_result: {json.dumps(query_result, indent=2)}")
    print(f"Deep parsed result: {json.dumps(result, indent=2)}")

    assert (
        result is not None
    ), f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    # The actual script result is nested under result["result"]["result"]
    demo_result = result["result"]["result"]

    # Check for exceptions in execution
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    # Verify position was created
    assert (
        demo_result.get("success") is True
    ), f"Failed to create LONG position. Result: {json.dumps(demo_result, indent=2)}"

    # Extract parsed data
    position_id = demo_result["position_id"]
    reserves = demo_result["reserves"]
    foo_name = demo_result["foo_name"]
    bar_name = demo_result["bar_name"]

    # From immediate response
    held_denom_response = demo_result["held_denom"]
    held_amount_response = int(demo_result["held_amount"])

    # Pool amounts should be 10000 for both denoms
    assert (
        reserves[foo_name] == 10000
    ), f"reserve for {foo_name} incorrect: expected 10000, got {reserves[foo_name]}"
    assert (
        reserves[bar_name] == 10000
    ), f"reserve for {bar_name} incorrect: expected 10000, got {reserves[bar_name]}"

    # held denom should be the other denom (bar_name) when borrowing foo_name
    assert (
        held_denom_response == bar_name
    ), f"LONG: held denom should be {bar_name}, got {held_denom_response}"

    # Verify held amounts: borrow_amount * price(held/borrow)
    # price = reserves[bar]/reserves[foo] = 10000/10000 = 1.0
    assert (
        held_amount_response == 500
    ), f"LONG: held amount should be 500 (borrow * price), got {held_amount_response}"


def test_open_short_position_basic(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Integration test: Can create a SHORT position with correct denom/amount calculation."""
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

def demo_short_position(alice_addr, foo_name, bar_name):
    # Create pool with two specific denoms (ordering is lexicographic/semanticless)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Query pool to inspect reserves (map by denom; ignore index order)
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    pool_coins = pool_query["pool"]["coins"]
    denom_to_amount = {c["denom"]: int(c["amount"]) for c in pool_coins}
    
    # SHORT-like exposure: borrow bar_name; held denom is the other pool denom
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": foo_name, "amount": "750"},
        "borrow": {"denom": bar_name, "amount": "500"}
    })
    
    position_result = sudo_position_result["results"][0]
    
    return {
        "position_id": position_result["position_id"],
        "held_denom": position_result["held"]["denom"],
        "held_amount": position_result["held"]["amount"],
        "reserves": denom_to_amount,
        "foo_name": foo_name,
        "bar_name": bar_name,
        "success": True
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
        "demo_short_position",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    result = deep_parse(query_result)

    print(f"Full query_result: {json.dumps(query_result, indent=2)}")
    print(f"Deep parsed result: {json.dumps(result, indent=2)}")

    assert (
        result is not None
    ), f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    # The actual script result is nested under result["result"]["result"]
    demo_result = result["result"]["result"]

    # Check for exceptions in execution
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    # Verify position was created
    assert (
        demo_result.get("success") is True
    ), f"Failed to create SHORT position. Result: {json.dumps(demo_result, indent=2)}"

    # Extract parsed data
    position_id = demo_result["position_id"]
    reserves = demo_result["reserves"]
    foo_name = demo_result["foo_name"]
    bar_name = demo_result["bar_name"]

    # From immediate response
    held_denom_response = demo_result["held_denom"]
    held_amount_response = int(demo_result["held_amount"])

    # Pool amounts should be 10000 for both denoms
    assert (
        reserves[foo_name] == 10000
    ), f"reserve for {foo_name} incorrect: expected 10000, got {reserves[foo_name]}"
    assert (
        reserves[bar_name] == 10000
    ), f"reserve for {bar_name} incorrect: expected 10000, got {reserves[bar_name]}"

    # held denom should be the other denom (foo_name) when borrowing bar_name
    assert (
        held_denom_response == foo_name
    ), f"SHORT: held denom should be {foo_name}, got {held_denom_response}"

    # Verify held amounts: borrow_amount / price(borrow/held)
    # price(held/borrow) = reserves[foo]/reserves[bar] = 10000/10000 = 1.0
    assert (
        held_amount_response == 500
    ), f"SHORT: held amount should be 500 (borrow / price), got {held_amount_response}"


def test_open_position_pool_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that OpenPosition fails when pool doesn't exist."""
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

def demo_pool_not_found(alice_addr, foo_name, bar_name):
    # Try to open position on non-existent pool ID
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": "99999",
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
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
        "demo_pool_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for non-existent pool. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert "pool" in exception_msg, f"Expected 'pool' in error, got: {exception_msg}"
    assert (
        "not found" in exception_msg
    ), f"Expected 'not found' in error, got: {exception_msg}"


def test_open_position_insufficient_collateral_ratio(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that OpenPosition fails when CR < min_collateral_ratio."""
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

def demo_insufficient_cr(alice_addr, foo_name, bar_name):
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # CR = collateral/borrow = 100/1000 = 0.1 < 1.5 (min)
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "100"},
        "borrow": {"denom": foo_name, "amount": "1000"}
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
        "demo_insufficient_cr",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for insufficient CR. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "collateral" in exception_msg
    ), f"Expected 'collateral' in error, got: {exception_msg}"


def test_open_position_excessive_leverage(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that OpenPosition fails when leverage > max_leverage_ratio."""
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

def demo_excessive_leverage(alice_addr, foo_name, bar_name):
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "1.4",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # CR = 750/500 = 1.5 (passes min_collateral_ratio)
    # Leverage = (750 + 500) / 750 = 1.667 > 1.4 (max)
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
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
        "demo_excessive_leverage",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for excessive leverage. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"])
    assert (
        "leverage" in exception_msg.lower()
    ), f"Expected leverage error, got: {exception_msg}"


def test_open_position_borrow_cap_exceeded(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that OpenPosition fails when borrow exceeds max_borrow_percent."""
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

def demo_borrow_cap_exceeded(alice_addr, foo_name, bar_name):
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.5"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Borrow 6000 when max = 10000 * 0.5 = 5000
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "9000"},
        "borrow": {"denom": foo_name, "amount": "6000"}
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
        "demo_borrow_cap_exceeded",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for borrow cap exceeded. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "borrow" in exception_msg
    ), f"Expected 'borrow' in error, got: {exception_msg}"
    assert "cap" in exception_msg, f"Expected 'cap' in error, got: {exception_msg}"


def test_open_position_invalid_collateral_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that OpenPosition fails when collateral denom not in pool."""
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

def demo_invalid_collateral_denom(alice_addr, foo_name, bar_name):
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Collateral in udys (not in pool)
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": "udys", "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
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
        "demo_invalid_collateral_denom",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for invalid collateral denom. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "collateral" in exception_msg
    ), f"Expected 'collateral' in error, got: {exception_msg}"
    assert "denom" in exception_msg, f"Expected 'denom' in error, got: {exception_msg}"


def test_open_position_invalid_borrow_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that OpenPosition fails when borrow denom not in pool."""
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

def demo_invalid_borrow_denom(alice_addr, foo_name, bar_name):
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Borrow udys (not in pool)
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": "udys", "amount": "500"}
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
        "demo_invalid_borrow_denom",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for invalid borrow denom. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "borrow" in exception_msg
    ), f"Expected 'borrow' in error, got: {exception_msg}"
    assert "denom" in exception_msg, f"Expected 'denom' in error, got: {exception_msg}"


def test_open_position_zero_collateral(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that OpenPosition fails with zero or negative collateral amount."""
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

def demo_zero_collateral(alice_addr, foo_name, bar_name):
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "0"},
        "borrow": {"denom": foo_name, "amount": "500"}
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
        "demo_zero_collateral",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for zero collateral. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"])
    assert (
        "collateral" in exception_msg.lower()
    ), f"Expected invalid collateral error, got: {exception_msg}"


def test_open_position_zero_borrow(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that OpenPosition fails with zero or negative borrow amount."""
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

def demo_zero_borrow(alice_addr, foo_name, bar_name):
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20.0",
        "max_borrow_percent": "0.8"
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "0"}
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
        "demo_zero_borrow",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for zero borrow. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"])
    assert (
        "borrow" in exception_msg.lower()
    ), f"Expected invalid borrow error, got: {exception_msg}"
