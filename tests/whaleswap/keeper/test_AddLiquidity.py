"""
Test AddLiquidity keeper function for pool liquidity.

Tests the AddLiquidity message handler which allows majority owners to add
liquidity to pools. Supports both proportional (balanced) and unbalanced modes.

Covers all validation paths and happy paths for AddLiquidity function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_add_liquidity_proportional_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful proportional liquidity addition (happy path)."""
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

def demo_add_liquidity_proportional(alice_addr, foo_name, bar_name):
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
    
    add_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "1000"},
            {"denom": bar_name, "amount": "1000"}
        ],
        "unbalanced": False
    })
    
    return {
        "pool_id": pool_id,
        "add_result": add_result["results"][0]
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
        "demo_add_liquidity_proportional",
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
    add_result = demo_result["add_result"]

    assert "shares" in add_result, f"Missing shares: {add_result}"
    assert (
        int(add_result["shares"]) > 0
    ), f"Shares should be > 0, got {add_result['shares']}"


def test_add_liquidity_unbalanced_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful unbalanced liquidity addition (happy path)."""
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

def demo_add_liquidity_unbalanced(alice_addr, foo_name, bar_name):
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
    
    add_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "1000"},
            {"denom": bar_name, "amount": "1000"}
        ],
        "unbalanced": True
    })
    
    return {
        "pool_id": pool_id,
        "add_result": add_result["results"][0]
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
        "demo_add_liquidity_unbalanced",
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
    add_result = demo_result["add_result"]

    assert "shares" in add_result, f"Missing shares: {add_result}"
    assert (
        int(add_result["shares"]) > 0
    ), f"Shares should be > 0, got {add_result['shares']}"


def test_add_liquidity_pool_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddLiquidity fails when pool does not exist (line 55-57)."""
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

def demo_add_liquidity_nonexistent(alice_addr, foo_name, bar_name):
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": 99999,
        "amounts": [
            {"denom": foo_name, "amount": "1000"},
            {"denom": bar_name, "amount": "1000"}
        ],
        "unbalanced": False
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
        "demo_add_liquidity_nonexistent",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for non-existent pool: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "not found" in exception_msg
    ), f"Should mention 'not found', got: {exception_msg}"


def test_add_liquidity_wrong_number_of_denoms(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddLiquidity fails when amounts don't have exactly 2 denoms (line 74-75)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
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

def demo_add_liquidity_wrong_denoms(alice_addr, foo_name):
    base, quote = sorted([foo_name, "udys"])
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": "udys", "amount": "10000"}
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
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "1000"}
        ],
        "unbalanced": False
    })
"""

    kwargs = json.dumps({"alice_addr": alice_addr, "foo_name": foo_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_add_liquidity_wrong_denoms",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for wrong number of denoms: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    # Proportional add with 1 coin triggers "proportional add requires exactly 2 coins" error
    assert (
        "proportional add requires exactly 2 coins" in exception_msg
    ), f"Should mention 'proportional add requires exactly 2 coins', got: {exception_msg}"


def test_add_liquidity_denom_mismatch(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddLiquidity fails when amount denoms don't match pool denoms (line 80-81)."""
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

def demo_add_liquidity_denom_mismatch(alice_addr, foo_name, bar_name):
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
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": "udys", "amount": "1000"},
            {"denom": bar_name, "amount": "1000"}
        ],
        "unbalanced": False
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
        "demo_add_liquidity_denom_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for denom mismatch: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    # Unknown denom triggers DenomsSubsetOf check: "amount denoms must be subset of pool denoms"
    has_denom = "denom" in exception_msg
    has_subset = "subset" in exception_msg
    assert has_denom == True, f"Should mention 'denom'. Got: {exception_msg}"
    assert has_subset == True, f"Should mention 'subset'. Got: {exception_msg}"


def test_add_liquidity_non_positive_amounts(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddLiquidity fails when amounts are not positive (line 83-84)."""
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

def demo_add_liquidity_zero_amounts(alice_addr, foo_name, bar_name):
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
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "0"},
            {"denom": bar_name, "amount": "1000"}
        ],
        "unbalanced": False
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
        "demo_add_liquidity_zero_amounts",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for zero amounts: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    # Zero amounts get filtered out by sdk.NewCoins, leaving 1 coin
    # Proportional add then fails with "proportional add requires exactly 2 coins" error
    assert (
        "proportional add requires exactly 2 coins" in exception_msg
    ), f"Should mention 'proportional add requires exactly 2 coins' (zero amounts filtered). Got: {exception_msg}"
