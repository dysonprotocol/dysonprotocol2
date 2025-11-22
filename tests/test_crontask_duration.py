import json
import pytest
import time
from tests import utils
from typing import Dict, Any, List


def extract_task_id(result: Dict[str, Any]) -> int:
    """Extract task_id from transaction result."""
    # Find EventTaskCreated events
    task_created_events = [
        e
        for e in result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    assert task_created_events, "No EventTaskCreated found in transaction events"

    # Find task_id attributes
    task_id_attrs = [
        a
        for a in task_created_events[0].get("attributes", [])
        if a.get("key") == "task_id"
    ]
    assert task_id_attrs, "No task_id attribute found in EventTaskCreated"

    # Strip quotes from the value and return as int
    task_id_str = task_id_attrs[0].get("value").strip('"')
    return int(task_id_str)


def test_absolute_timestamp_format(chainnet, generate_account, faucet):
    """Test creating a task using absolute Unix timestamp format."""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Use Unix timestamps for scheduling
    current_time = int(time.time())
    scheduled_time = current_time + 5  # Schedule 5 seconds in the future
    expiry_time = scheduled_time + 10  # Expire 10 seconds after scheduled time

    # Create the task
    result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        f"--scheduled-timestamp",
        str(scheduled_time),
        f"--expiry-timestamp",
        str(expiry_time),
        "--task-gas-limit",
        "200000",
        "--task-gas-fee",
        "1udys",
        "--msgs",
        f'{{"@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "{alice_address}", "to_address": "{alice_address}", "amount": [{{"denom": "udys", "amount": "1"}}]}}',
        "--from",
        alice_name,
    )

    task_id = extract_task_id(result)

    # Verify task exists and has valid status
    result = dysond_bin("query", "crontask", "task-by-id", "--task-id", str(task_id))
    task = result["task"]

    valid_statuses = ["SCHEDULED", "PENDING", "DONE", "FAILED", "EXPIRED"]
    print(f"Task status: {task['status']}")
    expected = f"Task has invalid status: {task['status']}"
    assert task["status"] in valid_statuses, expected

    # Verify timestamps match what we set
    stored_scheduled_time = int(task["scheduled_timestamp"])
    stored_expiry_time = int(task["expiry_timestamp"])
    assert (
        stored_scheduled_time == scheduled_time
    ), f"Scheduled timestamp mismatch: {stored_scheduled_time} != {scheduled_time}"
    assert (
        stored_expiry_time == expiry_time
    ), f"Expiry timestamp mismatch: {stored_expiry_time} != {expiry_time}"
    # Exact delta based on inputs
    assert (
        stored_expiry_time - stored_scheduled_time
    ) == 10, f"Expected delta 10s, got {stored_expiry_time - stored_scheduled_time}"


def test_scheduled_duration_format(chainnet, generate_account, faucet):
    """Test using duration format for scheduled_timestamp and absolute timestamp for expiry."""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Use Unix timestamp for expiry, duration for scheduled
    current_time = int(time.time())
    expiry_time = current_time + 15  # Expire 15 seconds from now

    # Create the task with scheduled as duration and expiry as timestamp
    result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        "+5s",  # Schedule 5 seconds from now
        f"--expiry-timestamp",
        str(expiry_time),
        "--task-gas-limit",
        "200000",
        "--task-gas-fee",
        "1udys",
        "--msgs",
        f'{{"@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "{alice_address}", "to_address": "{alice_address}", "amount": [{{"denom": "udys", "amount": "1"}}]}}',
        "--from",
        alice_name,
    )

    task_id = extract_task_id(result)

    # Verify task exists and has valid status
    result = dysond_bin("query", "crontask", "task-by-id", "--task-id", str(task_id))
    task = result["task"]

    assert task["status"] in [
        "SCHEDULED",
        "PENDING",
        "DONE",
        "FAILED",
        "EXPIRED",
    ], f"Task has invalid status: {task['status']}"

    # Verify duration was converted to a timestamp correctly
    stored_scheduled_time = int(task["scheduled_timestamp"])
    stored_expiry_time = int(task["expiry_timestamp"])

    # Deterministic checks: exact expiry equals the absolute value we set
    print(
        f"scheduled={stored_scheduled_time}, expiry={stored_expiry_time}, expected_expiry={expiry_time}"
    )
    # We cannot assert exact scheduled here due to block-time evaluation; only expiry is deterministic
    assert (
        stored_expiry_time == expiry_time
    ), f"Expiry timestamp mismatch: {stored_expiry_time} != {expiry_time}"
    assert (
        stored_expiry_time - stored_scheduled_time
    ) >= 5, f"Expected at least 5s between expiry and scheduled, got {stored_expiry_time - stored_scheduled_time}"


