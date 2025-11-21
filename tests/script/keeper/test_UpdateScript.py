"""
UpdateScript message handler coverage tests.

Tests the UpdateScript message handler which updates script code at a given address.
Covers success path (update existing script, create new script), and validation errors.
All tests use stateless script query execution with _sudo calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_update_script_success(chainnet):
    """Test UpdateScript successfully updates an existing script and increments version."""
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

def demo_update_script_success(gov_addr):
    # First create a script
    script_code_v1 = "def hello():\\n    return 'Hello World'"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code_v1
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Get initial script info
    initial_info = _query({
        "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
        "address": script_address
    })
    initial_version = int(initial_info["script"]["version"])
    
    # Update the script
    script_code_v2 = "def hello():\\n    return 'Hello Updated'"
    update_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgUpdateScript",
        "address": script_address,
        "code": script_code_v2
    })
    
    # Get updated script info
    updated_info = _query({
        "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
        "address": script_address
    })
    updated_version = int(updated_info["script"]["version"])
    
    return {
        "script_address": script_address,
        "initial_version": initial_version,
        "update_result": update_result,
        "updated_version": updated_version,
        "updated_code": updated_info["script"]["code"]
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
        "demo_update_script_success",
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

    update_result = demo_result["update_result"]
    assert isinstance(
        update_result, dict
    ), f"Update result should be dict, got {type(update_result)}"
    assert (
        "results" in update_result
    ), f"Update result missing 'results' key. Keys: {list(update_result.keys())}"
    assert (
        len(update_result["results"]) > 0
    ), f"Update result should have at least one result. Results: {update_result['results']}"

    update_response = update_result["results"][0]
    assert (
        "version" in update_response
    ), f"Update response missing 'version' key. Keys: {list(update_response.keys())}"

    initial_version = demo_result["initial_version"]
    updated_version = demo_result["updated_version"]
    response_version = int(update_response["version"])

    # Version should increment by 1
    assert (
        updated_version == initial_version + 1
    ), f"Version should increment by 1. Initial: {initial_version}, Updated: {updated_version}"
    assert (
        response_version == updated_version
    ), f"Response version should match updated version. Response: {response_version}, Updated: {updated_version}"

    # Code should be updated
    updated_code = demo_result["updated_code"]
    assert isinstance(
        updated_code, str
    ), f"Updated code should be string, got {type(updated_code)}"
    assert (
        "Hello Updated" in updated_code
    ), f"Updated code should contain 'Hello Updated'. Code: {updated_code}"


def test_update_script_create_new(chainnet):
    """Test UpdateScript creates a new script if it doesn't exist."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate a valid but non-existent script address
    address_result = dysond(
        "q", "auth", "address-bytes-to-string", "0xabcdef", "-o", "json"
    )
    new_script_address = address_result["address_string"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_script_create_new(gov_addr, script_addr):
    # Verify script doesn't exist
    try:
        initial_info = _query({
            "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
            "address": script_addr
        })
        script_exists = True
    except:
        script_exists = False
    
    # Update script (should create new script)
    script_code = "def new_function():\\n    return 'New Script'"
    update_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgUpdateScript",
        "address": script_addr,
        "code": script_code
    })
    
    # Verify script now exists
    updated_info = _query({
        "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
        "address": script_addr
    })
    
    return {
        "script_exists_before": script_exists,
        "update_result": update_result,
        "script_info": updated_info
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "script_addr": new_script_address})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_script_create_new",
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

    update_result = demo_result["update_result"]
    assert isinstance(
        update_result, dict
    ), f"Update result should be dict, got {type(update_result)}"
    assert (
        "results" in update_result
    ), f"Update result missing 'results' key. Keys: {list(update_result.keys())}"
    assert (
        len(update_result["results"]) > 0
    ), f"Update result should have at least one result. Results: {update_result['results']}"

    update_response = update_result["results"][0]
    assert (
        "version" in update_response
    ), f"Update response missing 'version' key. Keys: {list(update_response.keys())}"

    # New script should have version 1
    response_version = int(update_response["version"])
    assert (
        response_version == 1
    ), f"New script should have version 1, got {response_version}"

    # Script should now exist
    script_info = demo_result["script_info"]
    assert isinstance(
        script_info, dict
    ), f"Script info should be dict, got {type(script_info)}"
    assert (
        "script" in script_info
    ), f"Script info missing 'script' key. Keys: {list(script_info.keys())}"
    script_data = script_info["script"]
    assert (
        script_data["address"] == new_script_address
    ), f"Script address mismatch. Expected: {new_script_address}, Got: {script_data['address']}"


def test_update_script_invalid_format(chainnet):
    """Test UpdateScript fails with invalid Python code that cannot be formatted."""
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

def demo_update_script_invalid_format(gov_addr):
    # Create a script first
    script_code_v1 = "def hello():\\n    return 'Hello'"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code_v1
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Try to update with invalid Python code (syntax error)
    invalid_code = "def invalid_syntax(\\n    return 'missing closing paren'"
    try:
        update_result = _sudo({
            "@type": "/dysonprotocol.script.v1.MsgUpdateScript",
            "address": script_address,
            "code": invalid_code
        })
        return {"update_result": update_result, "error": None}
    except Exception as e:
        return {"error": str(e)}
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
        "demo_update_script_invalid_format",
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
    ), f"Expected error for invalid code format, got: {json.dumps(demo_result, indent=2)}"
    assert (
        demo_result["error"] is not None
    ), f"Expected error, got None. Result: {json.dumps(demo_result, indent=2)}"

    error_str = str(demo_result["error"]).lower()
    # Check for format error specifically (most specific)
    assert (
        "format" in error_str
    ), f"Expected error about formatting, got: {demo_result['error']}"
