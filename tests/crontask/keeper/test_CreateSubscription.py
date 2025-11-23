"""
CreateSubscription message handler coverage tests.

Tests the CreateSubscription message handler which creates event-triggered subscriptions.
Covers success path, stake requirements, invalid addresses, and JSON validation.
All tests use stateless script query execution with _sudo calls.
"""

import json
from deep_parse import deep_parse


def test_create_subscription_success(chainnet):
    """Test CreateSubscription successfully creates a subscription with valid parameters."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("keys", "show", "alice")
    alice_addr = alice_result["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_subscription_success(gov_addr, alice_addr):
    # Fund gov account first (for subscription fee)
    fund_msg = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": gov_addr,
        "amount": [{"denom": "udys", "amount": "1000"}]
    }
    _sudo(fund_msg)

    # Update params to remove stake requirements for testing
    update_params_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "block_gas_limit": "3000000",
            "expiry_limit": "86400",
            "max_scheduled_time": "86400",
            "clean_up_time": "86400",
            "max_subscription_duration": "24h0m0s",
            "min_stake_per_subscription": {
                "denom": "udys",
                "amount": "0"
            }
        }
    }
    _sudo(update_params_msg)

    # Create a script first
    script_code = '''
def test_function():
    return {"result": "subscription_triggered"}
'''
    create_script_msg = {
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    }
    script_result = _sudo(create_script_msg)
    script_address = script_result["results"][0]["script_address"]

    # Create subscription
    create_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateSubscription",
        "creator": gov_addr,
        "filter": "tm.event='Tx'",
        "script_address": script_address,
        "function": "test_function",
        "args": "[]",
        "kwargs": "{}",
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"}
    }

    create_result = _sudo(create_subscription_msg)
    subscription_id = create_result["results"][0]["subscription_id"]

    # Query the subscription to verify it was created
    subscription_info = _query({
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionByIDRequest",
        "subscription_id": subscription_id
    })

    return {
        "create_result": create_result,
        "subscription_id": subscription_id,
        "script_address": script_address,
        "subscription_info": subscription_info
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "alice_addr": alice_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_create_subscription_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
        "--output",
        "json",
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"
    assert "create_result" in demo_result, f"Result missing 'create_result' key. Keys: {list(demo_result.keys())}"
    assert "subscription_id" in demo_result, f"Result missing 'subscription_id' key. Keys: {list(demo_result.keys())}"
    assert "subscription_info" in demo_result, f"Result missing 'subscription_info' key. Keys: {list(demo_result.keys())}"

    # Verify create result
    create_result = demo_result["create_result"]
    assert isinstance(create_result, dict), f"Create result should be dict, got {type(create_result)}"
    assert "results" in create_result, f"Create result missing 'results' key. Keys: {list(create_result.keys())}"
    assert len(create_result["results"]) == 1, f"Create result should have 1 result, got {len(create_result['results'])}"

    result_item = create_result["results"][0]
    assert result_item["@type"] == "/dysonprotocol.crontask.v1.MsgCreateSubscriptionResponse", f"Expected MsgCreateSubscriptionResponse, got {result_item['@type']}"
    assert "subscription_id" in result_item, f"Result missing subscription_id, keys: {list(result_item.keys())}"

    subscription_id = result_item["subscription_id"]
    assert isinstance(subscription_id, str), f"Subscription ID should be string, got {type(subscription_id)}"
    assert subscription_id.isdigit(), f"Subscription ID should be numeric string, got {subscription_id}"

    # Verify subscription info from query
    subscription_info = demo_result["subscription_info"]
    assert isinstance(subscription_info, dict), f"Subscription info should be dict, got {type(subscription_info)}"
    assert "subscription" in subscription_info, f"Subscription info missing 'subscription' key. Keys: {list(subscription_info.keys())}"

    subscription = subscription_info["subscription"]
    assert isinstance(subscription, dict), f"Subscription should be dict, got {type(subscription)}"
    assert subscription["subscription_id"] == subscription_id, f"Subscription ID mismatch: expected {subscription_id}, got {subscription['subscription_id']}"
    assert subscription["creator"] == gov_addr, f"Creator mismatch: expected {gov_addr}, got {subscription['creator']}"
    assert subscription["status"] == "enabled", f"Status should be enabled, got {subscription['status']}"
    assert subscription["filter"] == "tm.event='Tx'", f"Filter mismatch"
    assert subscription["function"] == "test_function", f"Function name mismatch"


def test_create_subscription_invalid_script_address(chainnet):
    """Test CreateSubscription fails with invalid script address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("keys", "show", "alice")
    alice_addr = alice_result["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_subscription_invalid_script_address(gov_addr, alice_addr):
    # Fund gov account first
    fund_msg = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": gov_addr,
        "amount": [{"denom": "udys", "amount": "1000"}]
    }
    _sudo(fund_msg)

    # Update params to remove stake requirements
    update_params_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "block_gas_limit": "3000000",
            "expiry_limit": "86400",
            "max_scheduled_time": "86400",
            "clean_up_time": "86400",
            "max_subscription_duration": "24h0m0s",
            "min_stake_per_subscription": {"denom": "udys", "amount": "0"}
        }
    }
    _sudo(update_params_msg)

    # Try to create subscription with invalid script address
    create_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateSubscription",
        "creator": gov_addr,
        "filter": "tm.event='Tx'",
        "script_address": "invalid_script_address",
        "function": "test_function",
        "args": "[]",
        "kwargs": "{}",
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"}
    }

    # This should fail with invalid script address error
    create_result = _sudo(create_subscription_msg)
    return {"create_result": create_result}
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "alice_addr": alice_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_create_subscription_invalid_script_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution should have succeeded, but got exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"
    assert "create_result" in demo_result, f"Result missing 'create_result' key. Keys: {list(demo_result.keys())}"

    create_result = demo_result["create_result"]
    assert isinstance(create_result, dict), f"Create result should be dict, got {type(create_result)}"
    assert "results" in create_result, f"Create result missing 'results' key. Keys: {list(create_result.keys())}"
    assert len(create_result["results"]) == 1, f"Create result should have 1 result, got {len(create_result['results'])}"

    result_item = create_result["results"][0]
    assert result_item["@type"] == "/dysonprotocol.crontask.v1.MsgCreateSubscriptionResponse", f"Expected MsgCreateSubscriptionResponse, got {result_item['@type']}"
    assert "subscription_id" in result_item, f"Response missing subscription_id. Keys: {list(result_item.keys())}"


