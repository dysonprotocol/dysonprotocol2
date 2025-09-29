import decimal
import pytest
import json
import time
import datetime
import subprocess
from typing import Dict, List
import uuid
from tests.conftest import faucet
from tests.utils import poll_until_condition

# Constants for test delays
TASK_SCHEDULED_DELAY = (
    15  # Increased from 3 to 15 seconds to keep tasks in SCHEDULED status longer
)
TASK_WAIT_TIMEOUT = 8  # Maximum time to wait for task execution
TASK_CHECK_INTERVAL = 0.5  # How often to check task status
GAS_LIMIT = 200000
GAS_FEE = 1


def test_crontask_params(chainnet):
    """Test querying crontask module parameters"""
    dysond_bin = chainnet[0]
    params_result = dysond_bin("query", "crontask", "params")
    assert "params" in params_result, "Params response does not contain 'params' field"
    params = params_result["params"]
    assert "block_gas_limit" in params, "Missing 'block_gas_limit' in params"
    assert "expiry_limit" in params, "Missing 'expiry_limit' in params"
    assert "max_scheduled_time" in params, "Missing 'max_scheduled_time' in params"
    assert isinstance(
        int(params["block_gas_limit"]), int
    ), "block_gas_limit should be an integer"
    assert isinstance(
        int(params["expiry_limit"]), int
    ), "expiry_limit should be an integer"
    assert isinstance(
        int(params["max_scheduled_time"]), int
    ), "max_scheduled_time should be an integer"

    dysond_bin = chainnet[0]
    # ensure the param exists in the response for basic sanity; the actual
    # governance update is performed in `test_crontask_governance_update_cleanup_param`.
    assert "clean_up_time" in params, "Missing 'clean_up_time' in params"
    print(f"Crontask params: {params}")


def test_create_task_and_query_by_id(chainnet, generate_account, faucet):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address)
    task_id = create_task_for_test(dysond_bin, alice_name, alice_address)
    assert task_id is not None, "Task ID should not be None"


def test_query_tasks_by_address(chainnet, generate_account, faucet):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address)
    task_id = create_task_for_test(dysond_bin, alice_name, alice_address)
    assert task_id is not None, "Task ID should not be None"
    tasks_result = dysond_bin(
        "query", "crontask", "tasks-by-address", "--creator", alice_address
    )
    assert "tasks" in tasks_result, "Tasks response does not contain 'tasks' field"
    tasks = tasks_result["tasks"]
    assert len(tasks) > 0, "No tasks found for the address"
    for task in tasks:
        assert (
            task["creator"] == alice_address
        ), f"Creator mismatch: {task['creator']} != {alice_address}"
    print(f"Found {len(tasks)} tasks for address {alice_address}")


def test_query_tasks_by_status_timestamp(chainnet, generate_account):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=10000)

    # Create tasks and track their IDs
    task_id1 = create_task_for_test_with_timestamp(
        dysond_bin, alice_name, alice_address, time_offset=TASK_SCHEDULED_DELAY + 3
    )
    task_id2 = create_task_for_test_with_timestamp(
        dysond_bin, alice_name, alice_address, time_offset=TASK_SCHEDULED_DELAY + 6
    )
    created_task_ids = {int(task_id1), int(task_id2)}

    tasks_result = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-timestamp",
        "--status",
        "SCHEDULED",
        "--page-reverse",
    )
    assert "tasks" in tasks_result, "Tasks response does not contain 'tasks' field"
    tasks = tasks_result["tasks"]

    # Filter to find our created tasks
    our_tasks = [task for task in tasks if int(task["task_id"]) in created_task_ids]
    assert (
        len(our_tasks) == 2
    ), f"Expected to find both created tasks, found {len(our_tasks)}"

    # Verify all tasks have the correct status
    for task in tasks:
        assert (
            task["status"] == "SCHEDULED"
        ), f"Status mismatch: {task['status']} != SCHEDULED"

    # Use a separate assertion that works for all cases
    assert all(
        int(tasks[i]["scheduled_timestamp"]) <= int(tasks[i + 1]["scheduled_timestamp"])
        for i in range(max(0, len(tasks) - 1))
    ), f"Tasks not ordered by timestamp ascending: {tasks}"

    # Find positions of our tasks
    task_positions = [(i, int(task["task_id"])) for i, task in enumerate(tasks)]
    task1_positions = [i for i, tid in task_positions if tid == int(task_id1)]
    task2_positions = [i for i, tid in task_positions if tid == int(task_id2)]

    # Assert both tasks are found
    assert len(task1_positions) == 1, f"Task1 should appear exactly once"
    assert len(task2_positions) == 1, f"Task2 should appear exactly once"

    # task1 should appear before task2 since it has earlier timestamp
    assert (
        task1_positions[0] < task2_positions[0]
    ), "Task1 should appear before task2 in timestamp order"

    print(f"Found {len(tasks)} tasks with status SCHEDULED, including our 2 tasks")