def test_both_durations_format(chainnet, generate_account, faucet):
    """Test using duration format for both scheduled_timestamp and expiry_timestamp."""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Create the task with both scheduled and expiry as durations
    result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        "+5s",  # Schedule 5 seconds from now
        "--expiry-timestamp",
        "+10s",  # Expire 10 seconds after scheduled time
        "--task-gas-limit",
        "200000",
        "--task-gas-fee",
        "1udys",
        "--msgs",
        f'{{"@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "{alice_address}", "to_address": "{alice_address}", "amount": [{{"denom": "udys", "amount": "1"}}]}}',
        "--from",
        alice_name,
    )

    task_id = extract_task_id(result)

    # Verify task exists and has valid status
    result = dysond_bin("query", "crontask", "task-by-id", "--task-id", str(task_id))
    task = result["task"]

    assert task["status"] in [
        "SCHEDULED",
        "PENDING",
        "DONE",
        "FAILED",
        "EXPIRED",
    ], f"Task has invalid status: {task['status']}"

    # Verify durations were converted to timestamps correctly
    stored_scheduled_time = int(task["scheduled_timestamp"])
    stored_expiry_time = int(task["expiry_timestamp"])

    # Verify the difference between expiry and scheduled is exactly 10s
    print(f"expiry-scheduled delta: {stored_expiry_time - stored_scheduled_time}")
    assert (
        stored_expiry_time - stored_scheduled_time
    ) == 10, f"Relative duration delta mismatch: {(stored_expiry_time - stored_scheduled_time)}"


def test_invalid_expiry_time(chainnet, generate_account, faucet):
    """Test that the system properly validates task expiry time."""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Create a task with an expiry time that is before the scheduled time
    current_time = int(time.time())
    scheduled_time = current_time + 10  # Schedule 10 seconds in the future
    expiry_time = (
        current_time + 5
    )  # But expire 5 seconds from now (before scheduled time)

    # The blockchain should reject this transaction with a specific error
    result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        f"--scheduled-timestamp",
        str(scheduled_time),
        f"--expiry-timestamp",
        str(expiry_time),
        "--task-gas-limit",
        "200000",
        "--task-gas-fee",
        "1udys",
        "--msgs",
        f'{{"@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "{alice_address}", "to_address": "{alice_address}", "amount": [{{"denom": "udys", "amount": "1"}}]}}',
        "--from",
        alice_name,
    )

    # Check that the transaction failed with the expected error
    assert (
        result["code"] != 0
    ), f"Transaction should have failed but succeeded: {result}"
    assert (
        "expiry time must be after scheduled time" in result["raw_log"]
    ), f"Expected error message not found in: {result['raw_log']}"


def test_task_execution(chainnet, generate_account, faucet):
    """Test that a task executes successfully when its scheduled time is reached."""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Create a task with immediate scheduling
    result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        "+1s",  # Schedule 1 second from now
        "--expiry-timestamp",
        "+10s",  # Expire 10 seconds after scheduled time
        "--task-gas-limit",
        "200000",
        "--task-gas-fee",
        "1udys",
        "--msgs",
        f'{{"@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "{alice_address}", "to_address": "{alice_address}", "amount": [{{"denom": "udys", "amount": "1"}}]}}',
        "--from",
        alice_name,
    )

    task_id = extract_task_id(result)

    # Define a function to check if the task has been executed
    def check_task_executed():
        result = dysond_bin(
            "query", "crontask", "task-by-id", "--task-id", str(task_id)
        )
        task = result["task"]
        return task["status"] == "DONE"

    # Wait for task to be executed with polling
    utils.poll_until_condition(
        check_func=check_task_executed,
        timeout=10,  # Maximum 10 seconds to wait
        poll_interval=0.2,  # Check every 200ms
        error_message=f"Task {task_id} was not executed within the expected timeframe",
    )

    # Get final task state to verify successful execution
    result = dysond_bin("query", "crontask", "task-by-id", "--task-id", str(task_id))
    task = result["task"]

    # Verify the task is in DONE status and has results
    assert (
        task["status"] == "DONE"
    ), f"Task should be in DONE status, found {task['status']}"
    assert len(task["msg_results"]) > 0, "Task execution didn't produce any results"


