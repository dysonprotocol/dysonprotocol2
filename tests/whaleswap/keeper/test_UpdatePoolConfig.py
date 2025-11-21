"""
Test UpdatePoolConfig keeper function for whaleswap pools.

Tests the UpdatePoolConfig message handler which allows majority owners to update
pool configuration (fees, leverage params, interest rates, etc.).

Covers all validation paths and happy paths for UpdatePoolConfig function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_update_pool_config_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful pool config update (happy path)."""
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

def demo_update_pool_config_success(alice_addr, foo_name, bar_name):
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
    
    # Update pool config
    update_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "fee_rate": [
            {"denom": base, "amount": "0.004"},
            {"denom": quote, "amount": "0.004"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "2.0"},
            {"denom": quote, "amount": "2.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.3"},
            {"denom": quote, "amount": "1.3"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.06"},
            {"denom": quote, "amount": "0.06"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.75"},
            {"denom": quote, "amount": "0.75"}
        ],
        "bound_percent": [
            {"denom": base, "amount": "0.5"},
            {"denom": quote, "amount": "0.9"}
        ]
    })
    
    # Query pool to verify update
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "update_result": update_result["results"][0],
        "pool": pool_query["pool"]
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
        "demo_update_pool_config_success",
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
    pool = demo_result["pool"]
    base, quote = sorted([foo_name, bar_name])

    # Verify fee_rate updated
    fee_map = {fr["denom"]: fr["amount"] for fr in pool["fee_rate"]}
    assert (
        fee_map[base] == "0.004000000000000000"
    ), f"Fee rate for {base} should be 0.004, got {fee_map[base]}"
    assert (
        fee_map[quote] == "0.004000000000000000"
    ), f"Fee rate for {quote} should be 0.004, got {fee_map[quote]}"

    # Verify min_initial_collateral_ratio updated
    mcr_map = {
        mcr["denom"]: mcr["amount"]
        for mcr in pool["min_initial_collateral_ratio"]
    }
    assert (
        mcr_map[base] == "2.000000000000000000"
    ), f"Min CR for {base} should be 2.0, got {mcr_map[base]}"

    # Verify bound_percent updated
    bp_map = {bp["denom"]: bp["amount"] for bp in pool["bound_percent"]}
    assert (
        bp_map[base] == "0.500000000000000000"
    ), f"Bound percent for {base} should be 0.5, got {bp_map[base]}"


def test_update_pool_config_pool_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when pool does not exist (line 58-61)."""
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

def demo_update_pool_config_nonexistent(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": 99999,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ]
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
        "demo_update_pool_config_nonexistent",
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


def test_update_pool_config_invalid_signer(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when signer address is invalid (line 63-66)."""
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

def demo_update_pool_config_invalid_signer(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": "invalid_address",
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ]
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
        "demo_update_pool_config_invalid_signer",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid signer: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "signer" in exception_msg
    ), f"Should mention signer, got: {exception_msg}"
    assert (
        "address" in exception_msg
    ), f"Should mention address, got: {exception_msg}"