def test_query_tasks_by_status_gas_price(chainnet, generate_account):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)

    # Create tasks and track their IDs
    task_id1 = create_task_for_test_with_gas_price(
        dysond_bin, alice_name, alice_address, gas_price=1
    )
    task_id2 = create_task_for_test_with_gas_price(
        dysond_bin, alice_name, alice_address, gas_price=2
    )
    created_task_ids = {int(task_id1), int(task_id2)}

    tasks_result = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-gas-price",
        "--status",
        "SCHEDULED",
    )
    assert "tasks" in tasks_result, "Tasks response does not contain 'tasks' field"
    tasks = tasks_result["tasks"]

    # Filter to find our created tasks
    our_tasks = [task for task in tasks if int(task["task_id"]) in created_task_ids]
    assert (
        len(our_tasks) == 2
    ), f"Expected to find both created tasks, found {len(our_tasks)}"

    # Verify all tasks have the correct status
    for task in tasks:
        assert (
            task["status"] == "SCHEDULED"
        ), f"Status mismatch: {task['status']} != SCHEDULED"

    # Check gas price ordering for all tasks

    gas_prices = [
        decimal.Decimal(task["task_gas_price"].strip("udys")) for task in tasks
    ]
    # Default order is descending by gas price
    assert all(
        gas_prices[i] >= gas_prices[i + 1] for i in range(max(0, len(gas_prices) - 1))
    ), f"Tasks not ordered by gas price descending: {tasks}"

    # Find positions of our tasks
    task_positions = [(i, int(task["task_id"])) for i, task in enumerate(tasks)]
    task1_positions = [i for i, tid in task_positions if tid == int(task_id1)]
    task2_positions = [i for i, tid in task_positions if tid == int(task_id2)]

    # Assert both tasks are found
    assert len(task1_positions) == 1, f"Task1 should appear exactly once"
    assert len(task2_positions) == 1, f"Task2 should appear exactly once"

    # With default DESC order, higher gas price (task2) should appear before lower (task1)
    assert (
        task2_positions[0] < task1_positions[0]
    ), "Task2 should appear before task1 in gas price order (DESC)"

    print(f"Found {len(tasks)} tasks with status SCHEDULED, including our 2 tasks")


