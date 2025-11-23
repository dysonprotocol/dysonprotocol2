"""
SubscriptionsAll query handler coverage tests.

Tests the SubscriptionsAll query endpoint which retrieves all subscriptions ordered by ID.
Covers subscriptions exist (basic structure validation) and query response format.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
from deep_parse import deep_parse


def test_subscriptions_all_basic_structure(chainnet):
    """Test SubscriptionsAll query returns proper response structure."""
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

def demo_subscriptions_all_basic(gov_addr, alice_addr):
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
            "max_subscription_duration": "24h0m0s",
            "min_stake_per_subscription": {"denom": "udys", "amount": "0"}
        }
    }

    # Update params
    _msg(update_params_msg)

    # Create a subscription
    create_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateSubscription",
        "creator": gov_addr,
        "filter": '{"type": "message", "attributes": [{"key": "action", "value": "test_all"}]}',
        "script_address": gov_addr,
        "function": "test_function_all",
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

    # Query all subscriptions
    subscriptions_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionsAllRequest"
    })

    return {
        "create_result": create_result,
        "subscription_id": subscription_id,
        "subscriptions_result": subscriptions_result
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
        "demo_subscriptions_all_basic",
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
        "subscriptions_result" in demo_result
    ), f"Result missing 'subscriptions_result' key. Keys: {list(demo_result.keys())}"

    subscriptions_result = demo_result["subscriptions_result"]
    assert isinstance(
        subscriptions_result, dict
    ), f"Subscriptions result should be dict, got {type(subscriptions_result)}"
    assert (
        "subscriptions" in subscriptions_result
    ), f"Subscriptions result missing 'subscriptions' key. Keys: {list(subscriptions_result.keys())}"

    subscriptions = subscriptions_result["subscriptions"]
    assert isinstance(subscriptions, list), f"Subscriptions should be list, got {type(subscriptions)}"
    assert len(subscriptions) >= 1, f"Expected at least 1 subscription, got {len(subscriptions)}"

    # Check that our created subscription is in the results
    subscription_ids = [
        str(subscription["subscription_id"])
        for subscription in subscriptions
        if isinstance(subscription, dict) and "subscription_id" in subscription
    ]
    expected_subscription_id = str(demo_result["subscription_id"])
    assert (
        expected_subscription_id in subscription_ids
    ), f"Created subscription {expected_subscription_id} not found in results: {subscription_ids}"

    # Verify subscription structure
    for subscription in subscriptions:
        assert isinstance(subscription, dict), f"Subscription should be dict, got {type(subscription)}"
        assert (
            "subscription_id" in subscription
        ), f"Subscription missing 'subscription_id' key. Keys: {list(subscription.keys())}"
        assert (
            "creator" in subscription
        ), f"Subscription missing 'creator' key. Keys: {list(subscription.keys())}"
        assert "status" in subscription, f"Subscription missing 'status' key. Keys: {list(subscription.keys())}"


def test_subscriptions_all_empty(chainnet):
    """Test SubscriptionsAll query returns empty results when no subscriptions exist."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_subscriptions_all_empty():
    # Query all subscriptions (should be empty initially)
    subscriptions_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionsAllRequest"
    })

    return {"subscriptions_result": subscriptions_result}
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
        "demo_subscriptions_all_empty",
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
        "subscriptions_result" in demo_result
    ), f"Result missing 'subscriptions_result' key. Keys: {list(demo_result.keys())}"

    subscriptions_result = demo_result["subscriptions_result"]
    assert isinstance(
        subscriptions_result, dict
    ), f"Subscriptions result should be dict, got {type(subscriptions_result)}"
    assert (
        "subscriptions" in subscriptions_result
    ), f"Subscriptions result missing 'subscriptions' key. Keys: {list(subscriptions_result.keys())}"

    subscriptions = subscriptions_result["subscriptions"]
    assert isinstance(subscriptions, list), f"Subscriptions should be list, got {type(subscriptions)}"
    assert len(subscriptions) == 0, f"Expected no subscriptions, got {len(subscriptions)}: {subscriptions}"
