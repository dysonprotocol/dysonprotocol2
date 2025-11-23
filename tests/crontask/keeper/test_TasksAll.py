"""
TasksAll query handler coverage tests.

Tests the TasksAll query endpoint which retrieves all tasks ordered by ID.
Covers tasks exist (basic structure validation) and query response format.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_tasks_all_basic_structure(chainnet):
    """Test TasksAll query returns proper response structure.

    WHEN this test is fixed (codec bug resolved), it should:
    - Create a task via MsgCreateTask
    - Query all tasks via QueryAllTasksRequest
    - Verify response contains the created task
    - Validate task structure and pagination metadata
    """
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import time

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_tasks_all_basic(gov_addr):
    # Create a task
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
    task_id = create_result["task_id"]

    # Query all tasks
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksAllRequest"
    })

    return {
        "create_result": create_result,
        "task_id": task_id,
        "tasks_result": tasks_result
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
        "demo_tasks_all_basic",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    # This assertion will currently fail due to the codec bug
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

    tasks = tasks_result["tasks"]
    assert isinstance(tasks, list), f"Tasks should be list, got {type(tasks)}"
    assert len(tasks) >= 1, f"Expected at least 1 task, got {len(tasks)}"

    # Check that our created task is in the results
    task_ids = [
        str(task["task_id"])
        for task in tasks
        if isinstance(task, dict) and "task_id" in task
    ]
    expected_task_id = str(demo_result["task_id"])
    assert (
        expected_task_id in task_ids
    ), f"Created task {expected_task_id} not found in results: {task_ids}"

    # Verify task structure
    for task in tasks:
        assert isinstance(task, dict), f"Task should be dict, got {type(task)}"
        assert (
            "task_id" in task
        ), f"Task missing 'task_id' key. Keys: {list(task.keys())}"
        assert (
            "creator" in task
        ), f"Task missing 'creator' key. Keys: {list(task.keys())}"
        assert "status" in task, f"Task missing 'status' key. Keys: {list(task.keys())}"
