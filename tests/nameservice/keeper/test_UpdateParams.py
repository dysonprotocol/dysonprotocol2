"""
Test UpdateParams message handler for nameservice keeper.

Tests the UpdateParams message which allows authorized accounts (governance)
to update the nameservice module parameters.
"""

import json
import pytest

from deep_parse import deep_parse


def test_update_params_success(chainnet):
    """Test successful parameter update by authorized authority."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_success():
    # Update parameters with valid values
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),  # gov module address
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "3600s",  # 1 hour
            "max_bid_timeout_class": "2592000s",  # 30 days
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",  # 2 hours
            "max_valuation_period": "2592000s"  # 30 days
        }
    })

    return {
        "sudo_result": sudo_result
    }
"""

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
        "--extra-code",
        extra_code,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Validate sudo result
    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"sudo_result should be dict, got {type(sudo_result)}"
    assert (
        sudo_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo should return sudo response, got {sudo_result.get('@type')}"
    assert (
        "results" in sudo_result
    ), f"sudo should have results, got {list(sudo_result.keys())}"
    assert (
        len(sudo_result["results"]) == 1
    ), f"sudo should have one result, got {len(sudo_result['results'])}"
    assert (
        sudo_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgUpdateParamsResponse"
    ), f"sudo should return update params response, got {sudo_result['results'][0].get('@type')}"


def test_update_params_invalid_authority(chainnet):
    """Test parameter update with invalid authority."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    # Use a random address that's not the authority
    invalid_authority = "dyson1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_invalid_authority(invalid_authority):
    # Try to update parameters with invalid authority - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": invalid_authority,
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "3600s",
            "max_bid_timeout_class": "2592000s",
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",
            "max_valuation_period": "2592000s"
        }
    })

    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({"invalid_authority": invalid_authority})

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

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
    assert (
        "invalid authority" in exception["msg"].lower()
    ), f"error should mention invalid authority, got: {exception['msg']}"


def test_update_params_invalid_params_negative_mint_fee(chainnet):
    """Test parameter update with invalid parameters (negative mint fee)."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_invalid_params():
    # Try to update parameters with negative mint fee - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "-0.01",  # Invalid: negative fee
            "min_bid_timeout_class": "3600s",
            "max_bid_timeout_class": "2592000s",
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",
            "max_valuation_period": "2592000s"
        }
    })

    return {
        "sudo_result": sudo_result
    }
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_params",
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
    assert (
        "invalid parameters" in exception["msg"].lower()
    ), f"error should mention invalid parameters, got: {exception['msg']}"


def test_update_params_invalid_params_invalid_decimal(chainnet):
    """Test parameter update with invalid parameters (invalid decimal string)."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_invalid_decimal():
    # Try to update parameters with invalid decimal string - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "not_a_number",  # Invalid: not a decimal
            "min_bid_timeout_class": "3600s",
            "max_bid_timeout_class": "2592000s",
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",
            "max_valuation_period": "2592000s"
        }
    })

    return {
        "sudo_result": sudo_result
    }
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_decimal",
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
    assert (
        "invalid parameters" in exception["msg"].lower()
    ), f"error should mention invalid parameters, got: {exception['msg']}"


def test_update_params_invalid_params_bounds_violation(chainnet):
    """Test parameter update with invalid parameters (min > max bounds)."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_bounds_violation():
    # Try to update parameters with min > max bounds - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "2592000s",  # 30 days
            "max_bid_timeout_class": "3600s",     # 1 hour (min > max)
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",
            "max_valuation_period": "2592000s"
        }
    })

    return {
        "sudo_result": sudo_result
    }
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_bounds_violation",
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
    assert (
        "invalid parameters" in exception["msg"].lower()
    ), f"error should mention invalid parameters, got: {exception['msg']}"


def test_update_params_nil_request(chainnet):
    """Test parameter update with nil request."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_nil_request():
    # Try to call with nil message - should fail at framework level
    sudo_result = _sudo(None)

    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_nil_request",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