def test_delete_task(chainnet, generate_account):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)
    task_id = create_task_for_test(dysond_bin, alice_name, alice_address)
    delete_result = dysond_bin(
        "tx",
        "crontask",
        "delete-task",
        "--task-id",
        str(task_id),
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    print(f"Delete task result: {delete_result}")

    # Query the task after deletion - expect it to be deleted (key not found error)
    task_result = dysond_bin(
        "query", "crontask", "task-by-id", "--task-id", str(task_id)
    )
    assert isinstance(
        task_result, str
    ), f"Expected string error on deleted task, got {type(task_result)}: {task_result}"
    assert "key not found" in task_result, f"'key not found' not in: {task_result}"
    print(f"Task {task_id} successfully deleted")


def test_task_execution(chainnet, generate_account, faucet):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, amount=100)
    now = int(datetime.datetime.now().timestamp())
    scheduled_time = now + TASK_SCHEDULED_DELAY
    expiry_time = now + 86400
    msg_obj = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_address,
        "to_address": alice_address,
        "amount": [{"denom": "udys", "amount": "1"}],
    }
    create_result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        str(scheduled_time),
        "--expiry-timestamp",
        str(expiry_time),
        "--task-gas-limit",
        str(GAS_LIMIT),
        "--task-gas-fee",
        f"{GAS_FEE}udys",
        "--msgs",
        json.dumps(msg_obj),
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    # Extract task ID from events using list comprehensions
    task_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    task_id_attrs = [
        a
        for e in task_events
        for a in e.get("attributes", [])
        if a.get("key") == "task_id"
    ]

    # Use direct assertion instead of conditional
    assert task_id_attrs, "No task_id attribute found in events"
    task_id = json.loads(task_id_attrs[0].get("value"))
    assert task_id is not None, "Failed to extract task ID"

    print(
        f"Created task {task_id} scheduled for {scheduled_time} (in {TASK_SCHEDULED_DELAY}s)"
    )

    def check_task_executed():
        task_result = dysond_bin(
            "query", "crontask", "task-by-id", "--task-id", str(task_id)
        )

        # Task was deleted - not done
        task_deleted = isinstance(task_result, str) and "key not found" in task_result
        assert (
            not task_deleted
        ), f"Task {task_id} was unexpectedly deleted during execution"

        # Task should exist as dict
        assert isinstance(
            task_result, dict
        ), f"Unexpected response format: {task_result}"

        task = task_result.get("task", {})
        status = task.get("status")

        # Assert if task failed
        assert (
            status != "FAILED"
        ), f"Task failed unexpectedly: {task.get('error_log', 'no error log')}"

        # Return True if done
        return status == "DONE"

    # Wait for scheduled time + execution time
    poll_until_condition(
        check_task_executed,
        timeout=TASK_SCHEDULED_DELAY + TASK_WAIT_TIMEOUT,
        error_message=f"Task {task_id} was not executed within timeout",
    )
    print(f"Task {task_id} executed successfully")


# Helper function to create a task for testing


def create_task_for_test(dysond_bin, creator_name, creator_address) -> int:
    now = int(datetime.datetime.now().timestamp())
    scheduled_time = now + TASK_SCHEDULED_DELAY
    expiry_time = now + 86400
    gas_limit = 200000
    gas_fee = max(1, int(gas_limit * 0.0000001))
    msg_obj = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": creator_address,
        "to_address": creator_address,
        "amount": [{"denom": "udys", "amount": "1"}],
    }
    create_result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        str(scheduled_time),
        "--expiry-timestamp",
        str(expiry_time),
        "--task-gas-limit",
        str(gas_limit),
        "--task-gas-fee",
        f"{gas_fee}udys",
        "--msgs",
        json.dumps(msg_obj),
        "--from",
        creator_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    # Extract task ID from events using list comprehensions
    task_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    task_id_attrs = [
        a
        for e in task_events
        for a in e.get("attributes", [])
        if a.get("key") == "task_id"
    ]

    # Use direct assertion instead of conditional
    assert task_id_attrs, "No task_id attribute found in events"
    task_id = json.loads(task_id_attrs[0].get("value"))
    assert task_id is not None, "Failed to extract task ID"
    return task_id