def test_task_status_change(chainnet, generate_account, faucet):
    """Test that a task changes status properly when executed or expired."""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Create a task with immediate scheduling but delay it slightly to ensure we can catch it in SCHEDULED status
    result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        "+2s",  # Schedule 2 seconds from now to give us time to check the initial status
        "--expiry-timestamp",
        "+10s",  # Expire 10 seconds after scheduled
        "--task-gas-limit",
        "200000",
        "--task-gas-fee",
        "1udys",
        "--msgs",
        f'{{"@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "{alice_address}", "to_address": "{alice_address}", "amount": [{{"denom": "udys", "amount": "1"}}]}}',
        "--from",
        alice_name,
    )

    task_id = extract_task_id(result)

    # Get initial task state
    result = dysond_bin("query", "crontask", "task-by-id", "--task-id", str(task_id))
    task = result["task"]

    # Verify the task starts in SCHEDULED status (prior to being picked up by the scheduler)
    assert (
        task["status"] == "SCHEDULED"
    ), f"Task should start in SCHEDULED status, found {task['status']}"

    # Wait for the task to change status from SCHEDULED
    def check_task_status_changed():
        result = dysond_bin(
            "query", "crontask", "task-by-id", "--task-id", str(task_id)
        )
        task = result["task"]
        return task["status"] != "SCHEDULED"

    # Wait for status to change with polling
    utils.poll_until_condition(
        check_func=check_task_status_changed,
        timeout=10,  # Maximum 10 seconds to wait
        poll_interval=0.2,  # Check every 200ms
        error_message=f"Task {task_id} status didn't change from SCHEDULED",
    )

    # Get final task state
    result = dysond_bin("query", "crontask", "task-by-id", "--task-id", str(task_id))
    task = result["task"]

    # Verify status changed to one of the valid terminal states
    terminal = {"DONE", "FAILED", "EXPIRED"}
    assert (
        task["status"] in terminal
    ), f"Task status should be one of {sorted(list(terminal))}, found {task['status']}"

    # For terminal status, require exact result count deterministically
    expected_results_by_status = {"DONE": 1, "FAILED": 0, "EXPIRED": 0}
    actual_results = len(task.get("msg_results", []))
    assert (
        actual_results == expected_results_by_status[task["status"]]
    ), f"Expected exactly {expected_results_by_status[task['status']]} result(s) for status {task['status']}, got {actual_results}"


def test_task_failure(chainnet, generate_account, faucet):
    """Test that a task fails properly when it can't be executed successfully."""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Create a task that can't execute properly (invalid address)
    invalid_address = "dys1invalid000000000000000000000000000000000"

    result = dysond_bin(
        "tx",
        "crontask",
        "create-task",
        "--scheduled-timestamp",
        "+0s",  # Schedule immediately
        "--expiry-timestamp",
        "+10s",  # Long expiry to ensure it attempts execution
        "--task-gas-limit",
        "200000",
        "--task-gas-fee",
        "1udys",
        "--msgs",
        f'{{"@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "{alice_address}", "to_address": "{invalid_address}", "amount": [{{"denom": "udys", "amount": "1"}}]}}',
        "--from",
        alice_name,
    )

    task_id = extract_task_id(result)

    # Wait for the task to change to FAILED status
    def check_task_failed():
        result = dysond_bin(
            "query", "crontask", "task-by-id", "--task-id", str(task_id)
        )
        task = result["task"]
        return task["status"] == "FAILED"

    # Wait for task to fail with polling
    utils.poll_until_condition(
        check_func=check_task_failed,
        timeout=10,  # Maximum 10 seconds to wait
        poll_interval=0.2,  # Check every 200ms
        error_message=f"Task {task_id} did not fail within the expected timeframe",
    )

    # Final verification
    result = dysond_bin("query", "crontask", "task-by-id", "--task-id", str(task_id))
    task = result["task"]

    # Verify the task is in FAILED status
    assert (
        task["status"] == "FAILED"
    ), f"Task should be in FAILED status, found {task['status']}"
    # Failed tasks should have error information in error_log field
    assert (
        "error_log" in task
    ), "Failed task should have error information in error_log field"
    assert task["error_log"], "error_log should contain error information"
