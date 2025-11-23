"""
SubscriptionsByCreator query handler coverage tests.

Tests the SubscriptionsByCreator query endpoint which retrieves subscriptions for a specific creator.
Covers subscriptions exist (paginated) and no subscriptions found cases.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
from deep_parse import deep_parse


def test_subscriptions_by_creator_existing(chainnet):
    """Test SubscriptionsByCreator query successfully returns subscriptions for a creator with existing subscriptions."""
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

def demo_subscriptions_by_creator_existing(gov_addr, alice_addr):
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

    # Create multiple subscriptions using the same creator address
    subscriptions_data = []

    for i in range(2):
        create_subscription_msg = {
            "@type": "/dysonprotocol.crontask.v1.MsgCreateSubscription",
            "creator": gov_addr,
            "filter": f'{{"type": "message", "attributes": [{{"key": "action", "value": "test{i}"}}]}}',
            "script_address": gov_addr,
            "function": f"test_function_{i}",
            "args": "[]",
            "kwargs": "{}",
            "task_gas_limit": 200000,
            "task_gas_fee": {"denom": "udys", "amount": str(i + 1)}
        }

        # Use sudo to create subscription with governance authority
        create_result = _sudo(create_subscription_msg)

        # Extract subscription_id from sudo results
        results = create_result["results"]
        subscription_response = results[0]
        subscription_id = subscription_response["subscription_id"]

        subscriptions_data.append({
            "subscription_id": subscription_id,
            "function": f"test_function_{i}",
            "gas_fee": i + 1
        })

    # Query subscriptions by creator
    subscriptions_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionsByCreatorRequest",
        "creator": gov_addr
    })

    return {
        "created_subscriptions": subscriptions_data,
        "subscriptions_query": subscriptions_result
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
        "demo_subscriptions_by_creator_existing",
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
        "subscriptions_query" in demo_result
    ), f"Result missing 'subscriptions_query' key. Keys: {list(demo_result.keys())}"

    subscriptions_query = demo_result["subscriptions_query"]
    assert isinstance(
        subscriptions_query, dict
    ), f"Subscriptions query should be dict, got {type(subscriptions_query)}"
    assert (
        "subscriptions" in subscriptions_query
    ), f"Subscriptions query missing 'subscriptions' key. Keys: {list(subscriptions_query.keys())}"

    subscriptions = subscriptions_query["subscriptions"]
    assert isinstance(
        subscriptions, list
    ), f"Subscriptions should be list, got {type(subscriptions)}"
    assert (
        len(subscriptions) >= 2
    ), f"Expected at least 2 subscriptions, got {len(subscriptions)}"

    # Verify each subscription has the correct creator
    created_subscription_ids = [
        str(sub_data["subscription_id"])
        for sub_data in demo_result["created_subscriptions"]
    ]
    for subscription in subscriptions:
        assert isinstance(
            subscription, dict
        ), f"Subscription should be dict, got {type(subscription)}"
        assert (
            "subscription_id" in subscription
        ), f"Subscription missing 'subscription_id' key. Keys: {list(subscription.keys())}"
        assert (
            "creator" in subscription
        ), f"Subscription missing 'creator' key. Keys: {list(subscription.keys())}"
        assert (
            subscription["creator"] == gov_addr
        ), f"Creator mismatch: expected {gov_addr}, got {subscription['creator']}"

        # All subscriptions should be enabled
        assert (
            "status" in subscription
        ), f"Subscription missing 'status' key. Keys: {list(subscription.keys())}"
        assert (
            subscription["status"] == "enabled"
        ), f"Status mismatch: expected 'enabled', got {subscription['status']}"


def test_subscriptions_by_creator_no_subscriptions(chainnet):
    """Test SubscriptionsByCreator query returns empty results for creator with no subscriptions."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate a deterministic valid bech32 address that does not have any subscriptions
    bytes_to_addr_result = dysond(
        "query",
        "auth",
        "address-bytes-to-string",
        "0x999999",
        "-o",
        "json",
    )
    random_addr = bytes_to_addr_result["address_string"]
    assert isinstance(
        random_addr, str
    ), f"Address string should be str. Got: {type(random_addr)}"
    assert (
        len(random_addr) > 0
    ), f"Failed to convert bytes to address: {bytes_to_addr_result}"

    extra_code = f"""
from dys import _query

def demo_subscriptions_by_creator_no_subscriptions(random_addr):
    # Query subscriptions by creator for an address with no subscriptions
    subscriptions_result = _query({{
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionsByCreatorRequest",
        "creator": random_addr
    }})

    return {{
        "query_result": subscriptions_result
    }}
"""

    kwargs = json.dumps({"random_addr": random_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_subscriptions_by_creator_no_subscriptions",
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
        "query_result" in demo_result
    ), f"Result missing 'query_result' key. Keys: {list(demo_result.keys())}"

    query_result_data = demo_result["query_result"]
    assert isinstance(
        query_result_data, dict
    ), f"Query result should be dict, got {type(query_result_data)}"
    assert (
        "subscriptions" in query_result_data
    ), f"Query result missing 'subscriptions' key. Keys: {list(query_result_data.keys())}"

    subscriptions = query_result_data["subscriptions"]
    assert isinstance(
        subscriptions, list
    ), f"Subscriptions should be list, got {type(subscriptions)}"
    assert (
        len(subscriptions) == 0
    ), f"Expected no subscriptions, got {len(subscriptions)}: {subscriptions}"
