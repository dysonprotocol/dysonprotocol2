"""
Run query handler coverage tests.

Tests the Run query endpoint which executes scripts in read-only mode.
Covers success path, missing function, script runtime panic, and validation errors.
All tests use stateless script query execution with _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_run_success(chainnet):
    """Test Run query successfully executes a script function."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import json
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_run_success(gov_addr):
    # Create a script using _sudo
    script_code = "def add_numbers(x, y):\\n    return x + y"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Execute the script using Run query (nested RunScript is supported)
    run_result = _query({
        "@type": "/dysonprotocol.script.v1.RunScript",
        "executor_address": gov_addr,
        "script_address": script_address,
        "function_name": "add_numbers",
        "args": json.dumps([5, 3])
    })
    
    return {
        "run_result": run_result
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
        "demo_run_success",
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
        "run_result" in demo_result
    ), f"Result missing 'run_result' key. Keys: {list(demo_result.keys())}"

    run_result = demo_result["run_result"]
    assert isinstance(
        run_result, dict
    ), f"Run result should be dict, got {type(run_result)}"

    # When RunScript is called via _query, _query wraps the ResponseRunScript in execution metadata
    # Structure: run_result = ResponseRunScript dict
    #           run_result["result"] = execution metadata dict (from _query wrapper)
    #           run_result["result"]["result"] = ResponseRunScript.Result string (function return value)
    assert (
        "@type" in run_result
    ), f"Run result missing '@type' key. Keys: {list(run_result.keys())}"
    assert (
        run_result["@type"] == "/dysonprotocol.script.v1.ResponseRunScript"
    ), f"Expected ResponseRunScript type, got: {run_result['@type']}"

    assert (
        "result" in run_result
    ), f"Run result missing 'result' key. Keys: {list(run_result.keys())}"

    result_metadata = run_result["result"]
    assert isinstance(
        result_metadata, dict
    ), f"Result metadata should be dict, got {type(result_metadata)}"
    assert (
        "result" in result_metadata
    ), f"Result metadata missing 'result' key. Keys: {list(result_metadata.keys())}"

    # The actual function result is in result_metadata["result"]
    actual_result = result_metadata["result"]
    # The result can be a string or int depending on how it's serialized
    result_value = (
        str(actual_result) if isinstance(actual_result, int) else actual_result
    )

    # The result should be "8" (5 + 3)
    assert (
        result_value == "8"
    ), f"Expected result '8', got '{result_value}' (type: {type(actual_result)}). Full result: {json.dumps(run_result, indent=2)}"


def test_run_missing_function(chainnet):
    """Test Run query handles missing function error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import json
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_run_missing_function(gov_addr):
    # Create a script without the function we'll try to call
    script_code = "def other_function():\\n    return 'test'"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Attempt to execute a non-existent function
    run_result = _query({
        "@type": "/dysonprotocol.script.v1.RunScript",
        "executor_address": gov_addr,
        "script_address": script_address,
        "function_name": "nonexistent_function",
        "args": json.dumps([])
    })
    
    return {
        "run_result": run_result
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
        "demo_run_missing_function",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # The query should fail because the function doesn't exist
    assert (
        query_result.get("exception") is not None
    ), f"Expected script execution to fail with missing function, but got: {json.dumps(query_result, indent=2)}"

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
    assert (
        len(error_msg) > 0
    ), f"Error message should not be empty. Exception: {json.dumps(exception, indent=2)}"


def test_run_script_panic(chainnet):
    """Test Run query handles script runtime panic (bubble-up)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import json
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_run_panic(gov_addr):
    # Create a script that panics
    script_code = "def panic_function():\\n    raise Exception('Test panic')"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Attempt to execute the panic function
    run_result = _query({
        "@type": "/dysonprotocol.script.v1.RunScript",
        "executor_address": gov_addr,
        "script_address": script_address,
        "function_name": "panic_function",
        "args": json.dumps([])
    })
    
    return {
        "run_result": run_result
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
        "demo_run_panic",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # The query should fail because the script panics
    assert (
        query_result.get("exception") is not None
    ), f"Expected script execution to fail with panic, but got: {json.dumps(query_result, indent=2)}"

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
    assert (
        len(error_msg) > 0
    ), f"Error message should not be empty. Exception: {json.dumps(exception, indent=2)}"


def test_run_missing_executor_address(chainnet):
    """Test Run query handles missing executor address validation error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Test validation error by calling Run query directly without executor address
    # This tests the validation in query_run.go line 37-39
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--function-name",
        "test_function",
        "--args",
        json.dumps([]),
    )

    # CLI validation errors return strings, not dicts
    assert isinstance(
        query_result, str
    ), f"Expected string error response, got {type(query_result)}: {json.dumps(query_result, indent=2)}"

    error_str_lower = query_result.lower()
    assert (
        "executor address is required" in error_str_lower
    ), f"Expected 'executor address is required' in error message, got: {query_result}"


def test_run_missing_script_address(chainnet):
    """Test Run query handles missing script address validation error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Test validation error by calling Run query directly without script address or name
    # This tests the validation in query_run.go line 40-42
    query_result = dysond(
        "query",
        "script",
        "run",
        "--executor-address",
        gov_addr,
        "--function-name",
        "test_function",
        "--args",
        json.dumps([]),
    )

    # CLI validation errors return strings, not dicts
    assert isinstance(
        query_result, str
    ), f"Expected string error response, got {type(query_result)}: {json.dumps(query_result, indent=2)}"

    error_str_lower = query_result.lower()
    assert (
        "script_address" in error_str_lower
    ), f"Expected 'script_address' in error message, got: {query_result}"


def test_run_nil_request(chainnet):
    """Test Run query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_run_nil_request():
    # Attempt to query with None/null request
    # This tests the nil check in query_run.go line 33-35
    run_result = _query(None)
    return {
        "run_result": run_result
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
        "demo_run_nil_request",
        "--extra-code",
        extra_code,
    )

    # The query should fail when None is passed
    assert (
        query_result.get("exception") is not None
    ), f"Expected error for nil request, but got: {json.dumps(query_result, indent=2)}"

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
    assert (
        len(error_msg) > 0
    ), f"Error message should not be empty. Exception: {json.dumps(exception, indent=2)}"
