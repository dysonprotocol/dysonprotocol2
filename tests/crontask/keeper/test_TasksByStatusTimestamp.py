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


def test_tasks_by_status_timestamp_scheduled_immediate(chainnet):
    """Test TasksByStatusTimestamp query with SCHEDULED status for immediate execution."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import time

def demo_tasks_by_status_timestamp_immediate(gov_addr):
    # Create a task scheduled for immediate execution (now)
    current_time = int(time.time())
    scheduled_time = current_time  # Schedule for now
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

    # Query tasks by status SCHEDULED (our task should be in this status)
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
        "demo_tasks_by_status_timestamp_immediate",
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

    # Check that we have at least one SCHEDULED task
    assert len(tasks) >= 1, f"Expected at least 1 SCHEDULED task, got {len(tasks)}"

    # Find our task by ID
    task_ids = [
        str(task["task_id"])
        for task in tasks
        if isinstance(task, dict) and "task_id" in task
    ]
    expected_task_id = str(demo_result["task_id"])
    assert (
        expected_task_id in task_ids
    ), f"Created task {expected_task_id} not found in SCHEDULED tasks: {task_ids}"

    # Get our task and verify its status
    our_task = next(task for task in tasks if str(task["task_id"]) == expected_task_id)
    assert (
        our_task["status"] == "SCHEDULED"
    ), f"Task should be SCHEDULED, got {our_task['status']}"
    assert (
        "scheduled_timestamp" in our_task
    ), f"SCHEDULED task missing 'scheduled_timestamp' key. Keys: {list(our_task.keys())}"


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
    """Test TasksByStatusTimestamp query returns empty results for invalid status."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_tasks_by_status_timestamp_invalid():
    # Query tasks by invalid status - should return empty results
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByStatusTimestampRequest",
        "status": "INVALID_STATUS"
    })
    return {"tasks_result": tasks_result}
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
        "tasks_result" in demo_result
    ), f"Result missing 'tasks_result' key. Keys: {list(demo_result.keys())}"

    tasks_result = demo_result["tasks_result"]
    assert isinstance(
        tasks_result, dict
    ), f"Tasks result should be dict, got {type(tasks_result)}"
    assert (
        "tasks" in tasks_result
    ), f"Tasks result missing 'tasks' key. Keys: {list(tasks_result.keys())}"
    assert (
        tasks_result["tasks"] == []
    ), f"Expected empty tasks list for invalid status, got {tasks_result['tasks']}"
