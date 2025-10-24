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
    assert (
        result["result"] is not None
    ), f"Result is None: {json.dumps(result, indent=2)}"

    outer = json.loads(result["result"])  # contains keys: exception, result, etc.

    # Fail fast with full context if the script raised
    assert outer["exception"] is None, (
        f"Script execution failed with exception:\n"
        f"{json.dumps(outer['exception'], indent=2)}\n"
        f"Args: {args_json[:500]}"
    )

    assert outer["result"] is not None, (
        f"Script returned None result (no exception but no result):\n"
        f"Full output: {json.dumps(outer, indent=2)[:1000]}"
    )

    return outer["result"]
