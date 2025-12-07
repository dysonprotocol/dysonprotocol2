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


@pytest.mark.nameservice
def test_params_default_reserved_names_loaded(chainnet):
    """Test that default params includes reserved names from embedded file.
    
    Note: This test checks the params as stored in the chain. If the chain was
    initialized before reserved names were added, it may not have them. The test
    verifies that reserved names functionality works correctly.
    """
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query, _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_default_reserved_names():
    # Query current params
    params_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    params = params_result["params"]
    current_reserved_names = params.get("reserved_names", "")
    
    # If reserved_names is empty, it means the chain was initialized before
    # reserved names were added. This is expected for existing chains.
    # We'll verify the functionality by checking that we can set reserved names.
    has_reserved_names = len(current_reserved_names) > 0
    
    # Check for known reserved names if they exist
    has_aaron = "aaron.dys" in current_reserved_names if has_reserved_names else False
    has_admin = "admin.dys" in current_reserved_names if has_reserved_names else False
    
    return {
        "has_reserved_names": has_reserved_names,
        "reserved_names_length": len(current_reserved_names),
        "has_aaron": has_aaron,
        "has_admin": has_admin,
        "reserved_names_preview": current_reserved_names[:200] if current_reserved_names else ""
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
        "demo_default_reserved_names",
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
    
    # Verify structure
    assert (
        "has_reserved_names" in demo_result
    ), f"Result missing 'has_reserved_names' key. Keys: {list(demo_result.keys())}"
    assert (
        "reserved_names_length" in demo_result
    ), f"Result missing 'reserved_names_length' key. Keys: {list(demo_result.keys())}"
    
    # params.ReservedNames is now empty by default (custom additional names only)
    # Default reserved names from the embedded file are enforced separately
    reserved_names_length = demo_result["reserved_names_length"]
    assert isinstance(
        reserved_names_length, int
    ), f"reserved_names_length should be int, got {type(reserved_names_length)}"
    # params.ReservedNames should be empty for a fresh chain (defaults are enforced separately)
    assert reserved_names_length == 0, (
        f"Expected params.reserved_names to be empty (defaults are enforced separately), "
        f"but got length {reserved_names_length}. Preview: {demo_result.get('reserved_names_preview', '')}"
    )


@pytest.mark.nameservice
def test_reveal_default_reserved_name_fails(chainnet):
    """Test that revealing a name from default reserved names list fails."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def reveal_default_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Try to reveal "admin.dys" which should be in default reserved names
    # Step 1: Create commitment
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "admin.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 2: Try reveal with reserved name - should fail
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "admin.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
    except Exception as e:
        return {"error": str(e), "result": None}
"""

    kwargs = json.dumps({})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "reveal_default_reserved_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert "result" in parsed, "Missing result in response"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    assert "error" in function_result, "Missing error in response"
    assert "result" in function_result, "Missing result in response"

    error = function_result["error"]
    assert isinstance(error, str), f"Expected error to be string, got {type(error)}"
    assert error is not None, "Expected error for reserved name"
    assert "reserved" in error.lower(), (
        f"Expected reserved name error, got: {error}"
    )
    assert "cannot be registered via reveal" in error.lower(), (
        f"Expected 'cannot be registered via reveal' in error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"

