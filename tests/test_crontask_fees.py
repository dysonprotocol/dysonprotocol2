import pytest
import json
import time
import datetime
from tests.test_crontask_cli import TASK_SCHEDULED_DELAY, TASK_WAIT_TIMEOUT
from typing import Dict, Any, List
from tests.utils import poll_until_condition


# Function to get blockchain time
def get_blockchain_time(dysond_bin):
    """Get the current blockchain time from the node status."""
    status = dysond_bin("status")
    latest_block_time = status.get("SyncInfo", {}).get("latest_block_time", "")
    # Parse the time (format: 2023-10-01T12:34:56.789Z) or fallback to system time
    dt = (
        datetime.datetime.strptime(latest_block_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        if latest_block_time
        else datetime.datetime.now()
    )
    return int(dt.timestamp())


# Test for successful fee deduction
def test_fee_deduction_success(chainnet, generate_account):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=10)
    [bob_name, bob_address] = generate_account("bob", faucet_amount=10)
    balance_before = dysond_bin("query", "bank", "balances", alice_address)
    dys_balance_before = next(
        (
            coin["amount"]
            for coin in balance_before["balances"]
            if coin["denom"] == "udys"
        ),
        "0",
    )

    print(f"Initial balance: {dys_balance_before} dys")

    # Set up test parameters using blockchain time
    current_time = get_blockchain_time(dysond_bin)
    scheduled_time = current_time + 3  # 3 seconds from now
    expiry_time = scheduled_time + 86400  # 1 day later
    gas_limit = 200000
    gas_fee = 1

    # Create a simple send message to send 1 dys from Alice to Bob
    msg_obj = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_address,
        "to_address": bob_address,
        "amount": [{"denom": "udys", "amount": "1"}],
    }

    # Create the task using execute_tx_and_wait directly
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
        alice_name,
    )

    # Extract the task ID using list comprehensions
    task_created_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    assert task_created_events, "No EventTaskCreated found in transaction events"

    task_id_attrs = [
        a
        for a in task_created_events[0].get("attributes", [])
        if a.get("key") == "task_id"
    ]
    assert task_id_attrs, "No task_id attribute found in EventTaskCreated"

    task_id = json.loads(task_id_attrs[0].get("value"))

    # Define a check function for polling task completion
    def check_task_executed():
        task_result = dysond_bin(
            "query", "crontask", "task-by-id", "--task-id", str(task_id)
        )
        task = task_result.get("task", {})

        assert (
            task.get("status") != "FAILED"
        ), f"Task failed unexpectedly: {task.get('error_log', 'no error log')}"
        return task.get("status") == "DONE"

    # Poll until task is executed
    poll_until_condition(
        check_task_executed,
        timeout=TASK_SCHEDULED_DELAY
        + TASK_WAIT_TIMEOUT,  # Need to wait for scheduled time + execution
        error_message="Task was not executed within timeout",
    )
    print(f"Task {task_id} executed successfully")

    # Define a check function for polling balance updates
    def check_balance_updated():
        nonlocal balance_after_int_result
        balance_after = dysond_bin("query", "bank", "balances", alice_address)
        dys_balance_after = next(
            (
                coin["amount"]
                for coin in balance_after["balances"]
                if coin["denom"] == "udys"
            ),
            "0",
        )

        balance_before_int = int(dys_balance_before)
        balance_after_int = int(dys_balance_after)

        # Check if balance has been reduced (fee deducted)
        balance_reduced = balance_before_int > balance_after_int
        # Store the updated balance for later comparison
        balance_after_int_result = balance_after_int
        return balance_reduced

    # Use a nonlocal variable to store the result
    balance_after_int_result = 0

    # Poll until balance is updated
    poll_until_condition(
        check_balance_updated,
        timeout=10,  # 10 seconds should be enough
        error_message="Balance was not updated within timeout period",
    )
    print(f"Balance was successfully updated")

    # Calculate the balance difference
    balance_before_int = int(dys_balance_before)
    balance_diff = balance_before_int - balance_after_int_result

    # The difference should be at least the gas fee plus the sent amount
    expected_diff = gas_fee + 1  # gas fee + 1 dys sent to Bob
    assert (
        balance_diff >= expected_diff
    ), f"Expected fee deduction of at least {expected_diff}, but got {balance_diff}"

    print(f"Successfully verified fee deduction: {balance_diff} dys")


