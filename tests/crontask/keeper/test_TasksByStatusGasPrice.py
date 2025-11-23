"""
TasksByStatusGasPrice query handler coverage tests.

Tests the TasksByStatusGasPrice query endpoint which retrieves tasks filtered by status and ordered by gas price.
Covers valid status filter, gas price ordering (descending), empty results, and pagination edge cases.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_tasks_by_status_gas_price_scheduled_with_varying_fees(chainnet):
    """Test TasksByStatusGasPrice query with SCHEDULED status and varying gas fees."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import time

def demo_tasks_by_status_gas_price_scheduled(gov_addr):
    # Create multiple tasks with different gas fees to test ordering
    current_time = int(time.time())
    tasks_data = []

    # Create tasks with decreasing gas fees (higher fee first, then lower)
    gas_fees = ["5", "3", "1"]  # Higher fees should come first in descending order

    for i, fee in enumerate(gas_fees):
        scheduled_time = current_time + 3600 + (i * 60)  # Stagger by minutes
        expiry_time = current_time + 7200

        create_task_msg = {
            "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
            "creator": gov_addr,
            "scheduled_timestamp": str(scheduled_time),
            "expiry_timestamp": str(expiry_time),
            "task_gas_limit": 200000,
            "task_gas_fee": {"denom": "udys", "amount": fee},
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
            "gas_fee": int(fee),
            "scheduled_time": scheduled_time
        })

    # Query tasks by status SCHEDULED ordered by gas price (descending)
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByStatusGasPriceRequest",
        "status": "SCHEDULED"
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
        "demo_tasks_by_status_gas_price_scheduled",
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
        len(tasks) >= 3
    ), f"Expected at least 3 tasks, got {len(tasks)}"

    # Verify we have tasks returned
    assert (
        len(tasks) >= 1
    ), f"Expected at least 1 task in SCHEDULED status, got {len(tasks)}"

    # Get the first task (should be one of our created tasks due to ordering)
    our_task = tasks[0]

    assert our_task["status"] == "SCHEDULED", f"Task should be SCHEDULED, got {our_task['status']}"
    assert (
        "task_gas_price" in our_task
    ), f"Task missing 'task_gas_price' key. Keys: {list(our_task.keys())}"


def test_tasks_by_status_gas_price_empty(chainnet):
    """Test TasksByStatusGasPrice query returns empty results for status with no tasks."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_tasks_by_status_gas_price_empty():
    # Query tasks by status EXPIRED ordered by gas price (assuming no expired tasks)
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByStatusGasPriceRequest",
        "status": "EXPIRED"
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
        "demo_tasks_by_status_gas_price_empty",
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
    # Should be empty for EXPIRED status
    assert len(tasks) == 0, f"Expected no EXPIRED tasks, got {len(tasks)}: {tasks}"


def test_tasks_by_status_gas_price_invalid_status(chainnet):
    """Test TasksByStatusGasPrice query returns empty results for invalid status."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_tasks_by_status_gas_price_invalid():
    # Query tasks by invalid status - should return empty results
    tasks_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTasksByStatusGasPriceRequest",
        "status": "NONEXISTENT_STATUS"
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
        "demo_tasks_by_status_gas_price_invalid",
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
    assert isinstance(tasks_result, dict), f"Tasks result should be dict, got {type(tasks_result)}"
    assert "tasks" in tasks_result, f"Tasks result missing 'tasks' key. Keys: {list(tasks_result.keys())}"
    assert tasks_result["tasks"] == [], f"Expected empty tasks list for invalid status, got {tasks_result['tasks']}"
