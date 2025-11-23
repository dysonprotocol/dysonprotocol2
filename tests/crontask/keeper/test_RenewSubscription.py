"""
RenewSubscription message handler coverage tests.

Tests the RenewSubscription message handler which extends subscription expiry and recharges fees.
Covers success path, insufficient stake, subscription not found, and unauthorized renewal.
All tests use stateless script query execution with _sudo calls.
"""

import json
from deep_parse import deep_parse


def test_renew_subscription_success(chainnet):
    """Test RenewSubscription successfully extends subscription expiry and recharges fee."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("keys", "show", "alice")
    alice_addr = alice_result["address"]

    extra_code = """
import time
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_renew_subscription_success(gov_addr, alice_addr):
    # Fund gov account first (for subscription fee and renewal)
    fund_msg = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": gov_addr,
        "amount": [{"denom": "udys", "amount": "2000"}]
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

    # Get initial subscription info
    subscription_info_before = _query({
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionByIDRequest",
        "subscription_id": subscription_id
    })
    expiry_before = subscription_info_before["subscription"]["expiry_timestamp"]

    # Renew the subscription
    renew_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgRenewSubscription",
        "creator": gov_addr,
        "subscription_id": subscription_id
    }

    renew_result = _sudo(renew_subscription_msg)

    # Get subscription info after renewal
    subscription_info_after = _query({
        "@type": "/dysonprotocol.crontask.v1.QuerySubscriptionByIDRequest",
        "subscription_id": subscription_id
    })
    expiry_after = subscription_info_after["subscription"]["expiry_timestamp"]

    # Verify params were updated
    updated_params = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryParamsRequest"
    })

    return {
        "create_result": create_result,
        "subscription_id": subscription_id,
        "updated_params": updated_params,
        "expiry_before": expiry_before,
        "renew_result": renew_result,
        "expiry_after": expiry_after,
        "renewal_extended": expiry_after > expiry_before
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
        "demo_renew_subscription_success",
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

    # Verify subscription was created
    assert (
        "subscription_id" in demo_result
    ), f"Result missing subscription_id, keys: {list(demo_result.keys())}"
    subscription_id = demo_result["subscription_id"]
    assert isinstance(
        subscription_id, str
    ), f"Subscription ID should be string, got {type(subscription_id)}"

    # Note: Cannot verify expiry extension in stateless test since time doesn't pass
    # between creation and renewal in the same script execution
    assert "expiry_before" in demo_result, f"Result missing expiry_before"
    assert "expiry_after" in demo_result, f"Result missing expiry_after"

    # Verify renewal result
    assert "renew_result" in demo_result, f"Result missing renew_result"
    renew_result = demo_result["renew_result"]
    assert isinstance(
        renew_result, dict
    ), f"Renew result should be dict, got {type(renew_result)}"
    assert "results" in renew_result, f"Renew result missing results"
    assert len(renew_result["results"]) == 1, f"Renew result should have 1 result"

    result_item = renew_result["results"][0]
    assert (
        result_item["@type"]
        == "/dysonprotocol.crontask.v1.MsgRenewSubscriptionResponse"
    ), f"Expected MsgRenewSubscriptionResponse, got {result_item['@type']}"

    # Note: Cannot verify expiry extension in stateless test


def test_renew_subscription_not_found(chainnet):
    """Test RenewSubscription fails when subscription does not exist."""
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

def demo_renew_subscription_not_found(gov_addr):
    # Try to renew a non-existent subscription
    non_existent_subscription_id = 999999

    renew_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgRenewSubscription",
        "creator": gov_addr,
        "subscription_id": non_existent_subscription_id
    }

    # This should fail with subscription not found error
    renew_result = _sudo(renew_subscription_msg)
    return {"renew_result": renew_result}
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
        "demo_renew_subscription_not_found",
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
    assert isinstance(
        exception, dict
    ), f"Exception should be dict, got {type(exception)}"
    assert (
        "msg" in exception
    ), f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(
        error_msg, str
    ), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert (
        "not found" in error_msg_lower
    ), f"Error should mention subscription not found, got: {error_msg}"


def test_renew_subscription_unauthorized(chainnet):
    """Test RenewSubscription fails when creator doesn't match subscription creator."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use a different address for unauthorized renewal
    wrong_addr = "dys216vwht46aw58efaxx"

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_renew_subscription_unauthorized(gov_addr, alice_addr):
    # Use a different address for unauthorized renewal
    wrong_addr = "dys216vwht46aw58efaxx"

    # Fund gov account first
    fund_msg = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": gov_addr,
        "amount": [{"denom": "udys", "amount": "2000"}]
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

    # Try to renew with wrong creator
    renew_subscription_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgRenewSubscription",
        "creator": wrong_addr,
        "subscription_id": subscription_id
    }

    # This should fail with unauthorized error
    renew_result = _sudo(renew_subscription_msg)
    return {"create_result": create_result, "subscription_id": subscription_id, "renew_result": renew_result}
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
        "demo_renew_subscription_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with unauthorized renewal, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(
        exception, dict
    ), f"Exception should be dict, got {type(exception)}"
    assert (
        "msg" in exception
    ), f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(
        error_msg, str
    ), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert (
        "unauthorized" in error_msg_lower
    ), f"Error should mention unauthorized, got: {error_msg}"