def test_update_pool_config_not_majority_owner(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when signer is not majority owner (line 67-69)."""
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

def demo_update_pool_config_not_owner(alice_addr, bob_addr, foo_name, bar_name):
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
    
    # Bob tries to update (not majority owner)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": bob_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "2.0"},
            {"denom": quote, "amount": "2.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.3"},
            {"denom": quote, "amount": "1.3"}
        ]
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
        "demo_update_pool_config_not_owner",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for non-majority owner: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "majority" in exception_msg
    ), f"Should mention majority, got: {exception_msg}"
    assert (
        "owner" in exception_msg
    ), f"Should mention owner, got: {exception_msg}"


def test_update_pool_config_invalid_fee_rate(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when fee_rate >= 1 (line 81-83)."""
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

def demo_update_pool_config_invalid_fee(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "fee_rate": [
            {"denom": base, "amount": "1.0"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ]
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
        "demo_update_pool_config_invalid_fee",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid fee_rate: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "fee_rate" in exception_msg
    ), f"Should mention fee_rate, got: {exception_msg}"


def test_update_pool_config_invalid_min_cr(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when min_initial_collateral_ratio <= 1 (line 98-100)."""
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

def demo_update_pool_config_invalid_min_cr(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.0"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ]
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
        "demo_update_pool_config_invalid_min_cr",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid min_collateral_ratio: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "min" in exception_msg
    ), f"Should mention min, got: {exception_msg}"
    assert (
        "collateral" in exception_msg
    ), f"Should mention collateral, got: {exception_msg}"


def test_update_pool_config_invalid_liquidation_threshold(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when liquidation_threshold <= 1 (line 110-112)."""
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

def demo_update_pool_config_invalid_liq(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "0.9"},
            {"denom": quote, "amount": "1.2"}
        ]
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
        "demo_update_pool_config_invalid_liq",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid liquidation_threshold: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "liquidation_threshold" in exception_msg
    ), f"Should mention liquidation_threshold, got: {exception_msg}"


def test_update_pool_config_invalid_interest_rate(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when interest_rate < 0 (line 121-123)."""
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

def demo_update_pool_config_invalid_interest(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "-0.01"},
            {"denom": quote, "amount": "0.05"}
        ]
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
        "demo_update_pool_config_invalid_interest",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid interest_rate: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "not positive" in exception_msg
    ), f"Should mention not positive, got: {exception_msg}"


def test_update_pool_config_invalid_max_borrow_percent(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when max_borrow_percent >= 1 (line 143-146)."""
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

def demo_update_pool_config_invalid_max_borrow(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "1.0"},
            {"denom": quote, "amount": "0.8"}
        ]
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
        "demo_update_pool_config_invalid_max_borrow",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid max_borrow_percent: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "max_borrow_percent" in exception_msg
    ), f"Should mention max_borrow_percent, got: {exception_msg}"


def test_update_pool_config_invalid_bound_percent(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when bound_percent > 1 (line 164-166)."""
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

def demo_update_pool_config_invalid_bound(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "bound_percent": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "0.9"}
        ]
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
        "demo_update_pool_config_invalid_bound",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid bound_percent: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "bound_percent" in exception_msg
    ), f"Should mention bound_percent, got: {exception_msg}"


def test_update_pool_config_min_cr_wrong_denoms(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when min_initial_collateral_ratio has wrong denoms (line 95-97)."""
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

def demo_update_pool_config_wrong_denoms_min_cr(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": "udys", "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ]
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
        "demo_update_pool_config_wrong_denoms_min_cr",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for wrong denoms: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "min" in exception_msg
    ), f"Should mention min, got: {exception_msg}"
    assert (
        "collateral" in exception_msg
    ), f"Should mention collateral, got: {exception_msg}"


def test_update_pool_config_bound_percent_duplicate(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when bound_percent has duplicate denoms (line 160-162)."""
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

def demo_update_pool_config_duplicate_bound(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "bound_percent": [
            {"denom": base, "amount": "0.5"},
            {"denom": base, "amount": "0.9"}
        ]
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
        "demo_update_pool_config_duplicate_bound",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for duplicate bound_percent: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "duplicate" in exception_msg
    ), f"Should mention duplicate, got: {exception_msg}"
    assert (
        "bound_percent" in exception_msg
    ), f"Should mention bound_percent, got: {exception_msg}"



def test_update_pool_config_liquidation_threshold_wrong_denoms(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when liquidation_threshold has wrong denoms (line 107-109)."""
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

def demo_update_pool_config_liq_wrong_denoms(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": "udys", "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ]
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
        "demo_update_pool_config_liq_wrong_denoms",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for wrong denoms: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "liquidation_threshold" in exception_msg
    ), f"Should mention liquidation_threshold, got: {exception_msg}"


def test_update_pool_config_max_borrow_wrong_denoms(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when max_borrow_percent has wrong denoms (line 139-141)."""
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

def demo_update_pool_config_max_borrow_wrong_denoms(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": "udys", "amount": "0.75"},
            {"denom": quote, "amount": "0.75"}
        ]
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
        "demo_update_pool_config_max_borrow_wrong_denoms",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for wrong denoms: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "max_borrow_percent" in exception_msg
    ), f"Should mention max_borrow_percent, got: {exception_msg}"


def test_update_pool_config_liquidation_threshold_wrong_count(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdatePoolConfig fails when liquidation_threshold has wrong count (line 107-109)."""
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

def demo_update_pool_config_liq_wrong_count(alice_addr, foo_name, bar_name):
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
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"}
        ]
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
        "demo_update_pool_config_liq_wrong_count",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for wrong count: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "liquidation_threshold" in exception_msg
    ), f"Should mention liquidation_threshold, got: {exception_msg}"
