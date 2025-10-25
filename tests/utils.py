"""
Utility functions for testing blockchain operations.
"""

import time
from typing import Callable, TypeVar

T = TypeVar("T")


# This is the only place it is allowed to use time.sleep
def poll_until_condition(
    check_func: Callable[[], T],
    timeout: int = 30,
    poll_interval: float = 0.2,  # any faster will DOS the node
    error_message: str = "Condition not met within timeout",
) -> T:
    """
    Poll until a condition function returns a truthy value or timeout is reached.

    Args:
        check_func: Function that returns a truthy value when the condition is met
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        check_interval: Alias for poll_interval (backward compatibility)
        error_message: Message to print if condition not met

    Returns:
        The truthy value returned by check_func if condition met within timeout

    Raises:
        Exception: If condition not met within timeout
    """
    start_time = time.time()
    attempts = 0

    while time.time() - start_time < timeout:
        attempts += 1

        if return_value := check_func():
            return return_value

        if attempts % 10 == 0:
            elapsed = time.time() - start_time
            print(
                f"Waiting for condition... ({attempts} attempts, {elapsed:.2f}s elapsed)"
            )

        time.sleep(poll_interval)

    raise Exception(f"TIMEOUT: {error_message} after {timeout}s")


def extract_script_result(wait_tx_json):
    """Parse EventExecScript.response and return the inner script result dict."""
    events = wait_tx_json.get("events", [])
    for e in events:
        if e.get("type") == "dysonprotocol.script.v1.EventExecScript":
            for a in e.get("attributes", []):
                if a.get("key") == "response":
                    data = a.get("value", "{}")
                    outer = __import__("json").loads(data)
                    inner = __import__("json").loads(outer.get("result", "{}"))
                    return inner.get("result")
    raise AssertionError(
        "EventExecScript response not found. Full events: "
        + __import__("json").dumps(events, indent=2)
    )
