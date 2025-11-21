"""
ScriptInfo query handler coverage tests.

Tests the ScriptInfo query endpoint which retrieves script information by address/name in multiple scenarios.
Covers existing script, script not found, and malformed address cases.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_script_info_existing_script(chainnet):
    """Test ScriptInfo query successfully returns information for an existing script."""
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

def demo_script_info_existing(gov_addr):
    # Create a script using MsgCreateNewScript which returns the script address
    script_code = "def hello():\\n    return 'Hello World'"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    # Extract script address from create result
    # MsgSudoResponse has a results array containing the message responses
    create_response = create_result["results"][0]
    script_addr = create_response["script_address"]
    
    # Query script info by address
    script_info_result = _query({
        "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
        "address": script_addr
    })
    
    return {
        "create_result": create_result,
        "script_addr": script_addr,
        "script_info": script_info_result
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
        "demo_script_info_existing",
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
        "script_info" in demo_result
    ), f"Result missing 'script_info' key. Keys: {list(demo_result.keys())}"

    script_info = demo_result["script_info"]
    assert isinstance(
        script_info, dict
    ), f"Script info should be dict, got {type(script_info)}"
    assert (
        "script" in script_info
    ), f"Script info missing 'script' key. Keys: {list(script_info.keys())}"

    script = script_info["script"]
    assert isinstance(script, dict), f"Script should be dict, got {type(script)}"
    assert (
        "address" in script
    ), f"Script missing 'address' key. Keys: {list(script.keys())}"
    assert (
        "version" in script
    ), f"Script missing 'version' key. Keys: {list(script.keys())}"
    assert "code" in script, f"Script missing 'code' key. Keys: {list(script.keys())}"
    assert (
        "update_height" in script
    ), f"Script missing 'update_height' key. Keys: {list(script.keys())}"

    assert (
        script["address"] == demo_result["script_addr"]
    ), f"Script address mismatch: expected {demo_result['script_addr']}, got {script['address']}"
    assert (
        script["version"] == "1"
    ), f"Script version mismatch: expected '1', got {script['version']}"


def test_script_info_not_found(chainnet):
    """Test ScriptInfo query returns NotFound error for non-existent script."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate a deterministic valid bech32 address that does not have a script
    bytes_to_addr_result = dysond(
        "query",
        "auth",
        "address-bytes-to-string",
        "0x123456",
        "-o",
        "json",
    )
    random_addr = bytes_to_addr_result.get("address_string")
    assert isinstance(
        random_addr, str
    ), f"Address string should be str. Got: {type(random_addr)}"
    assert (
        len(random_addr) > 0
    ), f"Failed to convert bytes to address: {bytes_to_addr_result}"

    extra_code = """
from dys import _query

def demo_script_info_not_found(random_addr):
    # Query script info for a valid bech32 address that doesn't have a script
    # Using address converted from manual bytes which doesn't map to any script
    # This should hit the NotFound path (lines 50-51) for non-existent script addresses
    try:
        script_info_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
            "address": random_addr
        })
        return {"error": "Should have failed", "result": script_info_result}
    except Exception as e:
        return {
            "error": str(e)
        }
"""

    kwargs = json.dumps({"random_addr": random_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_script_info_not_found",
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
        "error" in demo_result
    ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
    actual_error = demo_result["error"]
    assert isinstance(
        actual_error, str
    ), f"Error should be string, got {type(actual_error)}"
    assert (
        "code = NotFound" in actual_error
    ), f"Expected NotFound error code. Error: {actual_error}"
    assert (
        f"script with address {random_addr}" in actual_error
    ), f"Expected address {random_addr} in error. Error: {actual_error}"
    assert (
        "doesn\\'t exist" in actual_error
    ), f"Expected 'doesn\\'t exist' message. Error: {actual_error}"


def test_script_info_malformed_address(chainnet):
    """Test ScriptInfo query returns error for malformed address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_script_info_malformed():
    # Query script info with malformed address
    malformed_addr = "invalid_address_format"
    
    try:
        script_info_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
            "address": malformed_addr
        })
        return {"error": "Should have failed", "result": script_info_result}
    except Exception as e:
        error_str = str(e)
        return {
            "error": error_str,
            "expected_error": True
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
        "demo_script_info_malformed",
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
        "expected_error" in demo_result
    ), f"Result missing 'expected_error' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected_error"] is True
    ), f"Expected error for malformed address, but got: {json.dumps(demo_result, indent=2)}"


def test_script_info_empty_address(chainnet):
    """Test ScriptInfo query returns error for empty address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_script_info_empty():
    # Query script info with empty address
    try:
        script_info_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
            "address": ""
        })
        return {"error": "Should have failed", "result": script_info_result}
    except Exception as e:
        error_str = str(e)
        return {
            "error": error_str,
            "expected_empty_error": "empty" in error_str.lower()
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
        "demo_script_info_empty",
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
        "expected_empty_error" in demo_result
    ), f"Result missing 'expected_empty_error' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected_empty_error"] is True
    ), f"Expected error for empty address, but got: {json.dumps(demo_result, indent=2)}"
