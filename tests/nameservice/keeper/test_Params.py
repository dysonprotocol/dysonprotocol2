"""
Params query handler coverage tests.

Tests the Params query endpoint which retrieves current nameservice module parameters.
Covers success path (returns all parameter fields) and nil request error handling.
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
    # Query nameservice module parameters
    params_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
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

    # Verify all expected parameter fields are present
    expected_fields = [
        "mint_fee_per_coin",
        "min_bid_timeout_class",
        "max_bid_timeout_class",
        "min_reject_bid_valuation_fee_percent",
        "max_reject_bid_valuation_fee_percent",
        "min_minimum_bid_percent_increase",
        "max_minimum_bid_percent_increase",
        "min_valuation_fee_pct",
        "max_valuation_fee_pct",
        "min_valuation_period",
        "max_valuation_period",
    ]

    for field in expected_fields:
        assert (
            field in params
        ), f"Params missing expected field '{field}'. Available fields: {list(params.keys())}"

    # Verify mint_fee_per_coin is a string
    assert isinstance(
        params["mint_fee_per_coin"], str
    ), f"mint_fee_per_coin should be string, got {type(params['mint_fee_per_coin'])}"

    # Verify fee percent fields are strings
    percent_fields = [
        "min_reject_bid_valuation_fee_percent",
        "max_reject_bid_valuation_fee_percent",
        "min_minimum_bid_percent_increase",
        "max_minimum_bid_percent_increase",
        "min_valuation_fee_pct",
        "max_valuation_fee_pct",
    ]
    for field in percent_fields:
        assert isinstance(
            params[field], str
        ), f"{field} should be string, got {type(params[field])}"


def test_params_nil_request(chainnet):
    """Test Params query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_params_nil_request():
    # Attempt to query with None/null request
    try:
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
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"
    error_msg = demo_result.get("error", "")
    # The error occurs at the query framework level (missing @type field) before reaching the handler
    error_lower = error_msg.lower()
    assert "@type" in error_lower, (
        f"Error message should mention '@type'. Got: {error_msg}"
    )

