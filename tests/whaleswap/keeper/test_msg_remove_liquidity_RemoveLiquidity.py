"""
Test RemoveLiquidity keeper function for pool liquidity.

Tests the RemoveLiquidity message handler which allows liquidity providers to burn
shares and withdraw proportional reserves from pools. Supports both partial and
full exit (pool deletion).

Covers all validation paths and happy paths for RemoveLiquidity function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_remove_liquidity_partial_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful partial liquidity removal (happy path)."""
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

def demo_remove_liquidity_partial(alice_addr, foo_name, bar_name):
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
    
    # Add liquidity to get shares
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
    
    shares_minted = add_result["results"][0]["shares"]
    
    # Query pool to get shares denom
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    shares_denom = pool_query["pool"]["shares_denom"]
    
    # Remove partial liquidity (remove half of shares)
    shares_to_remove = str(int(shares_minted) // 2)
    remove_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "shares": shares_to_remove
    })
    
    return {
        "pool_id": pool_id,
        "shares_minted": shares_minted,
        "shares_to_remove": shares_to_remove,
        "remove_result": remove_result["results"][0],
        "shares_denom": shares_denom
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
        "demo_remove_liquidity_partial",
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

    assert "amount" in remove_result, f"Missing amount: {remove_result}"
    assert isinstance(
        remove_result["amount"], list
    ), f"Amount should be list, got {type(remove_result['amount'])}"
    assert (
        len(remove_result["amount"]) == 2
    ), f"Should return 2 coins, got {len(remove_result['amount'])}"

    # Verify coins are positive
    for coin in remove_result["amount"]:
        assert (
            int(coin["amount"]) > 0
        ), f"Coin amount should be > 0, got {coin['amount']}"


def test_remove_liquidity_full_exit_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful full liquidity removal (pool deletion)."""
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

def demo_remove_liquidity_full_exit(alice_addr, foo_name, bar_name):
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
    
    # Query pool to get total shares
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    shares_denom = pool_query["pool"]["shares_denom"]
    
    # Query bank supply to get total shares
    supply_query = _query({
        "@type": "/cosmos.bank.v1beta1.QuerySupplyOfRequest",
        "denom": shares_denom
    })
    
    total_shares = supply_query["amount"]["amount"]
    
    # Remove all liquidity (full exit)
    remove_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "shares": total_shares
    })
    
    return {
        "pool_id": pool_id,
        "total_shares": total_shares,
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
        "demo_remove_liquidity_full_exit",
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

    assert "amount" in remove_result, f"Missing amount: {remove_result}"
    assert isinstance(
        remove_result["amount"], list
    ), f"Amount should be list, got {type(remove_result['amount'])}"
    assert (
        len(remove_result["amount"]) == 2
    ), f"Should return 2 coins, got {len(remove_result['amount'])}"


def test_remove_liquidity_pool_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveLiquidity fails when pool does not exist (line 49-52)."""
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

def demo_remove_liquidity_nonexistent(alice_addr):
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": alice_addr,
        "pool_id": 99999,
        "shares": "1000"
    })
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
        "demo_remove_liquidity_nonexistent",
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


def test_remove_liquidity_invalid_shares(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveLiquidity fails when shares is invalid (line 54-57)."""
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

def demo_remove_liquidity_invalid_shares(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "shares": "0"
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
        "demo_remove_liquidity_invalid_shares",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid shares: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "invalid shares" in exception_msg
    ), f"Should mention 'invalid shares', got: {exception_msg}"


def test_remove_liquidity_insufficient_shares(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveLiquidity fails when signer doesn't have enough shares (line 62-65)."""
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

def demo_remove_liquidity_insufficient(alice_addr, bob_addr, foo_name, bar_name):
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
    
    # Bob tries to remove liquidity without having shares
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": bob_addr,
        "pool_id": pool_id,
        "shares": "1000"
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
        "demo_remove_liquidity_insufficient",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for insufficient shares: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "insufficient" in exception_msg
    ), f"Should mention insufficient, got: {exception_msg}"
    assert "shares" in exception_msg, f"Should mention shares, got: {exception_msg}"


def test_remove_liquidity_shares_too_small(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RemoveLiquidity fails when shares are too small to exit (line 110-112)."""
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

def demo_remove_liquidity_too_small(alice_addr, foo_name, bar_name):
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
    
    # Add liquidity to get shares
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
    
    # Try to remove 1 share (too small to get any payout)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "shares": "1"
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
        "demo_remove_liquidity_too_small",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for shares too small: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "too small" in exception_msg
    ), f"Should mention 'too small', got: {exception_msg}"
