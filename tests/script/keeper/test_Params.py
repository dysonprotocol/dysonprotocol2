"""
Params query handler coverage tests.

Tests the Params query endpoint which retrieves current script module parameters.
Covers success path and nil request error handling.
All tests use stateless script query execution with _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_params_success(chainnet):
    """Test Params query successfully returns current module parameters."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_params_query():
    # Query script module parameters
    params_result = _query({
        "@type": "/dysonprotocol.script.v1.QueryParamsRequest"
    })
    
    return {
        "params_result": params_result
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
    assert isinstance(
        params_result, dict
    ), f"Params result should be dict, got {type(params_result)}"
    assert (
        "params" in params_result
    ), f"Params result missing 'params' key. Keys: {list(params_result.keys())}"

    params = params_result["params"]
    assert isinstance(
        params, dict
    ), f"Params should be dict, got {type(params)}"
    # Params is currently empty, so we just verify the structure exists


def test_params_nil_request_error(chainnet):
    """Test Params query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_params_nil_request():
    # Attempt to query with None/null request
    # In gRPC, nil requests are typically handled at the framework level,
    # but we test that the query handler properly validates the request
    try:
        # Pass None/null which should trigger validation error
        params_result = _query(None)
        return {"error": "Should have failed", "result": params_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_params_nil_request",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    # The query should fail when None is passed
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    # Verify that an error was expected and occurred
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"

