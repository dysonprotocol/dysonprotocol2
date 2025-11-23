"""
ExecScript message handler coverage tests.

Tests the ExecScript message handler which executes script functions with state changes.
Covers success path, script error bubble-up, validation errors, and attached messages.
All tests use stateless script query execution with _sudo calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_exec_script_success(chainnet):
    """Test ExecScript successfully executes a script function and commits state."""
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

def demo_exec_script_success(gov_addr):
    # Create a script with a function
    script_code = "def add_numbers(x, y):\\n    return x + y"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Execute the script using ExecScript (message handler, commits state)
    exec_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": gov_addr,
        "script_address": script_address,
        "function_name": "add_numbers",
        "args": json.dumps([5, 3]),
        "kwargs": "{}"
    })
    
    return {
        "exec_result": exec_result,
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
        "demo_exec_script_success",
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
        "exec_result" in demo_result
    ), f"Result missing 'exec_result' key. Keys: {list(demo_result.keys())}"

    exec_result = demo_result["exec_result"]
    assert isinstance(
        exec_result, dict
    ), f"Exec result should be dict, got {type(exec_result)}"
    assert (
        "results" in exec_result
    ), f"Exec result missing 'results' key. Keys: {list(exec_result.keys())}"
    assert (
        len(exec_result["results"]) > 0
    ), f"Exec result should have at least one result. Results: {exec_result['results']}"

    exec_response = exec_result["results"][0]
    assert (
        "result" in exec_response
    ), f"Exec response missing 'result' key. Keys: {list(exec_response.keys())}"

    # Result is a dict containing execution metadata
    result_value = exec_response["result"]
    assert isinstance(
        result_value, dict
    ), f"Result should be dict, got {type(result_value)}"
    assert (
        "result" in result_value
    ), f"Result dict missing 'result' key. Keys: {list(result_value.keys())}"

    # Extract nested result (already parsed)
    function_result = result_value["result"]

    # Result should be the function return value (8 for add_numbers(5, 3))
    assert (
        function_result == 8
    ), f"Expected add_numbers(5, 3) = 8, got {function_result}"


def test_exec_script_missing_function(chainnet):
    """Test ExecScript fails when calling a non-existent function."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import json
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_exec_script_missing_function(gov_addr):
    # Create a script with a different function
    script_code = "def other_function():\\n    return 'test'"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Try to execute a non-existent function
    # Errors will bubble up naturally
    exec_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": gov_addr,
        "script_address": script_address,
        "function_name": "nonexistent_function",
        "args": "[]",
        "kwargs": "{}"
    })
    return {"exec_result": exec_result}
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
        "demo_exec_script_missing_function",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # ExecScript with missing function should fail and bubble up error
    assert (
        query_result.get("exception") is not None
    ), f"Expected error for missing function, but got: {json.dumps(query_result, indent=2)}"

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
        "function" in error_msg_lower
    ), f"Expected error about missing function, got: {error_msg}"


def test_exec_script_runtime_error(chainnet):
    """Test ExecScript bubbles up script runtime errors."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import json
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_exec_script_runtime_error(gov_addr):
    # Create a script that raises an error
    script_code = "def error_function():\\n    raise Exception('Test error')"
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Try to execute the function that raises an error
    # Errors will bubble up naturally
    exec_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": gov_addr,
        "script_address": script_address,
        "function_name": "error_function",
        "args": "[]",
        "kwargs": "{}"
    })
    return {"exec_result": exec_result}
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
        "demo_exec_script_runtime_error",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # ExecScript with runtime error should fail and bubble up error
    assert (
        query_result.get("exception") is not None
    ), f"Expected error for runtime exception, but got: {json.dumps(query_result, indent=2)}"

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
        "test error" in error_msg_lower
    ), f"Expected error about 'Test error', got: {error_msg}"


def test_exec_script_missing_script_address(chainnet):
    """Test ExecScript handles missing script address validation error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Test validation error by calling ExecScript directly without script address or name
    # Note: ExecScript CLI uses --from for executor (signer), not --executor-address
    # We'll test via _sudo instead to validate the message handler directly
    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_exec_script_missing_address(gov_addr):
    # Try to execute without script_address or script_name
    exec_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": gov_addr,
        "function_name": "test",
        "args": "[]",
        "kwargs": "{}"
    })
    return {"exec_result": exec_result}
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
        "demo_exec_script_missing_address",
        "--kwargs",
        json.dumps({"gov_addr": gov_addr}),
        "--extra-code",
        extra_code,
    )

    # ExecScript with missing script_address/script_name should fail
    assert (
        query_result.get("exception") is not None
    ), f"Expected error for missing script address, but got: {json.dumps(query_result, indent=2)}"

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
        "script_address" in error_msg_lower
    ), f"Expected error about script_address, got: {error_msg}"


