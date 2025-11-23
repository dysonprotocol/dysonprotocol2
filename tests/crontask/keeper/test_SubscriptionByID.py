"""
SubscriptionByID query handler coverage tests.

Tests the SubscriptionByID query endpoint which retrieves subscription information by ID.
Covers existing subscription and subscription not found cases.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
from deep_parse import deep_parse


def test_subscription_by_id_existing(chainnet):
    """Test SubscriptionByID query successfully returns information for an existing subscription."""
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

def demo_subscription_by_id_existing(gov_addr, alice_addr):
    # First fund the gov account from alice using governance authority
    fund_gov_msg = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": gov_addr,
        "amount": [{"denom": "udys", "amount": "1000"}]
    }

    # Use sudo to send funds from alice to gov (governance can execute any message)
    _sudo(fund_gov_msg)

    # Modify parameters to not require stake for testing
    update_params_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "block_gas_limit": "3000000",
            "expiry_limit": "86400",
            "max_scheduled_time": "86400",
            "clean_up_time": "86400",
            "max_subscription_duration": "24h0m0s",  # 24 hours
            "min_stake_per_subscription": {"denom": "udys", "amount": "0"}  # No stake required for testing
        }
    }

    # Update params (this should work with gov authority)
    _msg(update_params_msg)

    # Create a subscription using governance sudo to bypass fee requirements
    create_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateSubscription",
        "creator": gov_addr,
        "filter": '{"type": "message", "attributes": [{"key": "action", "value": "send"}]}',
        "script_address": gov_addr,
        "function": "test_function",
        "args": "[]",
        "kwargs": "{}",
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"}
    }

    # Use sudo to create subscription with governance authority
    create_result = _sudo(create_subscription_msg)

    # Extract subscription_id from sudo results
    results = create_result["results"]
    subscription_response = results[0]
    subscription_id = subscription_response["subscription_id"]

    # Query subscription by ID
    subscription_info_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionByIDRequest",
        "subscription_id": subscription_id
    })

    return {
        "create_sudo_result": create_result,
        "subscription_id": subscription_id,
        "subscription_info": subscription_info_result
    }
"""

    # Get alice address for funding
    alice_result = dysond("keys", "show", "alice")
    alice_addr = alice_result["address"]

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
        "demo_subscription_by_id_existing",
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
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "subscription_info" in demo_result
    ), f"Result missing 'subscription_info' key. Keys: {list(demo_result.keys())}"

    subscription_info = demo_result["subscription_info"]
    assert isinstance(
        subscription_info, dict
    ), f"Subscription info should be dict, got {type(subscription_info)}"
    assert (
        "subscription" in subscription_info
    ), f"Subscription info missing 'subscription' key. Keys: {list(subscription_info.keys())}"

    subscription = subscription_info["subscription"]
    assert isinstance(subscription, dict), f"Subscription should be dict, got {type(subscription)}"
    assert "subscription_id" in subscription, f"Subscription missing 'subscription_id' key. Keys: {list(subscription.keys())}"
    assert "creator" in subscription, f"Subscription missing 'creator' key. Keys: {list(subscription.keys())}"
    assert "status" in subscription, f"Subscription missing 'status' key. Keys: {list(subscription.keys())}"

    # Verify the subscription ID matches what we created
    assert (
        subscription["subscription_id"] == demo_result["subscription_id"]
    ), f"Subscription ID mismatch: expected {demo_result['subscription_id']}, got {subscription['subscription_id']}"

    # Verify creator address
    assert (
        subscription["creator"] == gov_addr
    ), f"Creator mismatch: expected {gov_addr}, got {subscription['creator']}"

    # Verify status is enabled
    assert (
        subscription["status"] == "enabled"
    ), f"Status mismatch: expected 'enabled', got {subscription['status']}"


def test_subscription_by_id_not_found(chainnet):
    """Test SubscriptionByID query returns NotFound error for non-existent subscription."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use a subscription ID that definitely doesn't exist (very high number)
    non_existent_subscription_id = 999999

    extra_code = f"""
from dys import _query

def demo_subscription_by_id_not_found():
    # Query subscription by ID for a non-existent subscription - should raise exception
    subscription_info_result = _query({{
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionByIDRequest",
        "subscription_id": {non_existent_subscription_id}
    }})
    return {{"success": True, "result": subscription_info_result}}
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
        "demo_subscription_by_id_not_found",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Expected script to fail for non-existent subscription, but it succeeded: {json.dumps(result, indent=2)}"

    exception = query_result.get("exception", {})
    assert (
        "DysQueryException" in exception.get("context", "")
    ), f"Expected DysQueryException, got: {json.dumps(exception, indent=2)}"

    error_msg = exception.get("msg", "")
    assert (
        "subscription not found" in error_msg
    ), f"Expected NotFound error for subscription ID 999999, got: {error_msg}"