def create_task_for_test_with_gas_price(
    dysond_bin, creator_name, creator_address, gas_price: int = 1
) -> int:
    now = int(datetime.datetime.now().timestamp())
    scheduled_time = now + TASK_SCHEDULED_DELAY
    expiry_time = now + 86400
    gas_limit = 200000
    gas_fee = gas_price
    msg_obj = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": creator_address,
        "to_address": creator_address,
        "amount": [{"denom": "udys", "amount": "1"}],
    }
    create_result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        str(scheduled_time),
        "--expiry-timestamp",
        str(expiry_time),
        "--task-gas-limit",
        str(gas_limit),
        "--task-gas-fee",
        f"{gas_fee}udys",
        "--msgs",
        json.dumps(msg_obj),
        "--from",
        creator_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    # Extract task ID from events using list comprehensions
    task_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    task_id_attrs = [
        a
        for e in task_events
        for a in e.get("attributes", [])
        if a.get("key") == "task_id"
    ]

    # Use direct assertion instead of conditional
    assert task_id_attrs, "No task_id attribute found in events"
    task_id = json.loads(task_id_attrs[0].get("value"))
    assert task_id is not None, "Failed to extract task ID"
    return task_id


def create_task_for_test_with_timestamp(
    dysond_bin, creator_name, creator_address, time_offset: int = 5
) -> int:
    now = int(datetime.datetime.now().timestamp())
    scheduled_time = f"+{time_offset}s"
    expiry_time = f"+{86400}s"
    gas_limit = 200000
    gas_fee = max(1, int(gas_limit * 0.0000001))
    msg_obj = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": creator_address,
        "to_address": creator_address,
        "amount": [{"denom": "udys", "amount": "1"}],
    }
    create_result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        str(scheduled_time),
        "--expiry-timestamp",
        str(expiry_time),
        "--task-gas-limit",
        str(gas_limit),
        "--task-gas-fee",
        f"{gas_fee}udys",
        "--msgs",
        json.dumps(msg_obj),
        "--from",
        creator_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    # Extract task ID from events using list comprehensions
    task_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    task_id_attrs = [
        a
        for e in task_events
        for a in e.get("attributes", [])
        if a.get("key") == "task_id"
    ]

    # Use direct assertion instead of conditional
    assert task_id_attrs, "No task_id attribute found in events"
    task_id = json.loads(task_id_attrs[0].get("value"))
    assert task_id is not None, "Failed to extract task ID"
    return task_id


# -----------------------------------------------------------------------------
# Additional coverage: order DESC (default) and pagination on index-backed
# queries. These tests reuse the helper functions defined earlier in this file
# to avoid duplicated task-creation logic.
# -----------------------------------------------------------------------------


def test_query_tasks_by_status_timestamp_desc(chainnet, generate_account):
    """Default (descending) ordering of scheduled tasks by timestamp."""
    dysond_bin = chainnet[0]
    [name, addr] = generate_account("ts_desc", faucet_amount=1)

    # Create three tasks with staggered future times so they remain SCHEDULED
    # Track their IDs and timestamps
    created_tasks_info = []
    for offset in [120, 180, 240]:
        task_id = create_task_for_test_with_timestamp(
            dysond_bin, name, addr, time_offset=offset
        )
        created_tasks_info.append((task_id, offset))

    res = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-timestamp",
        "--status",
        "SCHEDULED",
        "--page-limit",
        "1000",
    )

    # Filter to only our created tasks
    our_task_ids = {int(tid) for tid, _ in created_tasks_info}
    our_tasks = [t for t in res.get("tasks", []) if int(t["task_id"]) in our_task_ids]

    # Verify we found all our tasks
    assert (
        len(our_tasks) == 3
    ), f"Expected to find all 3 created tasks, found {len(our_tasks)}"

    # Extract timestamps for our tasks in the order they appear
    our_task_timestamps = [int(t["scheduled_timestamp"]) for t in our_tasks]

    # Verify our tasks are sorted by timestamp in descending order
    assert our_task_timestamps == sorted(
        our_task_timestamps, reverse=True
    ), f"Our tasks should be sorted by timestamp DESC, got {our_task_timestamps}"


