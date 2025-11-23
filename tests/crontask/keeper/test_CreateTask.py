"""
CreateTask message handler coverage tests.

Tests the CreateTask message handler which creates new scheduled tasks.
Covers success path, timestamp parsing, expiry validation, gas limits, and message validation.
All tests use stateless script query execution with _sudo calls.
"""

import json
from deep_parse import deep_parse


def test_create_task_success(chainnet):
    """Test CreateTask successfully creates a task with valid parameters."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import time
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_task_success(gov_addr):
    # Create a task with valid parameters
    current_time = int(time.time())
    scheduled_time = current_time + 60  # 1 minute from now
    expiry_time = current_time + 3600   # 1 hour from now

    create_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": gov_addr,
        "scheduled_timestamp": str(scheduled_time),
        "expiry_timestamp": str(expiry_time),
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"},
        "msgs": [{
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": gov_addr,
            "to_address": gov_addr,
            "amount": [{"denom": "udys", "amount": "1"}]
        }]
    }

    # Execute the message handler via sudo
    create_result = _sudo(create_task_msg)

    # Query the task to verify it was created
    task_id = create_result["results"][0]["task_id"]
    task_info = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTaskByIDRequest",
        "task_id": task_id
    })

    return {
        "create_result": create_result,
        "task_id": task_id,
        "task_info": task_info
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
        "demo_create_task_success",
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
        "create_result" in demo_result
    ), f"Result missing 'create_result' key. Keys: {list(demo_result.keys())}"
    assert (
        "task_id" in demo_result
    ), f"Result missing 'task_id' key. Keys: {list(demo_result.keys())}"
    assert (
        "task_info" in demo_result
    ), f"Result missing 'task_info' key. Keys: {list(demo_result.keys())}"

    # Verify create result
    create_result = demo_result["create_result"]
    assert isinstance(create_result, dict), f"Create result should be dict, got {type(create_result)}"
    assert "results" in create_result, f"Create result missing 'results' key. Keys: {list(create_result.keys())}"
    assert len(create_result["results"]) == 1, f"Create result should have 1 result, got {len(create_result['results'])}"

    result_item = create_result["results"][0]
    assert result_item["@type"] == "/dysonprotocol.crontask.v1.MsgCreateTaskResponse", f"Expected MsgCreateTaskResponse, got {result_item['@type']}"
    assert "task_id" in result_item, f"Result missing task_id, keys: {list(result_item.keys())}"

    task_id = result_item["task_id"]
    assert isinstance(task_id, str), f"Task ID should be string, got {type(task_id)}"
    assert task_id.isdigit(), f"Task ID should be numeric string, got {task_id}"

    # Verify task info from query
    task_info = demo_result["task_info"]
    assert isinstance(task_info, dict), f"Task info should be dict, got {type(task_info)}"
    assert "task" in task_info, f"Task info missing 'task' key. Keys: {list(task_info.keys())}"

    task = task_info["task"]
    assert isinstance(task, dict), f"Task should be dict, got {type(task)}"
    assert task["task_id"] == task_id, f"Task ID mismatch: expected {task_id}, got {task['task_id']}"
    assert task["creator"] == gov_addr, f"Creator mismatch: expected {gov_addr}, got {task['creator']}"
    assert task["status"] == "SCHEDULED", f"Status should be SCHEDULED, got {task['status']}"
    assert task["task_gas_limit"] == "200000", f"Gas limit mismatch: expected 200000, got {task['task_gas_limit']}"
    assert task["task_gas_fee"]["denom"] == "udys", f"Gas fee denom mismatch"
    assert task["task_gas_fee"]["amount"] == "1", f"Gas fee amount mismatch"


def test_create_task_timestamp_parsing_duration(chainnet):
    """Test CreateTask correctly parses duration-based timestamps."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import time
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_task_duration_timestamp(gov_addr):
    # Create a task using duration offsets
    create_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": gov_addr,
        "scheduled_timestamp": "+2m",  # 2 minutes from now
        "expiry_timestamp": "+1h",    # 1 hour from scheduled time
        "task_gas_limit": 150000,
        "task_gas_fee": {"denom": "udys", "amount": "2"},
        "msgs": [{
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": gov_addr,
            "to_address": gov_addr,
            "amount": [{"denom": "udys", "amount": "1"}]
        }]
    }

    create_result = _sudo(create_task_msg)

    # Query the task
    task_id = create_result["results"][0]["task_id"]
    task_info = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTaskByIDRequest",
        "task_id": task_id
    })

    return {
        "create_result": create_result,
        "task_id": task_id,
        "task_info": task_info
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
        "demo_create_task_duration_timestamp",
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
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"

    # Verify task was created and timestamps were parsed correctly
    task_info = demo_result["task_info"]
    task = task_info["task"]
    assert task["status"] == "SCHEDULED", f"Task should be SCHEDULED, got {task['status']}"
    assert isinstance(int(task["scheduled_timestamp"]), int), f"Scheduled timestamp should be valid Unix timestamp"
    assert isinstance(int(task["expiry_timestamp"]), int), f"Expiry timestamp should be valid Unix timestamp"


def test_create_task_invalid_creator_address(chainnet):
    """Test CreateTask fails with invalid creator address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import time
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_task_invalid_creator():
    # Use invalid creator address
    current_time = int(time.time())
    create_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": "invalid_address",
        "scheduled_timestamp": str(current_time + 60),
        "expiry_timestamp": str(current_time + 3600),
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"},
        "msgs": [{
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": "invalid_address",
            "to_address": "invalid_address",
            "amount": [{"denom": "udys", "amount": "1"}]
        }]
    }

    # This should fail with invalid address error
    create_result = _sudo(create_task_msg)
    return {"create_result": create_result}
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
        "demo_create_task_invalid_creator",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with invalid creator address, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "invalid" in error_msg_lower, f"Error should mention invalid address, got: {error_msg}"


def test_create_task_past_scheduled_time(chainnet):
    """Test CreateTask fails when scheduled time is in the past."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import time
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_task_past_time(gov_addr):
    # Use past timestamp
    past_time = int(time.time()) - 3600  # 1 hour ago
    create_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": gov_addr,
        "scheduled_timestamp": str(past_time),
        "expiry_timestamp": str(past_time + 7200),
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"},
        "msgs": [{
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": gov_addr,
            "to_address": gov_addr,
            "amount": [{"denom": "udys", "amount": "1"}]
        }]
    }

    # This should fail with past time error
    create_result = _sudo(create_task_msg)
    return {"create_result": create_result}
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
        "demo_create_task_past_time",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with past scheduled time, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "time" in error_msg_lower, f"Error should mention time validation, got: {error_msg}"


