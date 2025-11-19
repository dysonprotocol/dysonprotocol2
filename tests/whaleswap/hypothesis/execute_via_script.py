import json


def execute_via_script(dysond, executor_script_path, gov_addr, function_name, args):
    """
    Execute a dyslang function via dysond script run and return parsed result.

    Uses gov address as both script and executor with --extra-code-path.
    """
    args_json = json.dumps(args)

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        function_name,
        "--args",
        args_json,
        "--extra-code-path",
        str(executor_script_path),
        "-o",
        "json",
    )

    # Expect dysond JSON dict with nested JSON string under "result"
    assert isinstance(result, dict), f"Expected dict result, got: {str(result)}"
    assert (
        "result" in result
    ), f"No 'result' key in response: {json.dumps(result, indent=2)}"

    # Parse outer result - may be None if script raised exception
    if result["result"] is not None:
        outer = json.loads(result["result"])
    else:
        # If result is None, there should be an exception in the response
        # Try to extract it from the result dict itself
        outer = {"exception": result.get("exception"), "result": None}

    # Check if the script raised an exception
    if outer.get("exception") is not None:
        exception_msg = outer["exception"].get("msg", "")

        # Skip expected edge case errors that are valid system rejections
        # These indicate the system correctly validates and rejects invalid operations
        expected_errors = [
            "swap output too small",  # Position too small for AMM to execute
            "borrow cap exceeded",  # Borrow exceeds available pool capacity
            "borrow would exceed cap",  # Alternative phrasing of borrow cap error
            "insufficient collateral",  # Collateral ratio below minimum
            "debit exceeds cap",  # Trader's net debit exceeds MaxInput caps
        ]

        for expected_error in expected_errors:
            if expected_error in exception_msg:
                from hypothesis import assume

                assume(False)  # Tell Hypothesis to skip this example

        # For any other exception, fail with full context
        assert False, (
            f"Script execution failed with exception:\n"
            f"{json.dumps(outer['exception'], indent=2)}\n"
            f"Args: {args_json[:500]}"
        )

    assert outer.get("result") is not None, (
        f"Script returned None result (no exception but no result):\n"
        f"Full output: {json.dumps(outer, indent=2)[:1000]}"
    )

    return outer["result"]