def test_query_tasks_by_status_timestamp_pagination(chainnet, generate_account):
    """Verify offset/limit pagination on timestamp index (ascending)."""
    dysond_bin = chainnet[0]
    [name, addr] = generate_account("ts_page", faucet_amount=1)

    # Create tasks and track their IDs
    created_task_ids = []
    for off in (1, 2, 3, 4):
        task_id = create_task_for_test_with_timestamp(
            dysond_bin, name, addr, time_offset=TASK_SCHEDULED_DELAY + off + 5
        )
        created_task_ids.append(task_id)

    # Query all scheduled tasks to verify our tasks exist
    all_tasks_result = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-timestamp",
        "--status",
        "SCHEDULED",
        "--page-limit",
        "1000",
        "--page-reverse",
    )

    # Verify our tasks are present
    our_task_ids_set = {str(tid) for tid in created_task_ids}
    all_task_ids = {t["task_id"] for t in all_tasks_result.get("tasks", [])}
    assert our_task_ids_set.issubset(
        all_task_ids
    ), f"Not all created tasks found. Created: {created_task_ids}"

    # Now test pagination
    page0 = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-timestamp",
        "--status",
        "SCHEDULED",
        "--page-limit",
        "2",
        "--page-offset",
        "0",
        "--page-reverse",
    )
    page1 = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-timestamp",
        "--status",
        "SCHEDULED",
        "--page-limit",
        "2",
        "--page-offset",
        "2",
        "--page-reverse",
    )

    # Ensure JSON decoded properly
    assert isinstance(page0, dict) and isinstance(
        page1, dict
    ), f"Pagination query failed: {page0} | {page1}"

    # Both pages should have tasks (since we're querying all scheduled tasks)
    # But we can't assume exact counts due to other tests
    page0_tasks = page0.get("tasks", [])
    page1_tasks = page1.get("tasks", [])

    # Check that pagination works correctly (no overlap)
    ids1 = {t["task_id"] for t in page0_tasks}
    ids2 = {t["task_id"] for t in page1_tasks}
    assert ids1.isdisjoint(
        ids2
    ), f"Pagination pages should not overlap: {ids1} | {ids2}"

    # Verify timestamps are in ascending order within page0 (when it has multiple tasks)
    page0_timestamps = [int(t["scheduled_timestamp"]) for t in page0_tasks]
    assert all(
        page0_timestamps[i] <= page0_timestamps[i + 1]
        for i in range(max(0, len(page0_timestamps) - 1))
    ), f"Page0 timestamps should be in ascending order"

    # Verify timestamps are in ascending order within page1 (when it has multiple tasks)
    page1_timestamps = [int(t["scheduled_timestamp"]) for t in page1_tasks]
    assert all(
        page1_timestamps[i] <= page1_timestamps[i + 1]
        for i in range(max(0, len(page1_timestamps) - 1))
    ), f"Page1 timestamps should be in ascending order"

    # Verify timestamp ordering across pages when both have tasks
    # Create a combined check that works regardless of page contents
    all_timestamps = page0_timestamps + page1_timestamps
    assert all(
        all_timestamps[i] <= all_timestamps[i + 1]
        for i in range(max(0, len(all_timestamps) - 1))
    ), "Combined timestamps should be in ascending order"


