"""
DeleteTask message handler coverage tests.

Tests the DeleteTask message handler which removes scheduled tasks.
Covers success path, task not found, and unauthorized deletion.
All tests use stateless script query execution with _sudo calls.
"""

import json
from deep_parse import deep_parse


def test_delete_task_success(chainnet):
    """Test DeleteTask successfully removes an existing task."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
import time
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_delete_task_success(gov_addr):
    # First create a task
    current_time = int(time.time())
    create_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": gov_addr,
        "scheduled_timestamp": str(current_time + 60),
        "expiry_timestamp": str(current_time + 3600),
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"},
        "msgs": [{
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": gov_addr,
            "to_address": gov_addr,
            "amount": [{"denom": "udys", "amount": "1"}]
        }]
    }

    create_result = _sudo(create_task_msg)
    task_id = create_result["results"][0]["task_id"]

    # Verify task exists
    task_info_before = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryTaskByIDRequest",
        "task_id": task_id
    })

    # Delete the task
    delete_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgDeleteTask",
        "creator": gov_addr,
        "task_id": task_id
    }

    delete_result = _sudo(delete_task_msg)

    # Try to query the task (should fail)
    try:
        task_info_after = _query({
            "@type": "/dysonprotocol.crontask.v1.QueryTaskByIDRequest",
            "task_id": task_id
        })
        task_deleted = False
    except:
        task_deleted = True

    return {
        "create_result": create_result,
        "task_id": task_id,
        "task_info_before": task_info_before,
        "delete_result": delete_result,
        "task_deleted": task_deleted
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
        "demo_delete_task_success",
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

    # Verify task was created
    assert "task_id" in demo_result, f"Result missing task_id, keys: {list(demo_result.keys())}"
    task_id = demo_result["task_id"]
    assert isinstance(task_id, str), f"Task ID should be string, got {type(task_id)}"

    # Verify task existed before deletion
    assert "task_info_before" in demo_result, f"Result missing task_info_before"
    task_info_before = demo_result["task_info_before"]
    assert "task" in task_info_before, f"Task info before missing task"
    assert task_info_before["task"]["task_id"] == task_id, f"Task ID mismatch before deletion"

    # Verify delete result
    assert "delete_result" in demo_result, f"Result missing delete_result"
    delete_result = demo_result["delete_result"]
    assert isinstance(delete_result, dict), f"Delete result should be dict, got {type(delete_result)}"
    assert "results" in delete_result, f"Delete result missing results"
    assert len(delete_result["results"]) == 1, f"Delete result should have 1 result"

    result_item = delete_result["results"][0]
    assert result_item["@type"] == "/dysonprotocol.crontask.v1.MsgDeleteTaskResponse", f"Expected MsgDeleteTaskResponse, got {result_item['@type']}"

    # Verify task was deleted
    assert demo_result["task_deleted"] == True, f"Task should be deleted, but task_deleted is {demo_result['task_deleted']}"


def test_delete_task_not_found(chainnet):
    """Test DeleteTask fails when task does not exist."""
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

def demo_delete_task_not_found(gov_addr):
    # Try to delete a non-existent task
    non_existent_task_id = 999999

    delete_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgDeleteTask",
        "creator": gov_addr,
        "task_id": non_existent_task_id
    }

    # This should fail with task not found error
    delete_result = _sudo(delete_task_msg)
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
        "demo_delete_task_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is not None
    ), f"Script execution should have failed with task not found, but got: {json.dumps(query_result, indent=2)}"

    exception = query_result.get("exception")
    assert isinstance(exception, dict), f"Exception should be dict, got {type(exception)}"
    assert "msg" in exception, f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    error_msg = exception["msg"]
    assert isinstance(error_msg, str), f"Error message should be string, got {type(error_msg)}"
    error_msg_lower = error_msg.lower()
    assert "not found" in error_msg_lower, f"Error should mention task not found, got: {error_msg}"


def test_delete_task_unauthorized(chainnet):
    """Test DeleteTask fails when creator doesn't match task creator."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use a different address for unauthorized deletion
    wrong_addr = "dys216vwht46aw58efaxx"

    extra_code = """
import time
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_delete_task_unauthorized(gov_addr, wrong_addr):
    # First create a task with gov_addr as creator
    current_time = int(time.time())
    create_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": gov_addr,
        "scheduled_timestamp": str(current_time + 60),
        "expiry_timestamp": str(current_time + 3600),
        "task_gas_limit": 200000,
        "task_gas_fee": {"denom": "udys", "amount": "1"},
        "msgs": [{
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": gov_addr,
            "to_address": gov_addr,
            "amount": [{"denom": "udys", "amount": "1"}]
        }]
    }

    create_result = _sudo(create_task_msg)
    task_id = create_result["results"][0]["task_id"]

    # Try to delete with wrong creator
    delete_task_msg = {
        "@type": "/dysonprotocol.crontask.v1.MsgDeleteTask",
        "creator": wrong_addr,
        "task_id": task_id
    }

    # This should fail with unauthorized error
    delete_result = _sudo(delete_task_msg)
    return {"create_result": create_result, "task_id": task_id, "delete_result": delete_result}
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
        "demo_delete_task_unauthorized",
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
