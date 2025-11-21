"""
CreateNewScript message handler coverage tests.

Tests the CreateNewScript message handler which creates a new script with
deterministic address derived from creator address and code hash.
Covers success path, duplicate script detection, invalid code format, and validation errors.
All tests use stateless script query execution with _sudo calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_create_new_script_success(chainnet):
    """Test CreateNewScript successfully creates a new script with deterministic address."""
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

def demo_create_new_script_success(gov_addr):
    script_code = "def hello():\\n    return 'Hello World'"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    version = int(create_result["results"][0]["version"])
    
    # Query script info to verify it was created
    script_info = _query({
        "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
        "address": script_address
    })
    
    return {
        "script_address": script_address,
        "version": version,
        "script_info": script_info
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
        "demo_create_new_script_success",
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
        "script_address" in demo_result
    ), f"Result missing 'script_address' key. Keys: {list(demo_result.keys())}"
    assert (
        "version" in demo_result
    ), f"Result missing 'version' key. Keys: {list(demo_result.keys())}"
    assert (
        "script_info" in demo_result
    ), f"Result missing 'script_info' key. Keys: {list(demo_result.keys())}"

    script_address = demo_result["script_address"]
    assert isinstance(
        script_address, str
    ), f"Script address should be string, got {type(script_address)}"
    assert (
        len(script_address) > 0
    ), f"Script address should not be empty, got: {script_address}"

    version = demo_result["version"]
    assert version == 1, f"Version should be 1, got {version}"

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
        script["address"] == script_address
    ), f"Script address mismatch: expected {script_address}, got {script['address']}"
    assert (
        int(script["version"]) == version
    ), f"Script version mismatch: expected {version}, got {script['version']}"
    assert (
        "code" in script
    ), f"Script missing 'code' key. Keys: {list(script.keys())}"
    assert isinstance(
        script["code"], str
    ), f"Script code should be string, got {type(script['code'])}"
    assert (
        len(script["code"]) > 0
    ), f"Script code should not be empty, got: {script['code']}"


def test_create_new_script_duplicate(chainnet):
    """Test CreateNewScript fails when trying to create duplicate script (same creator + code)."""
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

def demo_create_new_script_duplicate(gov_addr):
    script_code = "def hello():\\n    return 'Hello World'"
    
    # Create script first time
    create_result1 = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result1["results"][0]["script_address"]
    
    # Try to create same script again (same creator + code)
    create_result2 = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    return {
        "script_address": script_address,
        "first_create": create_result1,
        "second_create": create_result2
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
        "demo_create_new_script_duplicate",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with duplicate error, but got: {json.dumps(query_result, indent=2)}"

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
        "already exists" in error_msg_lower
    ), f"Error message should mention 'already exists', got: {error_msg}"


def test_create_new_script_invalid_code(chainnet):
    """Test CreateNewScript fails with invalid Python code that cannot be formatted."""
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

def demo_create_new_script_invalid_code(gov_addr):
    # Invalid Python syntax - unclosed string
    invalid_code = "def hello():\\n    return 'Hello World"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": invalid_code
    })
    
    return {
        "create_result": create_result
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
        "demo_create_new_script_invalid_code",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with invalid code error, but got: {json.dumps(query_result, indent=2)}"

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
        "format" in error_msg_lower
    ), f"Error message should mention formatting error, got: {error_msg}"


def test_create_new_script_empty_code(chainnet):
    """Test CreateNewScript handles empty code string."""
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

def demo_create_new_script_empty_code(gov_addr):
    # Try to create script with empty code string
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": ""
    })
    
    return {
        "create_result": create_result
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
        "demo_create_new_script_empty_code",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    # Empty code should succeed (empty script is valid)
    assert (
        query_result.get("exception") is None
    ), f"Script execution should succeed with empty code, but got exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "create_result" in demo_result
    ), f"Result missing 'create_result' key. Keys: {list(demo_result.keys())}"
    
    create_result = demo_result["create_result"]
    assert isinstance(
        create_result, dict
    ), f"Create result should be dict, got {type(create_result)}"
    assert (
        "results" in create_result
    ), f"Create result missing 'results' key. Keys: {list(create_result.keys())}"
    
    results = create_result["results"]
    assert isinstance(
        results, list
    ), f"Results should be list, got {type(results)}"
    assert (
        len(results) == 1
    ), f"Results should have 1 item, got {len(results)}"
    
    result_item = results[0]
    assert isinstance(
        result_item, dict
    ), f"Result item should be dict, got {type(result_item)}"
    assert (
        "script_address" in result_item
    ), f"Result item missing 'script_address' key. Keys: {list(result_item.keys())}"
    assert (
        "version" in result_item
    ), f"Result item missing 'version' key. Keys: {list(result_item.keys())}"
    
    script_address = result_item["script_address"]
    assert isinstance(
        script_address, str
    ), f"Script address should be string, got {type(script_address)}"
    assert (
        len(script_address) > 0
    ), f"Script address should not be empty, got: {script_address}"
    
    version = int(result_item["version"])
    assert version == 1, f"Version should be 1, got {version}"


def test_create_new_script_invalid_creator_address(chainnet):
    """Test CreateNewScript fails with invalid creator address."""
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

def demo_create_new_script_invalid_creator_address(gov_addr):
    script_code = "def hello():\\n    return 'Hello World'"
    
    # Use invalid bech32 address
    invalid_address = "invalid_address_12345"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": invalid_address,
        "code": script_code
    })
    
    return {
        "create_result": create_result
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
        "demo_create_new_script_invalid_creator_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with invalid address error, but got: {json.dumps(query_result, indent=2)}"

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
        "address" in error_msg_lower
    ), f"Error message should mention address, got: {error_msg}"

