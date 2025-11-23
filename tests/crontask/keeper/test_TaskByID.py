"""
TaskByID query handler coverage tests.

Tests the TaskByID query endpoint which retrieves task information by ID in multiple scenarios.
Covers existing task, task not found, and invalid task ID cases.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
from deep_parse import deep_parse


def test_task_by_id_existing_task(chainnet):
    """Test TaskByID query successfully returns information for an existing task."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import time

def demo_task_by_id_existing(gov_addr):
    # Create a task using MsgCreateTask
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

    # Send the message directly (not through governance)
    create_result = _msg(create_task_msg)

    # Extract task ID from create result
    # MsgCreateTask returns MsgCreateTaskResponse with task_id
    task_id = create_result["task_id"]

    # Query task by ID
    task_info_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTaskByIDRequest",
        "task_id": task_id
    })

    return {
        "create_result": create_result,
        "task_id": task_id,
        "task_info": task_info_result
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
        "demo_task_by_id_existing",
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
        "task_info" in demo_result
    ), f"Result missing 'task_info' key. Keys: {list(demo_result.keys())}"

    task_info = demo_result["task_info"]
    assert isinstance(
        task_info, dict
    ), f"Task info should be dict, got {type(task_info)}"
    assert (
        "task" in task_info
    ), f"Task info missing 'task' key. Keys: {list(task_info.keys())}"

    task = task_info["task"]
    assert isinstance(task, dict), f"Task should be dict, got {type(task)}"
    assert "task_id" in task, f"Task missing 'task_id' key. Keys: {list(task.keys())}"
    assert "creator" in task, f"Task missing 'creator' key. Keys: {list(task.keys())}"
    assert "status" in task, f"Task missing 'status' key. Keys: {list(task.keys())}"
    assert "msgs" in task, f"Task missing 'msgs' key. Keys: {list(task.keys())}"

    # Verify the task ID matches what we created
    assert (
        task["task_id"] == demo_result["task_id"]
    ), f"Task ID mismatch: expected {demo_result['task_id']}, got {task['task_id']}"

    # Verify creator address
    assert (
        task["creator"] == gov_addr
    ), f"Creator mismatch: expected {gov_addr}, got {task['creator']}"

    # Verify status is SCHEDULED
    assert (
        task["status"] == "SCHEDULED"
    ), f"Status mismatch: expected 'SCHEDULED', got {task['status']}"


def test_task_by_id_not_found(chainnet):
    """Test TaskByID query returns NotFound error for non-existent task."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use a task ID that definitely doesn't exist (very high number)
    non_existent_task_id = 999999

    extra_code = f"""
from dys import _query

def demo_task_by_id_not_found():
    # Query task by ID for a non-existent task - should raise exception
    task_info_result = _query({{
        "@type": "/dysonprotocol.crontask.v1.QueryTaskByIDRequest",
        "task_id": {non_existent_task_id}
    }})
    return {{"success": True, "result": task_info_result}}
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
        "demo_task_by_id_not_found",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Expected script to fail for non-existent task, but it succeeded: {json.dumps(result, indent=2)}"

    exception = query_result.get("exception", {})
    assert (
        "DysQueryException" in exception.get("context", "")
    ), f"Expected DysQueryException, got: {json.dumps(exception, indent=2)}"

    error_msg = exception.get("msg", "")
    assert (
        "task with ID 999999 not found" in error_msg
    ), f"Expected NotFound error for task ID 999999, got: {error_msg}"


def test_task_by_id_invalid_id_format(chainnet):
    """Test TaskByID query returns error for invalid task ID format."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_task_by_id_invalid():
    # Query task by ID with invalid format (negative number)
    invalid_task_id = -1

    task_info_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTaskByIDRequest",
        "task_id": invalid_task_id
    })
    return {"error": "Should have failed", "result": task_info_result}
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
        "demo_task_by_id_invalid",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Expected script to fail for invalid task ID, but it succeeded: {json.dumps(result, indent=2)}"

    exception = query_result.get("exception", {})
    assert (
        "DysRuntimeError" in exception.get("class", "")
    ), f"Expected DysRuntimeError for invalid task ID, got: {json.dumps(exception, indent=2)}"

    error_msg = exception.get("msg", "")
    assert (
        "uint64" in error_msg
    ), f"Expected uint64 error for invalid task ID, got: {error_msg}"