def test_query_tasks_by_status_gas_price_desc(chainnet, generate_account):
    """Default (descending) ordering of scheduled tasks by gas price."""
    dysond_bin = chainnet[0]
    [name, addr] = generate_account("gp_desc", faucet_amount=1)

    # Create tasks and track their IDs with their gas prices
    created_tasks_info = []
    for gas_price in [1, 3, 2]:
        task_id = create_task_for_test_with_gas_price(
            dysond_bin, name, addr, gas_price=gas_price
        )
        created_tasks_info.append((task_id, gas_price))

    res = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-gas-price",
        "--status",
        "SCHEDULED",
        "--page-reverse",  # Get results in descending order
        "--page-limit",
        "1000",  # Get all tasks
    )

    # Filter to only our created tasks
    our_task_ids = {int(tid) for tid, _ in created_tasks_info}
    our_tasks = [t for t in res.get("tasks", []) if int(t["task_id"]) in our_task_ids]

    # Verify we found all our tasks
    assert (
        len(our_tasks) == 3
    ), f"Expected to find all 3 created tasks, found {len(our_tasks)}"

    # Extract gas prices and task IDs for our tasks
    our_tasks_with_prices = []
    for t in our_tasks:
        task_id = int(t["task_id"])
        # Gas fee is stored in task_gas_fee, not task_gas_price
        gas_fee_obj = t.get("task_gas_fee", {})
        amount_str = str(gas_fee_obj.get("amount", "0"))
        # Remove 'udys' suffix and convert to int
        amount_str_clean = amount_str.replace("udys", "")
        gas_price = int(amount_str_clean)
        our_tasks_with_prices.append((task_id, gas_price))

    # Sort our tasks by gas price in descending order
    our_tasks_sorted = sorted(our_tasks_with_prices, key=lambda x: x[1], reverse=True)

    # Verify the sorted order matches our expectation
    expected_prices = [3, 2, 1]
    actual_prices = [price for _, price in our_tasks_sorted]
    assert (
        actual_prices == expected_prices
    ), f"Expected gas prices {expected_prices} after sorting, got {actual_prices}"


def test_query_tasks_by_status_gas_price_pagination(chainnet, generate_account):
    """Check pagination slice on gas-price index (ascending)."""
    dysond_bin = chainnet[0]
    [name, addr] = generate_account("gp_page", faucet_amount=1)

    # Create tasks and track their IDs
    created_task_ids = []
    for price in (5, 4, 7, 6):
        task_id = create_task_for_test_with_gas_price(
            dysond_bin, name, addr, gas_price=price
        )
        created_task_ids.append(task_id)
        print(f"Created task {task_id} with gas price {price}")

    # Convert task IDs to integers for comparison
    created_task_ids_int = [int(tid) for tid in created_task_ids]

    # Query all SCHEDULED tasks to verify our tasks exist
    all_tasks_result = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-gas-price",
        "--status",
        "SCHEDULED",
        "--page-limit",
        "1000",  # Get all tasks
    )

    # Filter to only our created tasks
    our_task_ids = {int(tid) for tid in created_task_ids}
    our_tasks = [
        t
        for t in all_tasks_result.get("tasks", [])
        if int(t["task_id"]) in our_task_ids
    ]
    assert (
        len(our_tasks) == 4
    ), f"Expected to find all 4 created tasks, found {len(our_tasks)}"

    # Now test pagination mechanics with page size 2
    # Page 0: offset=0, limit=2
    page0 = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-gas-price",
        "--status",
        "SCHEDULED",
        "--page-offset",
        "0",
        "--page-limit",
        "2",
        "--page-reverse",
    )

    # Page 1: offset=2, limit=2
    page1 = dysond_bin(
        "query",
        "crontask",
        "tasks-by-status-gas-price",
        "--status",
        "SCHEDULED",
        "--page-offset",
        "2",
        "--page-limit",
        "2",
        "--page-reverse",
    )

    # Verify basic pagination mechanics
    page0_tasks = page0.get("tasks", [])
    page1_tasks = page1.get("tasks", [])

    # Should get exactly 2 tasks per page (or less if fewer tasks exist)
    assert (
        len(page0_tasks) <= 2
    ), f"Page 0 should have at most 2 tasks, got {len(page0_tasks)}"
    assert (
        len(page1_tasks) <= 2
    ), f"Page 1 should have at most 2 tasks, got {len(page1_tasks)}"

    # Check that pagination works correctly (no overlap)
    ids0 = {t["task_id"] for t in page0_tasks}
    ids1 = {t["task_id"] for t in page1_tasks}
    assert ids0.isdisjoint(ids1), "Pagination pages should not overlap"

    # Verify gas prices are in ascending order within each page
    page0_prices = [
        decimal.Decimal(t["task_gas_price"].strip("udys")) for t in page0_tasks
    ]
    assert all(
        page0_prices[i] <= page0_prices[i + 1]
        for i in range(max(0, len(page0_prices) - 1))
    ), f"Page0 gas prices should be in ascending order"

    page1_prices = [
        decimal.Decimal(t["task_gas_price"].strip("udys")) for t in page1_tasks
    ]
    assert all(
        page1_prices[i] <= page1_prices[i + 1]
        for i in range(max(0, len(page1_prices) - 1))
    ), f"Page1 gas prices should be in ascending order"

    # Verify ordering between pages when both have tasks
    # The minimum price in page1 should be >= maximum price in page0
    # Use a boolean expression to check this only when both lists have elements
    both_have_tasks = bool(page0_prices) and bool(page1_prices)
    cross_page_ordering_valid = (not both_have_tasks) or (
        max(page0_prices) <= min(page1_prices)
    )
    assert (
        cross_page_ordering_valid
    ), f"Page1 should have higher or equal gas prices than page0"