# Test for insufficient funds during task execution
def test_fee_deduction_insufficient_funds(chainnet, generate_account):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    [poor_name, poor_address] = generate_account("poor_account", faucet_amount=1)
    # Fund poor_account with 1 dys

    # Calculate timestamps using blockchain time
    now = get_blockchain_time(dysond_bin)
    scheduled_time = now + TASK_SCHEDULED_DELAY
    expiry_time = now + 86400

    # Task parameters
    gas_limit = 200000
    gas_fee = max(
        2, int(gas_limit * 0.0000001)
    )  # Set fee higher than balance (at least 2 dys)

    # Create a task that should fail during execution due to insufficient funds
    msg_obj = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": poor_address,
        "to_address": poor_address,
        "amount": [{"denom": "udys", "amount": "10"}],
    }

    # Create the task using dysond directly
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
        poor_name,
    )
    print(f"Task creation succeeded with result: {json.dumps(create_result, indent=2)}")
    assert (
        create_result["code"] == 0
    ), f"Task creation failed unexpectedly: {create_result['raw_log']}"

    # Extract the task ID from the events using list comprehensions
    task_created_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventTaskCreated"
    ]
    assert task_created_events, "No EventTaskCreated found in transaction events"

    task_id_attrs = [
        a
        for a in task_created_events[0].get("attributes", [])
        if a.get("key") == "task_id"
    ]
    assert task_id_attrs, "No task_id attribute found in EventTaskCreated"

    task_id = json.loads(task_id_attrs[0].get("value"))
    print(f"Created task with ID: {task_id}")

    # Define a check function for polling task status
    def check_task_failed():
        task_result = dysond_bin(
            "query", "crontask", "task-by-id", "--task-id", str(task_id)
        )

        # Check what type of response we got
        is_string = isinstance(task_result, str)

        # Handle string responses (errors)
        string_is_not_found = is_string and "not found" in task_result.lower()
        string_is_other_error = is_string and not string_is_not_found

        # Validate we don't have unexpected errors
        assert not string_is_other_error, f"Unexpected query error: {task_result}"

        # Handle the "not found" case - assume task failed and was cleaned up
        string_is_not_found and print(
            f"Task {task_id} not found - may have been cleaned up after failure"
        )

        # Default values for when we don't have JSON
        task_dict = {}
        status_value = ""
        error_log_value = ""

        # Process JSON response only when we have one
        json_available = not is_string

        # Set values only when we have JSON data
        task_dict = json_available and task_result.get("task", {}) or {}
        status_value = json_available and task_dict.get("status", "") or ""
        error_log_value = json_available and task_dict.get("error_log", "") or ""

        # Check that task didn't complete successfully
        assert (
            status_value != "DONE"
        ), f"Task {task_id} executed successfully when it should have failed due to insufficient funds"

        # Check if task failed with correct error
        task_failed = status_value == "FAILED"
        correct_error = (
            "failed to deduct gas fee" in error_log_value
            or "insufficient funds" in error_log_value.lower()
        )
        valid_failure = not task_failed or correct_error
        assert (
            valid_failure
        ), f"Task failed but not due to insufficient funds: {error_log_value}"

        # Log the success
        task_failed and print(
            f"Task {task_id} failed as expected due to insufficient funds: {error_log_value}"
        )

        return string_is_not_found or task_failed

    # Poll until task status is updated to FAILED
    poll_until_condition(
        check_task_failed,
        timeout=TASK_SCHEDULED_DELAY
        + TASK_WAIT_TIMEOUT,  # Need to wait for scheduled time + execution
        error_message="Task did not fail as expected within timeout",
    )
    print("Successfully verified task execution fails with insufficient funds")
