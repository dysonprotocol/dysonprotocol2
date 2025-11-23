"""
Params query handler coverage tests.

Tests the Params query endpoint which retrieves current module parameters.
Covers success case with parameter validation.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
from deep_parse import deep_parse


def test_params_query(chainnet):
    """Test Params query returns current module parameters."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_params_query():
    # Query module parameters
    params_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryParamsRequest"
    })
    return {"params_result": params_result}
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
        "demo_params_query",
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
        "params_result" in demo_result
    ), f"Result missing 'params_result' key. Keys: {list(demo_result.keys())}"

    params_result = demo_result["params_result"]
    assert isinstance(params_result, dict), f"Params result should be dict, got {type(params_result)}"
    assert "params" in params_result, f"Params result missing 'params' key. Keys: {list(params_result.keys())}"

    params = params_result["params"]
    assert isinstance(params, dict), f"Params should be dict, got {type(params)}"

    # Verify expected parameter structure
    expected_keys = ["block_gas_limit", "expiry_limit", "max_scheduled_time", "clean_up_time", "max_subscription_duration", "min_stake_per_subscription"]
    for key in expected_keys:
        assert key in params, f"Params missing expected key '{key}'. Keys: {list(params.keys())}"
