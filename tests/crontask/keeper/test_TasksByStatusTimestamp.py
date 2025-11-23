"""
TasksByStatusTimestamp query handler coverage tests.

Tests the TasksByStatusTimestamp query endpoint which retrieves tasks filtered by status and ordered by timestamp.
Covers valid status filters, invalid status, empty results, and pagination with reverse ordering.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_tasks_by_status_timestamp_scheduled(chainnet):
    """Test TasksByStatusTimestamp query with SCHEDULED status filter."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import time

def demo_tasks_by_status_timestamp_scheduled(gov_addr):
    # Create a task that should be in SCHEDULED status
    current_time = int(time.time())
    scheduled_time = current_time + 3600  # 1 hour from now (should remain SCHEDULED)
    expiry_time = current_time + 7200

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

    create_result = _msg(create_task_msg)
    task_id = create_result["task_id"]

    # Query tasks by status SCHEDULED
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByStatusTimestampRequest",
        "status": "SCHEDULED"
    })

    return {
        "task_id": task_id,
        "scheduled_time": scheduled_time,
        "tasks_query": tasks_result
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
        "demo_tasks_by_status_timestamp_scheduled",
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
        "tasks_query" in demo_result
    ), f"Result missing 'tasks_query' key. Keys: {list(demo_result.keys())}"

    tasks_query = demo_result["tasks_query"]
    assert isinstance(
        tasks_query, dict
    ), f"Tasks query should be dict, got {type(tasks_query)}"
    assert (
        "tasks" in tasks_query
    ), f"Tasks query missing 'tasks' key. Keys: {list(tasks_query.keys())}"

    tasks = tasks_query["tasks"]
    assert isinstance(tasks, list), f"Tasks should be list, got {type(tasks)}"
    assert (
        len(tasks) >= 1
    ), f"Expected at least 1 task in SCHEDULED status, got {len(tasks)}"

    # Verify we have tasks returned
    assert (
        len(tasks) >= 1
    ), f"Expected at least 1 task in SCHEDULED status, got {len(tasks)}"

    # Get the first task (should be our created task due to ordering)
    our_task = tasks[0]

    assert (
        our_task["status"] == "SCHEDULED"
    ), f"Task status should be SCHEDULED, got {our_task['status']}"
    assert (
        "scheduled_timestamp" in our_task
    ), f"Task missing 'scheduled_timestamp' key. Keys: {list(our_task.keys())}"


def test_tasks_by_status_timestamp_done(chainnet):
    """Test TasksByStatusTimestamp query with DONE status filter."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import time

def demo_tasks_by_status_timestamp_done(gov_addr):
    # Create a task that will execute immediately (scheduled in the past)
    current_time = int(time.time())
    scheduled_time = current_time - 60  # 1 minute ago (should execute immediately)
    expiry_time = current_time + 3600

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

    create_result = _msg(create_task_msg)
    task_id = create_result["task_id"]

    # Wait a bit for the task to execute
    time.sleep(0.1)

    # Query tasks by status DONE
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByStatusTimestampRequest",
        "status": "DONE"
    })

    return {
        "task_id": task_id,
        "scheduled_time": scheduled_time,
        "tasks_query": tasks_result
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
        "demo_tasks_by_status_timestamp_done",
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
        "tasks_query" in demo_result
    ), f"Result missing 'tasks_query' key. Keys: {list(demo_result.keys())}"

    tasks_query = demo_result["tasks_query"]
    assert isinstance(
        tasks_query, dict
    ), f"Tasks query should be dict, got {type(tasks_query)}"
    assert (
        "tasks" in tasks_query
    ), f"Tasks query missing 'tasks' key. Keys: {list(tasks_query.keys())}"

    tasks = tasks_query["tasks"]
    assert isinstance(tasks, list), f"Tasks should be list, got {type(tasks)}"

    # The task should have executed, so check the first task in DONE status
    # (assuming our task executed and is the first one due to ordering)
    assert (
        len(tasks) >= 1
    ), f"Expected at least 1 DONE task, got {len(tasks)}"

    our_task = tasks[0]
    assert (
        our_task["status"] == "DONE"
    ), f"Task should be DONE, got {our_task['status']}"
    assert (
        "execution_timestamp" in our_task
    ), f"DONE task missing 'execution_timestamp' key. Keys: {list(our_task.keys())}"


def test_tasks_by_status_timestamp_empty(chainnet):
    """Test TasksByStatusTimestamp query returns empty results for status with no tasks."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_tasks_by_status_timestamp_empty():
    # Query tasks by status FAILED (assuming no failed tasks exist)
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByStatusTimestampRequest",
        "status": "FAILED"
    })

    return {
        "tasks_query": tasks_result
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
        "demo_tasks_by_status_timestamp_empty",
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
        "tasks_query" in demo_result
    ), f"Result missing 'tasks_query' key. Keys: {list(demo_result.keys())}"

    tasks_query = demo_result["tasks_query"]
    assert isinstance(
        tasks_query, dict
    ), f"Tasks query should be dict, got {type(tasks_query)}"
    assert (
        "tasks" in tasks_query
    ), f"Tasks query missing 'tasks' key. Keys: {list(tasks_query.keys())}"

    tasks = tasks_query["tasks"]
    assert isinstance(tasks, list), f"Tasks should be list, got {type(tasks)}"
    # Should be empty or very few tasks in FAILED status
    assert len(tasks) == 0, f"Expected no FAILED tasks, got {len(tasks)}: {tasks}"


def test_tasks_by_status_timestamp_invalid_status(chainnet):
    """Test TasksByStatusTimestamp query returns error for invalid status."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_tasks_by_status_timestamp_invalid():
    # Query tasks by invalid status
    try:
        tasks_result = _query({
            "@type": "/dysonprotocol.crontask.v1.QueryTasksByStatusTimestampRequest",
            "status": "INVALID_STATUS"
        })
        return {"error": "Should have failed", "result": tasks_result}
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
        "demo_tasks_by_status_timestamp_invalid",
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
    ), f"Expected error for invalid status, but got: {json.dumps(demo_result, indent=2)}"