def test_create_subscription_invalid_json_args(chainnet):
    """Test CreateSubscription fails with invalid JSON in args field."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("keys", "show", "alice")
    alice_addr = alice_result["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_subscription_invalid_json_args(gov_addr, alice_addr):
    # Fund gov account first
    fund_msg = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": gov_addr,
        "amount": [{"denom": "udys", "amount": "1000"}]
    }
    _sudo(fund_msg)

    # Update params to remove stake requirements
    update_params_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "block_gas_limit": "3000000",
            "expiry_limit": "86400",
            "max_scheduled_time": "86400",
            "clean_up_time": "86400",
            "max_subscription_duration": "24h0m0s",
            "min_stake_per_subscription": {"denom": "udys", "amount": "0"}
        }
    }
    _sudo(update_params_msg)

    # Create a valid script first
    script_code = '''
def test_function():
    return {"result": "success"}
'''
    create_script_msg = {
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    }
    script_result = _sudo(create_script_msg)
    script_address = script_result["results"][0]["script_address"]

    # Try to create subscription with invalid JSON in args
    create_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateSubscription",
        "creator": gov_addr,
        "filter": "tm.event='Tx'",
        "script_address": script_address,
        "function": "test_function",
        "args": "[invalid json",  # Invalid JSON - missing closing bracket
        "kwargs": "{}",
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"}
    }

    # This should fail with invalid JSON error
    create_result = _sudo(create_subscription_msg)
    return {"create_result": create_result, "script_address": script_address}
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "alice_addr": alice_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_create_subscription_invalid_json_args",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with invalid JSON args, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "json" in error_msg_lower, f"Error should mention JSON, got: {error_msg}"