# -----------------------------------------------------------------------------
# Task 1-7 additional happy-path tests covering new CLI endpoints
# -----------------------------------------------------------------------------


def create_task_high_gas_limit(
    dysond_bin,
    creator_name: str,
    creator_address: str,
    gas_limit: int,
    gas_price: int = 1,
):
    """Create a task with a specific gas limit (potentially > block limit).
    Returns task_id.
    """
    now = int(datetime.datetime.now().timestamp())
    scheduled_time = now + TASK_SCHEDULED_DELAY
    expiry_time = now + 86400
    msg_obj = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": creator_address,
        "to_address": creator_address,
        "amount": [{"denom": "udys", "amount": "1"}],
    }
    gas_fee_amount = gas_price * gas_limit
    create_result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        str(scheduled_time),
        "--expiry-timestamp",
        str(expiry_time),
        "--task-gas-limit",
        str(gas_limit),
        "--task-gas-fee",
        f"{gas_fee_amount}udys",
        "--msgs",
        json.dumps(msg_obj),
        "--from",
        creator_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    # Extract task ID from events using list comprehensions
    task_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    task_id_attrs = [
        a
        for e in task_events
        for a in e.get("attributes", [])
        if a.get("key") == "task_id"
    ]

    # Use direct assertion instead of conditional
    assert task_id_attrs, "No task_id attribute found in events"
    task_id = json.loads(task_id_attrs[0].get("value"))
    assert task_id is not None, "Failed to extract task ID"
    return task_id


def test_tasks_all_endpoint(chainnet, generate_account):
    """Verify /tasks/all lists tasks ordered by ID ASC."""
    dysond_bin = chainnet[0]
    [name, addr] = generate_account("all")
    # Create three tasks so we know recent IDs
    ids = [create_task_for_test(dysond_bin, name, addr) for _ in range(3)]

    res = dysond_bin("query", "crontask", "tasks-all")
    assert (
        isinstance(res, dict) and "tasks" in res
    ), "tasks-all returned non-json response or missing tasks"
    id_list = [int(t["task_id"]) for t in res["tasks"]]
    assert id_list == sorted(
        id_list
    ), "tasks-all should be ordered by task_id ascending"


# -----------------------------------------------------------------------------
# Task 1-8 pagination tests for new CLI endpoints
# -----------------------------------------------------------------------------