def test_exec_script_create_empty_script(chainnet):
    """Test ExecScript creates an empty script if script doesn't exist."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate a valid but non-existent script address
    address_result = dysond(
        "q", "auth", "address-bytes-to-string", "0x123456", "-o", "json"
    )
    new_script_address = address_result["address_string"]

    extra_code = """
import json
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_exec_script_create_empty(gov_addr, script_addr):
    # Execute script at non-existent address (should create empty script)
    # ExecScript creates empty script if address doesn't exist
    exec_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": gov_addr,
        "script_address": script_addr,
        "function_name": "",
        "args": "[]",
        "kwargs": "{}"
    })
    
    # Verify script now exists
    script_info = _query({
        "@type": "/dysonprotocol.script.v1.QueryScriptInfoRequest",
        "address": script_addr
    })
    
    return {
        "exec_result": exec_result,
        "script_info": script_info
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
        "demo_exec_script_create_empty",
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

    # Script should now exist (created by ExecScript)
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


def test_exec_script_script_name_resolution(chainnet):
    """Test ExecScript resolves script_name to address and executes script."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded addresses for stateless testing
    script_owner_addr = "dys216vwht46aw58efaxx"

    extra_code = f"""
import json
import re
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {{"denom": m.group(2), "amount": m.group(1)}}

def _register_name(name, destination, valuation="10udys"):
    owner = get_executor_address()
    salt = "salt-" + name
    hexhash = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    }})["hex_hash"]

    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    }})

    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    }})

    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": destination,
    }})

    return name

def demo_exec_script_name_resolution(gov_addr, script_owner_addr):
    # Register name and set destination
    script_name = _register_name("test-script-name.dys", script_owner_addr)

    # Update/create script at script_owner_addr (where script_name resolves to)
    script_code = "def multiply(x, y):\\n    return x * y"
    
    # Update script at script_owner_addr (creates if doesn't exist)
    update_result = _sudo({{
        "@type": "/dysonprotocol.script.v1.MsgUpdateScript",
        "address": script_owner_addr,
        "code": script_code
    }})
    
    # Execute using script_name instead of script_address
    exec_result = _sudo({{
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": gov_addr,
        "script_name": script_name,
        "function_name": "multiply",
        "args": json.dumps([6, 7]),
        "kwargs": "{{}}"
    }})
    
    return {{
        "exec_result": exec_result,
        "script_address": script_owner_addr
    }}
