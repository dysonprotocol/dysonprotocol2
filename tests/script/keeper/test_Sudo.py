"""
Sudo message handler coverage tests.

Tests the Sudo message handler which executes arbitrary messages with authority override.
Covers authority validation, message unpacking, atomic execution, and error handling.
All tests use stateless script query execution.
"""

import json
import pytest
from deep_parse import deep_parse


def test_sudo_success(chainnet):
    """Test Sudo successfully executes nested messages with valid gov authority."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def demo_sudo_success(gov_addr):
    # Execute Sudo with a nested UpdateParams message
    # This tests that Sudo can execute messages atomically
    sudo_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": gov_addr,
        "messages": [{
            "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
            "authority": gov_addr,
            "params": {}
        }]
    })
    
    # Query params to verify the nested message executed
    params = _query({
        "@type": "/dysonprotocol.script.v1.QueryParamsRequest"
    })
    
    return {
        "sudo_result": sudo_result,
        "params": params
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
        "demo_sudo_success",
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
        "sudo_result" in demo_result
    ), f"Result missing 'sudo_result' key. Keys: {list(demo_result.keys())}"
    assert (
        "params" in demo_result
    ), f"Result missing 'params' key. Keys: {list(demo_result.keys())}"

    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"Sudo result should be dict, got {type(sudo_result)}"
    assert (
        "@type" in sudo_result
    ), f"Sudo result missing '@type' key. Keys: {list(sudo_result.keys())}"
    assert (
        sudo_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"Expected MsgSudoResponse, got {sudo_result['@type']}"
    assert (
        "results" in sudo_result
    ), f"Sudo result missing 'results' key. Keys: {list(sudo_result.keys())}"

    results = sudo_result["results"]
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

    params = demo_result["params"]
    assert isinstance(params, dict), f"Params should be dict, got {type(params)}"
    assert (
        "params" in params
    ), f"Params missing 'params' key. Keys: {list(params.keys())}"


def test_sudo_invalid_authority(chainnet):
    """Test Sudo fails with invalid authority address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def demo_sudo_invalid_authority(gov_addr):
    # Use invalid authority address
    invalid_authority = "dys1invalidaddress123456789012345678901234567890"
    
    # This should fail with invalid authority error
    sudo_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": invalid_authority,
        "messages": [{
            "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
            "authority": gov_addr,
            "params": {}
        }]
    })
    
    return {
        "sudo_result": sudo_result
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
        "demo_sudo_invalid_authority",
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


def test_sudo_wrong_authority(chainnet):
    """Test Sudo fails when authority doesn't match gov module."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]
    wrong_addr = "dys216vwht46aw58efaxx"

    extra_code = """
from dys import _msg, get_executor_address

def demo_sudo_wrong_authority(gov_addr, wrong_addr):
    # Use wrong authority (valid address but not gov module)
    sudo_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": wrong_addr,
        "messages": [{
            "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
            "authority": gov_addr,
            "params": {}
        }]
    })
    
    return {
        "sudo_result": sudo_result
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
        "demo_sudo_wrong_authority",
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


def test_sudo_nested_message_error(chainnet):
    """Test Sudo fails when nested message returns error (atomic rollback)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def demo_sudo_nested_message_error(gov_addr):
    # Execute Sudo with a nested message that will fail
    # Use UpdateParams with wrong authority in nested message
    wrong_authority = "dys1wrong123456789012345678901234567890"
    
    sudo_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": gov_addr,
        "messages": [{
            "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
            "authority": wrong_authority,
            "params": {}
        }]
    })
    
    return {
        "sudo_result": sudo_result
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
        "demo_sudo_nested_message_error",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with nested message error, but got: {json.dumps(query_result, indent=2)}"

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
    # Error should mention that sudo message failed or invalid authority
    assert (
        "invalid" in error_msg_lower
    ), f"Error message should mention invalid, got: {error_msg}"


def test_sudo_multiple_messages(chainnet):
    """Test Sudo successfully executes multiple nested messages atomically."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def demo_sudo_multiple_messages(gov_addr):
    # Execute Sudo with multiple nested messages
    # Both should execute atomically
    sudo_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": gov_addr,
        "messages": [
            {
                "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
                "authority": gov_addr,
                "params": {}
            },
            {
                "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
                "authority": gov_addr,
                "params": {}
            }
        ]
    })
    
    return {
        "sudo_result": sudo_result
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
        "demo_sudo_multiple_messages",
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
        "sudo_result" in demo_result
    ), f"Result missing 'sudo_result' key. Keys: {list(demo_result.keys())}"

    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"Sudo result should be dict, got {type(sudo_result)}"
    assert (
        "results" in sudo_result
    ), f"Sudo result missing 'results' key. Keys: {list(sudo_result.keys())}"

    results = sudo_result["results"]
    assert isinstance(results, list), f"Results should be list, got {type(results)}"
    assert len(results) == 2, f"Results should have 2 items, got {len(results)}"

    for i, result_item in enumerate(results):
        assert isinstance(
            result_item, dict
        ), f"Result item {i} should be dict, got {type(result_item)}"
        assert (
            "@type" in result_item
        ), f"Result item {i} missing '@type' key. Keys: {list(result_item.keys())}"
        assert (
            result_item["@type"] == "/dysonprotocol.script.v1.MsgUpdateParamsResponse"
        ), f"Expected MsgUpdateParamsResponse for item {i}, got {result_item['@type']}"
