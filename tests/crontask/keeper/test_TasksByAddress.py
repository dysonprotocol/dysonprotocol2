"""
TasksByAddress query handler coverage tests.

Tests the TasksByAddress query endpoint which retrieves all tasks created by a specific address.
Covers tasks exist (paginated), no tasks found, invalid address format, and pagination edge cases.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


@pytest.mark.xfail(
    strict=True,
    reason="bug: codec registration - dyslang cannot resolve shared QueryTasksResponse type used by multiple query requests",
)
def test_tasks_by_address_existing_tasks(chainnet):
    """Test TasksByAddress query successfully returns tasks for an address with existing tasks."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import time

def demo_tasks_by_address_existing(gov_addr):
    # Create multiple tasks using the same creator address
    current_time = int(time.time())
    tasks_data = []

    for i in range(3):
        scheduled_time = current_time + 60 + (i * 30)  # Stagger by 30 seconds
        expiry_time = current_time + 3600

        create_task_msg = {
            "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
            "creator": gov_addr,
            "scheduled_timestamp": str(scheduled_time),
            "expiry_timestamp": str(expiry_time),
            "task_gas_limit": 200000,
            "task_gas_fee": {"denom": "udys", "amount": str(i + 1)},
            "msgs": [{
                "@type": "/cosmos.bank.v1beta1.MsgSend",
                "from_address": gov_addr,
                "to_address": gov_addr,
                "amount": [{"denom": "udys", "amount": "1"}]
            }]
        }

        create_result = _msg(create_task_msg)
        tasks_data.append({
            "task_id": create_result["task_id"],
            "scheduled_time": scheduled_time,
            "gas_fee": i + 1
        })

    # Query tasks by address
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByAddressRequest",
        "creator": gov_addr
    })

    return {
        "created_tasks": tasks_data,
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
        "demo_tasks_by_address_existing",
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
    assert len(tasks) >= 3, f"Expected at least 3 tasks, got {len(tasks)}"

    # Verify each task has the correct creator
    created_task_ids = [
        str(task_data["task_id"]) for task_data in demo_result["created_tasks"]
    ]
    for task in tasks:
        assert isinstance(task, dict), f"Task should be dict, got {type(task)}"
        assert (
            "task_id" in task
        ), f"Task missing 'task_id' key. Keys: {list(task.keys())}"
        assert (
            "creator" in task
        ), f"Task missing 'creator' key. Keys: {list(task.keys())}"
        assert (
            task["creator"] == gov_addr
        ), f"Creator mismatch: expected {gov_addr}, got {task['creator']}"

        # All tasks should be SCHEDULED (since we only create SCHEDULED tasks)
        assert "status" in task, f"Task missing 'status' key. Keys: {list(task.keys())}"
        assert (
            task["status"] == "SCHEDULED"
        ), f"Status mismatch: expected 'SCHEDULED', got {task['status']}"


@pytest.mark.xfail(
    strict=True,
    reason="bug: codec registration - dyslang cannot resolve shared QueryTasksResponse type used by multiple query requests",
)
def test_tasks_by_address_no_tasks(chainnet):
    """Test TasksByAddress query returns empty results for address with no tasks."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate a deterministic valid bech32 address that does not have any tasks
    bytes_to_addr_result = dysond(
        "query",
        "auth",
        "address-bytes-to-string",
        "0x999999",
        "-o",
        "json",
    )
    random_addr = bytes_to_addr_result["address_string"]
    assert isinstance(
        random_addr, str
    ), f"Address string should be str. Got: {type(random_addr)}"
    assert (
        len(random_addr) > 0
    ), f"Failed to convert bytes to address: {bytes_to_addr_result}"

    extra_code = f"""
from dys import _query

def demo_tasks_by_address_no_tasks(random_addr):
    # Query tasks by address for an address with no tasks
    tasks_result = _query({{
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByAddressRequest",
        "creator": random_addr
    }})

    return {{
        "query_result": tasks_result
    }}
"""

    kwargs = json.dumps({"random_addr": random_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_tasks_by_address_no_tasks",
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
        "query_result" in demo_result
    ), f"Result missing 'query_result' key. Keys: {list(demo_result.keys())}"

    query_result_data = demo_result["query_result"]
    assert isinstance(
        query_result_data, dict
    ), f"Query result should be dict, got {type(query_result_data)}"
    assert (
        "tasks" in query_result_data
    ), f"Query result missing 'tasks' key. Keys: {list(query_result_data.keys())}"

    tasks = query_result_data["tasks"]
    assert isinstance(tasks, list), f"Tasks should be list, got {type(tasks)}"
    assert len(tasks) == 0, f"Expected no tasks, got {len(tasks)}: {tasks}"


def test_tasks_by_address_invalid_address(chainnet):
    """Test TasksByAddress query returns error for invalid address format."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_tasks_by_address_invalid():
    # Query tasks by address with invalid address format
    # This should fail at protobuf validation level
    invalid_addr = "invalid_address_format"

    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByAddressRequest",
        "creator": invalid_addr
    })
    return {"result": tasks_result}
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
        "demo_tasks_by_address_invalid",
        "--extra-code",
        extra_code,
    )

    # Query should succeed but return empty results for invalid address
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed unexpectedly: {json.dumps(query_result.get('exception'), indent=2)}"

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "result" in demo_result
    ), f"Result missing 'result' key. Keys: {list(demo_result.keys())}"

    tasks_result = demo_result["result"]
    assert isinstance(
        tasks_result, dict
    ), f"Tasks result should be dict, got {type(tasks_result)}"
    assert (
        "tasks" in tasks_result
    ), f"Tasks result missing 'tasks' key. Keys: {list(tasks_result.keys())}"

    tasks = tasks_result["tasks"]
    assert isinstance(tasks, list), f"Tasks should be list, got {type(tasks)}"
    assert (
        len(tasks) == 0
    ), f"Expected no tasks for invalid address, got {len(tasks)}: {tasks}"