"""

    kwargs = json.dumps(
        {
            "gov_addr": gov_addr,
            "script_owner_addr": script_owner_addr,
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
        "demo_exec_script_name_resolution",
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
        "exec_result" in demo_result
    ), f"Result missing 'exec_result' key. Keys: {list(demo_result.keys())}"

    exec_result = demo_result["exec_result"]
    assert isinstance(
        exec_result, dict
    ), f"Exec result should be dict, got {type(exec_result)}"
    assert (
        "results" in exec_result
    ), f"Exec result missing 'results' key. Keys: {list(exec_result.keys())}"
    assert (
        len(exec_result["results"]) > 0
    ), f"Exec result should have at least one result. Results: {exec_result['results']}"

    exec_response = exec_result["results"][0]
    assert (
        "result" in exec_response
    ), f"Exec response missing 'result' key. Keys: {list(exec_response.keys())}"

    result_value = exec_response["result"]
    assert isinstance(
        result_value, dict
    ), f"Result should be dict, got {type(result_value)}"
    assert (
        "result" in result_value
    ), f"Result dict missing 'result' key. Keys: {list(result_value.keys())}"

    function_result = result_value["result"]
    assert function_result == 42, f"Expected multiply(6, 7) = 42, got {function_result}"

    # Verify script address matches script_owner_addr
    assert (
        demo_result["script_address"] == script_owner_addr
    ), f"Script address mismatch. Expected: {script_owner_addr}, Got: {demo_result['script_address']}"


def test_exec_script_address_name_mismatch(chainnet):
    """Test ExecScript fails when script_address and script_name don't match."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded addresses
    script_owner_addr = "dys216vwht46aw58efaxx"
    different_address = "dys216vwmdkmdkcsz2qrh"

    extra_code = f"""
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {{"denom": m.group(2), "amount": m.group(1)}}

def _register_name(name, destination, valuation="10udys"):
    owner = get_executor_address()
    salt = "salt-" + name
    hexhash = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    }})["hex_hash"]

    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    }})

    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    }})

    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": destination,
    }})

    return name

def demo_exec_script_mismatch(gov_addr, script_owner_addr, different_addr):
    # Register name and set destination so name resolves to script_owner_addr
    script_name = _register_name("test-script-mismatch.dys", script_owner_addr)

    # Try to execute with mismatched script_address and script_name
    exec_result = _sudo({{
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": gov_addr,
        "script_address": different_addr,
        "script_name": script_name,
        "function_name": "test",
        "args": "[]",
        "kwargs": "{{}}"
    }})
    return {{"exec_result": exec_result}}
"""

    kwargs = json.dumps(
        {
            "gov_addr": gov_addr,
            "script_owner_addr": script_owner_addr,
            "different_addr": different_address,
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
        "demo_exec_script_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # ExecScript with mismatched address/name should fail
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
    assert isinstance(
        error_msg, str
    ), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert (
        "match" in error_msg_lower
    ), f"Expected error about address/name mismatch, got: {error_msg}"


def test_exec_script_attached_messages(chainnet):
    """Test ExecScript executes attached messages before script function."""
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

def demo_exec_script_attached_messages(gov_addr):
    # Create a script that reads from storage
    script_code = '''
from dys import get_attached_messages
import json

def get_storage_value():
    attached = get_attached_messages()
    # Attached messages should have executed and set storage
    from dys import _query
    result = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
        "owner": "''' + gov_addr + '''",
        "index": "test_key"
    })
    return json.loads(result["entry"]["data"]) if "entry" in result else None
'''
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    script_address = create_result["results"][0]["script_address"]
    
    # Execute with attached message that sets storage
    exec_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": gov_addr,
        "script_address": script_address,
        "function_name": "get_storage_value",
        "args": "[]",
        "kwargs": "{}",
        "attached_messages": [{
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": gov_addr,
            "index": "test_key",
            "data": json.dumps({"value": "attached_message_set_this"})
        }]
    })
    
    return {
        "exec_result": exec_result,
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
        "demo_exec_script_attached_messages",
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
        "exec_result" in demo_result
    ), f"Result missing 'exec_result' key. Keys: {list(demo_result.keys())}"

    exec_result = demo_result["exec_result"]
    assert isinstance(
        exec_result, dict
    ), f"Exec result should be dict, got {type(exec_result)}"
    assert (
        "results" in exec_result
    ), f"Exec result missing 'results' key. Keys: {list(exec_result.keys())}"
    assert (
        len(exec_result["results"]) > 0
    ), f"Exec result should have at least one result. Results: {exec_result['results']}"

    exec_response = exec_result["results"][0]
    assert (
        "result" in exec_response
    ), f"Exec response missing 'result' key. Keys: {list(exec_response.keys())}"

    result_value = exec_response["result"]
    assert isinstance(
        result_value, dict
    ), f"Result should be dict, got {type(result_value)}"
    assert (
        "result" in result_value
    ), f"Result dict missing 'result' key. Keys: {list(result_value.keys())}"

    function_result = result_value["result"]
    assert isinstance(
        function_result, dict
    ), f"Function result should be dict, got {type(function_result)}"
    assert (
        function_result.get("value") == "attached_message_set_this"
    ), f"Expected attached message to set storage value, got: {function_result}"