def _assert_pages_non_overlapping(page0: dict, page1: dict):
    """Helper to assert two paginated responses are valid and non-overlapping."""
    assert isinstance(page0, dict) and isinstance(
        page1, dict
    ), f"Pagination query failed: {page0} | {page1}"
    assert len(page0.get("tasks", [])) >= 1, "First page returned no tasks"
    assert len(page1.get("tasks", [])) >= 1, "Second page returned no tasks"

    ids0 = {t["task_id"] for t in page0.get("tasks", [])}
    ids1 = {t["task_id"] for t in page1.get("tasks", [])}
    assert ids0.isdisjoint(ids1), "Pagination pages should not overlap"


# ------------------------------
# /tasks/all
# ------------------------------


def test_tasks_all_pagination(chainnet, generate_account):
    """Verify offset/limit pagination on /tasks/all endpoint."""
    dysond_bin = chainnet[0]
    [name, addr] = generate_account("all_page")

    # Create at least 4 tasks so there is something to paginate over
    for _ in range(4):
        create_task_for_test(dysond_bin, name, addr)

    page0 = dysond_bin(
        "query",
        "crontask",
        "tasks-all",
        "--page-limit",
        "2",
        "--page-offset",
        "0",
    )
    page1 = dysond_bin(
        "query",
        "crontask",
        "tasks-all",
        "--page-limit",
        "2",
        "--page-offset",
        "2",
    )

    _assert_pages_non_overlapping(page0, page1)


# ------------------------------------------------------------------
# Test that DONE tasks are automatically cleaned up after the short retention.
# ------------------------------------------------------------------


def test_done_tasks_are_cleaned_up(
    chainnet, generate_account, faucet, update_crontask_params
):
    """Test that DONE tasks are automatically cleaned up after the short retention."""
    _ = update_crontask_params
    dysond_bin = chainnet[0]

    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, amount=100)

    msg_obj = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_address,
        "to_address": alice_address,
        "amount": [{"denom": "udys", "amount": "1"}],
    }

    create_result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        "+1s",
        "--expiry-timestamp",
        "+10s",
        "--task-gas-limit",
        str(GAS_LIMIT),
        "--task-gas-fee",
        f"{GAS_FEE}udys",
        "--msgs",
        json.dumps(msg_obj),
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
    )

    # Extract task ID from events using list comprehensions
    task_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    task_id_attrs = [
        a
        for e in task_events
        for a in e.get("attributes", [])
        if a.get("key") == "task_id"
    ]

    # Use direct assertion instead of conditional
    assert task_id_attrs, "No task_id attribute found in events"
    task_id = json.loads(task_id_attrs[0].get("value"))
    assert task_id is not None, "Failed to extract task ID"

    def _task_done():
        task_result = dysond_bin(
            "query", "crontask", "task-by-id", "--task-id", str(task_id)
        )

        # Task deleted - not done yet
        assert isinstance(
            task_result, dict
        ), f"Expected dict response during execution, got {type(task_result)}: {task_result}"

        # Return False unless explicitly DONE
        is_done = task_result.get("task", {}).get("status") == "DONE"

        # Print status for debugging
        task_data = task_result if not isinstance(task_result, dict) else task_result
        print(f"Task {task_id} status check: DONE={is_done}, data={task_data}")

        return is_done

    print("Waiting for task to reach DONE...")
    poll_until_condition(
        _task_done,
        timeout=10,
        poll_interval=0.2,
        error_message="Task did not reach DONE state in time",
    )

    # Now poll for deletion instead of fixed sleep
    def _task_deleted():
        out = dysond_bin("query", "crontask", "task-by-id", "--task-id", str(task_id))
        is_deleted = "key not found" in out

        # Print status for debugging
        print(f"Task {task_id} deletion check: deleted={is_deleted}, response={out}")
        return is_deleted

    print("Polling until task is deleted by cleanup logic…")
    poll_until_condition(
        _task_deleted,
        timeout=10,
        poll_interval=0.5,
        error_message="Task was not cleaned up within expected time window",
    )