def test_create_task_gas_limit_exceeded(chainnet):
    """Test CreateTask fails when gas limit exceeds block gas limit."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # First get the block gas limit from params
    params_result = dysond("query", "crontask", "params")
    block_gas_limit = int(params_result["params"]["block_gas_limit"])

    extra_code = f"""
import time
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def demo_create_task_gas_limit_exceeded(gov_addr):
    # Use gas limit that exceeds block gas limit
    current_time = int(time.time())
    excessive_gas_limit = {block_gas_limit} + 1000000  # Exceed block limit

    create_task_msg = {{
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": gov_addr,
        "scheduled_timestamp": str(current_time + 60),
        "expiry_timestamp": str(current_time + 3600),
        "task_gas_limit": excessive_gas_limit,
        "task_gas_fee": {{"denom": "udys", "amount": "1"}},
        "msgs": [{{
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": gov_addr,
            "to_address": gov_addr,
            "amount": [{{"denom": "udys", "amount": "1"}}]
        }}]
    }}

    # This should fail with gas limit exceeded error
    create_result = _sudo(create_task_msg)
    return {{"create_result": create_result}}
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
        "demo_create_task_gas_limit_exceeded",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with gas limit exceeded, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "gas" in error_msg_lower, f"Error should mention gas limit, got: {error_msg}"


def test_create_task_empty_messages(chainnet):
    """Test CreateTask fails when no messages are provided."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import time
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_task_empty_messages(gov_addr):
    # Create task with no messages
    current_time = int(time.time())
    create_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": gov_addr,
        "scheduled_timestamp": str(current_time + 60),
        "expiry_timestamp": str(current_time + 3600),
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"},
        "msgs": []  # Empty messages array
    }

    # This should fail with no messages error
    create_result = _sudo(create_task_msg)
    return {"create_result": create_result}
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
        "demo_create_task_empty_messages",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with empty messages, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "message" in error_msg_lower, f"Error should mention messages, got: {error_msg}"
