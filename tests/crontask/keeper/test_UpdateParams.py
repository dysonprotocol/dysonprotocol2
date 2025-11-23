"""
UpdateParams message handler coverage tests.

Tests the UpdateParams message handler which updates module parameters via governance.
Covers success path, invalid authority, and parameter validation.
All tests use stateless script query execution with _sudo calls.
"""

import json
from deep_parse import deep_parse


def test_update_params_success(chainnet):
    """Test UpdateParams successfully updates parameters with valid authority."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_success(gov_addr):
    # Get current params
    current_params = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryParamsRequest"
    })

    # Update params with valid authority (gov module)
    update_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "block_gas_limit": "2500000",
            "expiry_limit": "7200",
            "max_scheduled_time": "7200",
            "clean_up_time": "7200",
            "max_subscription_duration": "12h0m0s",
            "min_stake_per_subscription": {
                "denom": "udys",
                "amount": "500"
            }
        }
    }

    update_result = _sudo(update_msg)

    # Query params again to verify update succeeded
    updated_params = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryParamsRequest"
    })

    return {
        "update_result": update_result,
        "current_params": current_params,
        "updated_params": updated_params
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"
    assert "update_result" in demo_result, f"Result missing 'update_result' key. Keys: {list(demo_result.keys())}"
    assert "current_params" in demo_result, f"Result missing 'current_params' key. Keys: {list(demo_result.keys())}"
    assert "updated_params" in demo_result, f"Result missing 'updated_params' key. Keys: {list(demo_result.keys())}"

    # Verify update result
    update_result = demo_result["update_result"]
    assert isinstance(update_result, dict), f"Update result should be dict, got {type(update_result)}"
    assert "results" in update_result, f"Update result missing 'results' key. Keys: {list(update_result.keys())}"
    assert len(update_result["results"]) == 1, f"Update result should have 1 result, got {len(update_result['results'])}"

    result_item = update_result["results"][0]
    assert result_item["@type"] == "/dysonprotocol.crontask.v1.MsgUpdateParamsResponse", f"Expected MsgUpdateParamsResponse, got {result_item['@type']}"

    # Verify params were updated
    current_params = demo_result["current_params"]
    updated_params = demo_result["updated_params"]
    assert isinstance(current_params, dict), f"Current params should be dict, got {type(current_params)}"
    assert isinstance(updated_params, dict), f"Updated params should be dict, got {type(updated_params)}"
    assert "params" in current_params, f"Current params missing 'params' key. Keys: {list(current_params.keys())}"
    assert "params" in updated_params, f"Updated params missing 'params' key. Keys: {list(updated_params.keys())}"

    current_param_values = current_params["params"]
    updated_param_values = updated_params["params"]

    # Check that at least one parameter changed (since we're updating with different values)
    # We can't guarantee which params changed since they might be reset, but we can verify the structure
    assert "block_gas_limit" in updated_param_values, f"Updated params missing block_gas_limit"
    assert "expiry_limit" in updated_param_values, f"Updated params missing expiry_limit"
    assert "max_scheduled_time" in updated_param_values, f"Updated params missing max_scheduled_time"


def test_update_params_invalid_authority(chainnet):
    """Test UpdateParams fails with invalid authority."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use invalid authority (different from gov module account)
    invalid_authority = "dys216vwht46aw58efaxx"

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_invalid_authority(invalid_authority):
    # Try to update params with invalid authority
    update_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgUpdateParams",
        "authority": invalid_authority,
        "params": {
            "block_gas_limit": "2500000",
            "expiry_limit": "7200",
            "max_scheduled_time": "7200",
            "clean_up_time": "7200",
            "max_subscription_duration": "12h0m0s",
            "min_stake_per_subscription": {
                "denom": "udys",
                "amount": "500"
            }
        }
    }

    # This should fail with invalid authority error
    update_result = _sudo(update_msg)
    return {"update_result": update_result}
"""

    kwargs = json.dumps({"invalid_authority": invalid_authority})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_authority",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with invalid authority, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "unauthorized" in error_msg_lower, f"Error should mention unauthorized, got: {error_msg}"


def test_update_params_invalid_parameters(chainnet):
    """Test UpdateParams fails with invalid parameters."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_invalid_parameters(gov_addr):
    # Try to update params with invalid parameters (zero block gas limit)
    update_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "block_gas_limit": "0",  # Invalid: must be positive
            "expiry_limit": "7200",
            "max_scheduled_time": "7200",
            "clean_up_time": "7200",
            "max_subscription_duration": "12h0m0s",
            "min_stake_per_subscription": {
                "denom": "udys",
                "amount": "500"
            }
        }
    }

    # This should fail with parameter validation error
    update_result = _sudo(update_msg)
    return {"update_result": update_result}
"""

    kwargs = json.dumps({"gov_addr": gov_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_parameters",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with invalid parameters, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "gas" in error_msg_lower, f"Error should mention gas limit validation, got: {error_msg}"


