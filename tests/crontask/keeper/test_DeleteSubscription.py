"""
DeleteSubscription message handler coverage tests.

Tests the DeleteSubscription message handler which removes event-triggered subscriptions.
Covers success path, subscription not found, and unauthorized deletion.
All tests use stateless script query execution with _sudo calls.
"""

import json
from deep_parse import deep_parse


def test_delete_subscription_success(chainnet):
    """Test DeleteSubscription successfully removes an existing subscription."""
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

def demo_delete_subscription_success(gov_addr, alice_addr):
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

    # Verify subscription exists
    subscription_info_before = _query({
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionByIDRequest",
        "subscription_id": subscription_id
    })

    # Delete the subscription
    delete_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgDeleteSubscription",
        "creator": gov_addr,
        "subscription_id": subscription_id
    }

    delete_result = _sudo(delete_subscription_msg)

    # Try to query the subscription (should fail)
    try:
        subscription_info_after = _query({
            "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionByIDRequest",
            "subscription_id": subscription_id
        })
        subscription_deleted = False
    except:
        subscription_deleted = True

    return {
        "create_result": create_result,
        "subscription_id": subscription_id,
        "subscription_info_before": subscription_info_before,
        "delete_result": delete_result,
        "subscription_deleted": subscription_deleted
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
        "demo_delete_subscription_success",
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

    # Verify subscription was created
    assert "subscription_id" in demo_result, f"Result missing subscription_id, keys: {list(demo_result.keys())}"
    subscription_id = demo_result["subscription_id"]
    assert isinstance(subscription_id, str), f"Subscription ID should be string, got {type(subscription_id)}"

    # Verify subscription existed before deletion
    assert "subscription_info_before" in demo_result, f"Result missing subscription_info_before"
    subscription_info_before = demo_result["subscription_info_before"]
    assert "subscription" in subscription_info_before, f"Subscription info before missing subscription"
    assert subscription_info_before["subscription"]["subscription_id"] == subscription_id, f"Subscription ID mismatch before deletion"

    # Verify delete result
    assert "delete_result" in demo_result, f"Result missing delete_result"
    delete_result = demo_result["delete_result"]
    assert isinstance(delete_result, dict), f"Delete result should be dict, got {type(delete_result)}"
    assert "results" in delete_result, f"Delete result missing results"
    assert len(delete_result["results"]) == 1, f"Delete result should have 1 result"

    result_item = delete_result["results"][0]
    assert result_item["@type"] == "/dysonprotocol.crontask.v1.MsgDeleteSubscriptionResponse", f"Expected MsgDeleteSubscriptionResponse, got {result_item['@type']}"

    # Verify subscription was deleted
    assert demo_result["subscription_deleted"] == True, f"Subscription should be deleted, but subscription_deleted is {demo_result['subscription_deleted']}"


def test_delete_subscription_not_found(chainnet):
    """Test DeleteSubscription fails when subscription does not exist."""
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

def demo_delete_subscription_not_found(gov_addr):
    # Try to delete a non-existent subscription
    non_existent_subscription_id = 999999

    delete_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgDeleteSubscription",
        "creator": gov_addr,
        "subscription_id": non_existent_subscription_id
    }

    # This should fail with subscription not found error
    delete_result = _msg(delete_subscription_msg)  # Direct call since sudo doesn't help with not found
    return {"delete_result": delete_result}
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
        "demo_delete_subscription_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with subscription not found, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "not found" in error_msg_lower, f"Error should mention subscription not found, got: {error_msg}"


def test_delete_subscription_unauthorized(chainnet):
    """Test DeleteSubscription fails when creator doesn't match subscription creator."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use a different address for unauthorized deletion
    wrong_addr = "dys216vwht46aw58efaxx"

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_delete_subscription_unauthorized(gov_addr, alice_addr):
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

    # Create subscription with gov_addr as creator
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

    # Try to delete with wrong creator
    delete_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgDeleteSubscription",
        "creator": wrong_addr,
        "subscription_id": subscription_id
    }

    # This should fail with unauthorized error
    delete_result = _sudo(delete_subscription_msg)
    return {"create_result": create_result, "subscription_id": subscription_id, "delete_result": delete_result}
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "wrong_addr": wrong_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_delete_subscription_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with unauthorized deletion, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "unauthorized" in error_msg_lower, f"Error should mention unauthorized, got: {error_msg}"
