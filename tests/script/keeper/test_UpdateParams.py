"""
UpdateParams message handler coverage tests.

Tests the UpdateParams message handler which updates module parameters via governance.
Covers authority validation, parameter validation, and state updates.
All tests use stateless script query execution with _sudo calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_update_params_success(chainnet):
    """Test UpdateParams successfully updates parameters with valid authority."""
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
    current_params = _query({
        "@type": "/dysonprotocol.script.v1.QueryParamsRequest"
    })
    
    # Update params (currently empty params, but we can still test the update)
    update_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {}
    })
    
    # Query params again to verify update succeeded
    updated_params = _query({
        "@type": "/dysonprotocol.script.v1.QueryParamsRequest"
    })
    
    return {
        "update_result": update_result,
        "current_params": current_params,
        "updated_params": updated_params
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
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "update_result" in demo_result
    ), f"Result missing 'update_result' key. Keys: {list(demo_result.keys())}"
    assert (
        "current_params" in demo_result
    ), f"Result missing 'current_params' key. Keys: {list(demo_result.keys())}"
    assert (
        "updated_params" in demo_result
    ), f"Result missing 'updated_params' key. Keys: {list(demo_result.keys())}"

    update_result = demo_result["update_result"]
    assert isinstance(
        update_result, dict
    ), f"Update result should be dict, got {type(update_result)}"
    assert (
        "results" in update_result
    ), f"Update result missing 'results' key. Keys: {list(update_result.keys())}"

    results = update_result["results"]
    assert isinstance(results, list), f"Results should be list, got {type(results)}"
    assert len(results) == 1, f"Results should have 1 item, got {len(results)}"

    result_item = results[0]
    assert isinstance(
        result_item, dict
    ), f"Result item should be dict, got {type(result_item)}"
    assert (
        "@type" in result_item
    ), f"Result item missing '@type' key. Keys: {list(result_item.keys())}"
    assert (
        result_item["@type"] == "/dysonprotocol.script.v1.MsgUpdateParamsResponse"
    ), f"Expected MsgUpdateParamsResponse, got {result_item['@type']}"

    current_params = demo_result["current_params"]
    updated_params = demo_result["updated_params"]
    assert isinstance(
        current_params, dict
    ), f"Current params should be dict, got {type(current_params)}"
    assert isinstance(
        updated_params, dict
    ), f"Updated params should be dict, got {type(updated_params)}"
    assert (
        "params" in current_params
    ), f"Current params missing 'params' key. Keys: {list(current_params.keys())}"
    assert (
        "params" in updated_params
    ), f"Updated params missing 'params' key. Keys: {list(updated_params.keys())}"


def test_update_params_invalid_authority(chainnet):
    """Test UpdateParams fails with invalid authority address."""
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

def demo_update_params_invalid_authority(gov_addr):
    # Use invalid authority address (not gov module)
    invalid_authority = "dys1invalidaddress123456789012345678901234567890"
    
    # This should fail with invalid authority error
    update_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
        "authority": invalid_authority,
        "params": {}
    })
    
    return {
        "update_result": update_result
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
        "demo_update_params_invalid_authority",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with invalid authority, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(
        exception, dict
    ), f"Exception should be dict, got {type(exception)}"
    assert (
        "msg" in exception
    ), f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(
        error_msg, str
    ), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert (
        "invalid" in error_msg_lower
    ), f"Error message should mention invalid, got: {error_msg}"
    assert (
        "authority" in error_msg_lower
    ), f"Error message should mention authority, got: {error_msg}"


def test_update_params_wrong_authority(chainnet):
    """Test UpdateParams fails when authority doesn't match gov module."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]
    wrong_addr = "dys216vwht46aw58efaxx"

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_wrong_authority(gov_addr, wrong_addr):
    # Use wrong authority (valid address but not gov module)
    update_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
        "authority": wrong_addr,
        "params": {}
    })
    
    return {
        "update_result": update_result
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "wrong_addr": wrong_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_wrong_authority",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with wrong authority, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(
        exception, dict
    ), f"Exception should be dict, got {type(exception)}"
    assert (
        "msg" in exception
    ), f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(
        error_msg, str
    ), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert (
        "invalid" in error_msg_lower
    ), f"Error message should mention invalid, got: {error_msg}"
    assert (
        "authority" in error_msg_lower
    ), f"Error message should mention authority, got: {error_msg}"
