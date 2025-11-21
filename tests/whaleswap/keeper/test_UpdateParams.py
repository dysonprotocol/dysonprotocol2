"""
Test UpdateParams keeper function for whaleswap module.

Tests the UpdateParams message handler which allows the authority to update
module parameters. Authority-only operation.

Covers all validation paths and happy paths for UpdateParams function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_update_params_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful parameter update (happy path)."""
    dysond = chainnet[0]
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

def demo_update_params_success(gov_addr):
    # Get current params
    current_params_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"
    })
    
    current_params = current_params_query["params"]
    
    # Update params with new values
    new_params = {
        "pfand_per_offer": {
            "denom": "udys",
            "amount": "1000"
        },
        "valuation_fee_pct": "0.01",
        "valuation_period": "3600s",
        "bid_timeout": "10s",
        "minimum_bid_percent_increase": "0.05",
        "max_note_length": 256,
        "block_delay_before_close": 2,
        "block_delay_before_liquidation": 2
    }
    
    update_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": new_params
    })
    
    # Query params again to verify update
    updated_params_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"
    })
    
    return {
        "update_result": update_result["results"][0],
        "updated_params": updated_params_query["params"]
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_success",
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
    updated_params = demo_result["updated_params"]

    assert (
        updated_params["pfand_per_offer"]["amount"] == "1000"
    ), f"Expected pfand_per_offer amount 1000, got {updated_params['pfand_per_offer']['amount']}"
    assert (
        updated_params["valuation_fee_pct"] == "0.01"
    ), f"Expected valuation_fee_pct 0.01, got {updated_params['valuation_fee_pct']}"


def test_update_params_invalid_authority(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdateParams fails when authority doesn't match (line 35-37)."""
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

def demo_update_params_invalid_authority(alice_addr):
    new_params = {
        "pfand_per_offer": {
            "denom": "udys",
            "amount": "1000"
        },
        "valuation_fee_pct": "0.01",
        "valuation_period": "3600s",
        "bid_timeout": "10s",
        "minimum_bid_percent_increase": "0.05",
        "max_note_length": 256,
        "block_delay_before_close": 2,
        "block_delay_before_liquidation": 2
    }
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": alice_addr,
        "params": new_params
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
        "demo_update_params_invalid_authority",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid authority: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "authority" in exception_msg
    ), f"Should mention authority, got: {exception_msg}"


def test_update_params_invalid_pfand_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdateParams fails when pfand_per_offer has amount > 0 but empty denom (line 33-35 in params.go)."""
    dysond = chainnet[0]
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

def demo_update_params_invalid_pfand(gov_addr):
    new_params = {
        "pfand_per_offer": {
            "denom": "",
            "amount": "1000"
        },
        "valuation_fee_pct": "0.01",
        "valuation_period": "3600s",
        "bid_timeout": "10s",
        "minimum_bid_percent_increase": "0.05",
        "max_note_length": 256,
        "block_delay_before_close": 2,
        "block_delay_before_liquidation": 2
    }
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": new_params
    })
"""

    kwargs = json.dumps({"gov_addr": gov_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_pfand",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid pfand denom: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "pfand_per_offer" in exception_msg
    ), f"Should mention pfand_per_offer, got: {exception_msg}"
    assert (
        "denom" in exception_msg
    ), f"Should mention denom, got: {exception_msg}"


def test_update_params_invalid_valuation_period(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdateParams fails when valuation_period <= 0 (line 36-38 in params.go)."""
    dysond = chainnet[0]
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

def demo_update_params_invalid_valuation_period(gov_addr):
    new_params = {
        "pfand_per_offer": {
            "denom": "udys",
            "amount": "1000"
        },
        "valuation_fee_pct": "0.01",
        "valuation_period": "0s",
        "bid_timeout": "10s",
        "minimum_bid_percent_increase": "0.05",
        "max_note_length": 256,
        "block_delay_before_close": 2,
        "block_delay_before_liquidation": 2
    }
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": new_params
    })
"""

    kwargs = json.dumps({"gov_addr": gov_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_valuation_period",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid valuation_period: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "valuation_period" in exception_msg
    ), f"Should mention valuation_period, got: {exception_msg}"


def test_update_params_invalid_bid_timeout(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdateParams fails when bid_timeout <= 0 (line 39-41 in params.go)."""
    dysond = chainnet[0]
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

def demo_update_params_invalid_bid_timeout(gov_addr):
    new_params = {
        "pfand_per_offer": {
            "denom": "udys",
            "amount": "1000"
        },
        "valuation_fee_pct": "0.01",
        "valuation_period": "3600s",
        "bid_timeout": "0s",
        "minimum_bid_percent_increase": "0.05",
        "max_note_length": 256,
        "block_delay_before_close": 2,
        "block_delay_before_liquidation": 2
    }
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": new_params
    })
"""

    kwargs = json.dumps({"gov_addr": gov_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_bid_timeout",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid bid_timeout: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "bid_timeout" in exception_msg
    ), f"Should mention bid_timeout, got: {exception_msg}"


def test_update_params_invalid_valuation_fee_pct(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdateParams fails when valuation_fee_pct >= 1 (line 42-49 in params.go)."""
    dysond = chainnet[0]
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

def demo_update_params_invalid_valuation_fee(gov_addr):
    new_params = {
        "pfand_per_offer": {
            "denom": "udys",
            "amount": "1000"
        },
        "valuation_fee_pct": "1.0",
        "valuation_period": "3600s",
        "bid_timeout": "10s",
        "minimum_bid_percent_increase": "0.05",
        "max_note_length": 256,
        "block_delay_before_close": 2,
        "block_delay_before_liquidation": 2
    }
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": new_params
    })
"""

    kwargs = json.dumps({"gov_addr": gov_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_valuation_fee",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid valuation_fee_pct: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "valuation_fee_pct" in exception_msg
    ), f"Should mention valuation_fee_pct, got: {exception_msg}"


def test_update_params_invalid_minimum_bid_percent_increase(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test UpdateParams fails when minimum_bid_percent_increase >= 1 (line 51-58 in params.go)."""
    dysond = chainnet[0]
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

def demo_update_params_invalid_min_bid(gov_addr):
    new_params = {
        "pfand_per_offer": {
            "denom": "udys",
            "amount": "1000"
        },
        "valuation_fee_pct": "0.01",
        "valuation_period": "3600s",
        "bid_timeout": "10s",
        "minimum_bid_percent_increase": "1.0",
        "max_note_length": 256,
        "block_delay_before_close": 2,
        "block_delay_before_liquidation": 2
    }
    
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": new_params
    })
"""

    kwargs = json.dumps({"gov_addr": gov_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_min_bid",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for invalid minimum_bid_percent_increase: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "minimum_bid_percent_increase" in exception_msg
    ), f"Should mention minimum_bid_percent_increase, got: {exception_msg}"

