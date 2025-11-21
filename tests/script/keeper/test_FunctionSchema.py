"""
FunctionSchema query handler coverage tests.

Tests the FunctionSchema query endpoint which extracts JSON schemas for all public functions in a script.
Covers success path (schema present), missing script (empty schema), and validation errors.
All tests use stateless script query execution with _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_function_schema_success(chainnet):
    """Test FunctionSchema query successfully returns function schemas for a script with functions."""
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

def demo_function_schema(gov_addr):
    # Create a script with multiple functions
    script_code = '''
def add_numbers(x, y):
    return x + y

def greet(name="World"):
    return f"Hello {name}"

def process_data(data, multiplier=1):
    return {"result": data * multiplier}
'''
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Query function schema
    schema_result = _query({
        "@type": "/dysonprotocol.script.v1.QueryFunctionSchemaRequest",
        "executor_address": gov_addr,
        "script_address": script_address
    })
    
    return {
        "schema_result": schema_result,
        "script_address": script_address
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
        "demo_function_schema",
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
        "schema_result" in demo_result
    ), f"Result missing 'schema_result' key. Keys: {list(demo_result.keys())}"

    schema_result = demo_result["schema_result"]
    assert isinstance(
        schema_result, dict
    ), f"Schema result should be dict, got {type(schema_result)}"
    assert (
        "schema_json" in schema_result
    ), f"Schema result missing 'schema_json' key. Keys: {list(schema_result.keys())}"

    schema_data = schema_result["schema_json"]
    assert isinstance(
        schema_data, list
    ), f"Schema data should be list, got {type(schema_data)}"
    assert (
        len(schema_data) > 0
    ), f"Schema should contain at least one function. Schema: {json.dumps(schema_data, indent=2)}"
    
    # Schema is a list of function schema objects
    # Extract function names from the list
    function_names = [item.get("function_name") for item in schema_data if isinstance(item, dict) and "function_name" in item]
    
    # Verify expected functions are present
    assert (
        "add_numbers" in function_names
    ), f"Schema missing 'add_numbers' function. Functions: {function_names}"
    assert (
        "greet" in function_names
    ), f"Schema missing 'greet' function. Functions: {function_names}"
    assert (
        "process_data" in function_names
    ), f"Schema missing 'process_data' function. Functions: {function_names}"


def test_function_schema_missing_script(chainnet):
    """Test FunctionSchema query returns empty schema for non-existent script."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate a valid but non-existent script address
    address_result = dysond("q", "auth", "address-bytes-to-string", "0x123456", "-o", "json")
    non_existent_address = address_result["address_string"]

    extra_code = """
from dys import _query, get_executor_address

def demo_function_schema_missing(gov_addr, script_addr):
    # Query function schema for non-existent script
    schema_result = _query({
        "@type": "/dysonprotocol.script.v1.QueryFunctionSchemaRequest",
        "executor_address": gov_addr,
        "script_address": script_addr
    })
    
    return {
        "schema_result": schema_result
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "script_addr": non_existent_address})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_function_schema_missing",
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
        "schema_result" in demo_result
    ), f"Result missing 'schema_result' key. Keys: {list(demo_result.keys())}"

    schema_result = demo_result["schema_result"]
    assert isinstance(
        schema_result, dict
    ), f"Schema result should be dict, got {type(schema_result)}"
    assert (
        "schema_json" in schema_result
    ), f"Schema result missing 'schema_json' key. Keys: {list(schema_result.keys())}"

    schema_data = schema_result["schema_json"]
    assert isinstance(
        schema_data, list
    ), f"Schema data should be list, got {type(schema_data)}"
    assert (
        len(schema_data) == 0
    ), f"Schema for non-existent script should be empty list, got: {json.dumps(schema_data, indent=2)}"


def test_function_schema_nil_request(chainnet):
    """Test FunctionSchema query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_function_schema_nil_request():
    # Attempt to query with None/null request
    schema_result = _query(None)
    return {
        "schema_result": schema_result
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
        "demo_function_schema_nil_request",
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
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    assert (
        len(error_msg) > 0
    ), f"Error message should not be empty. Exception: {json.dumps(exception, indent=2)}"


def test_function_schema_missing_executor_address(chainnet):
    """Test FunctionSchema query handles missing executor address validation error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Test validation error by calling FunctionSchema query directly without executor address
    query_result = dysond(
        "query",
        "script",
        "function-schema",
        "--script-address",
        gov_addr,
    )

    # CLI validation errors return strings, not dicts
    assert isinstance(
        query_result, str
    ), f"Expected string error response, got {type(query_result)}: {json.dumps(query_result, indent=2)}"
    
    error_str_lower = query_result.lower()
    assert (
        "executor address is required" in error_str_lower
    ), f"Expected 'executor address is required' in error message, got: {query_result}"


def test_function_schema_missing_script_address(chainnet):
    """Test FunctionSchema query handles missing script address validation error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Test validation error by calling FunctionSchema query directly without script address or name
    query_result = dysond(
        "query",
        "script",
        "function-schema",
        "--executor-address",
        gov_addr,
    )

    # CLI validation errors return strings, not dicts
    assert isinstance(
        query_result, str
    ), f"Expected string error response, got {type(query_result)}: {json.dumps(query_result, indent=2)}"
    
    error_str_lower = query_result.lower()
    assert (
        "script_address" in error_str_lower
    ), f"Expected 'script_address' in error message, got: {query_result}"


def test_function_schema_address_name_mismatch(chainnet):
    """Test FunctionSchema query handles script address and name mismatch."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate a valid but different script address
    address_result = dysond("q", "auth", "address-bytes-to-string", "0x789abc", "-o", "json")
    different_address = address_result["address_string"]

    extra_code = """
from dys import _query, get_executor_address

def demo_function_schema_mismatch(gov_addr, script_addr):
    # Query with mismatched script_address and script_name
    # Use a name that resolves to a different address
    schema_result = _query({
        "@type": "/dysonprotocol.script.v1.QueryFunctionSchemaRequest",
        "executor_address": gov_addr,
        "script_address": script_addr,
        "script_name": "nonexistent.dys"
    })
    
    return {
        "schema_result": schema_result
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "script_addr": different_address})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_function_schema_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # The query should fail due to address/name mismatch or name resolution failure
    assert (
        query_result.get("exception") is not None
    ), f"Expected error for address/name mismatch, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(
        exception, dict
    ), f"Exception should be dict, got {type(exception)}"
    assert (
        "msg" in exception
    ), f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert (
        "script_address" in error_msg_lower
    ), f"Expected error about script_address mismatch or resolution failure, got: {error_msg}"

