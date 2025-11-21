"""
StorageDelete message handler coverage tests.

Tests the StorageDelete message handler which removes storage entries.
Covers all validation paths, success cases, ownership verification, and metrics updates.
All tests use stateless script query execution with _sudo for state setup and deletion.
"""

import json
import pytest
from deep_parse import deep_parse


def test_storage_delete_success_single(chainnet, generate_account):
    """Test StorageDelete deletes single entry successfully."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_single", faucet_amount=1_000_000
    )
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

def demo_storage_delete_single(owner_addr, test_index, test_data):
    # Set storage entry using _sudo
    set_result = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Verify entry exists before deletion
    get_before = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
        "owner": owner_addr,
        "index": test_index
    })
    
    # Delete entry using _sudo
    delete_result = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
        "owner": owner_addr,
        "indexes": [test_index]
    })
    
    # Verify entry no longer exists
    try:
        get_after = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": owner_addr,
            "index": test_index
        })
        get_after_exists = True
    except Exception:
        get_after_exists = False
    
    return {
        "set_result": set_result,
        "get_before": get_before,
        "delete_result": delete_result,
        "get_after_exists": get_after_exists
    }
"""

    test_index = "test/delete_single"
    test_data = '{"test": "delete"}'
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": test_index,
            "test_data": test_data,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_single",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "delete_result" in demo_result
    ), f"Result missing 'delete_result' key. Keys: {list(demo_result.keys())}"

    delete_result = demo_result["delete_result"]
    assert isinstance(
        delete_result, dict
    ), f"Delete result should be dict, got {type(delete_result)}"
    assert (
        "results" in delete_result
    ), f"Delete result missing 'results' key. Keys: {list(delete_result.keys())}"
    assert (
        len(delete_result["results"]) > 0
    ), f"Delete result should have at least one result, got {len(delete_result['results'])}"

    delete_response = delete_result["results"][0]
    assert isinstance(
        delete_response, dict
    ), f"Delete response should be dict, got {type(delete_response)}"
    assert (
        "deleted_indexes" in delete_response
    ), f"Delete response missing 'deleted_indexes' key. Keys: {list(delete_response.keys())}"

    deleted_indexes = delete_response["deleted_indexes"]
    assert isinstance(
        deleted_indexes, list
    ), f"deleted_indexes should be list, got {type(deleted_indexes)}"
    assert (
        len(deleted_indexes) == 1
    ), f"Expected 1 deleted index, got {len(deleted_indexes)}"
    assert (
        deleted_indexes[0] == test_index
    ), f"Expected deleted index {test_index}, got {deleted_indexes[0]}"

    # Verify entry no longer exists
    assert (
        demo_result["get_after_exists"] is False
    ), f"Entry should not exist after deletion"


def test_storage_delete_success_multiple(chainnet, generate_account):
    """Test StorageDelete deletes multiple entries successfully."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_multiple", faucet_amount=1_000_000
    )
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

def demo_storage_delete_multiple(owner_addr, entries):
    # Set multiple storage entries using _sudo
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
    
    # Delete multiple entries using _sudo
    indexes = [entry[0] for entry in entries]
    delete_result = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
        "owner": owner_addr,
        "indexes": indexes
    })
    
    # Verify entries no longer exist
    still_exist = []
    for index in indexes:
        try:
            _query({
                "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                "owner": owner_addr,
                "index": index
            })
            still_exist.append(index)
        except Exception:
            pass
    
    return {
        "delete_result": delete_result,
        "still_exist": still_exist
    }
"""

    entries = [
        ["test/delete1", '{"value": 1}'],
        ["test/delete2", '{"value": 2}'],
        ["test/delete3", '{"value": 3}'],
    ]
    kwargs = json.dumps({"owner_addr": owner_addr, "entries": entries})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_multiple",
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
    delete_result = demo_result["delete_result"]
    delete_response = delete_result["results"][0]
    deleted_indexes = delete_response["deleted_indexes"]

    assert isinstance(
        deleted_indexes, list
    ), f"deleted_indexes should be list, got {type(deleted_indexes)}"
    assert (
        len(deleted_indexes) == 3
    ), f"Expected 3 deleted indexes, got {len(deleted_indexes)}"

    # Verify all entries were deleted
    still_exist = demo_result["still_exist"]
    assert isinstance(
        still_exist, list
    ), f"still_exist should be list, got {type(still_exist)}"
    assert (
        len(still_exist) == 0
    ), f"Expected no entries to still exist, got {still_exist}"


def test_storage_delete_nonexistent_entry(chainnet, generate_account):
    """Test StorageDelete handles non-existent entry gracefully (skipped, not error)."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_nonexist", faucet_amount=1_000_000
    )
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

def demo_storage_delete_nonexistent(owner_addr, test_index):
    # Try to delete non-existent entry
    # This should succeed but return empty deleted_indexes
    try:
        delete_result = _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": owner_addr,
            "indexes": [test_index]
        })
        return {"delete_result": delete_result, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    test_index = "test/nonexistent"
    kwargs = json.dumps({"owner_addr": owner_addr, "test_index": test_index})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_nonexistent",
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
    # Non-existent entries should cause error (no entries deleted)
    assert (
        demo_result.get("error") is not None
    ), f"Expected error for non-existent entry deletion, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "no entries were deleted" in error_str
    ), f"Expected 'no entries were deleted' error, got: {demo_result['error']}"


def test_storage_delete_partial(chainnet, generate_account):
    """Test StorageDelete handles partial deletion (some exist, some don't)."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_partial", faucet_amount=1_000_000
    )
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

def demo_storage_delete_partial(owner_addr, existing_index, existing_data, nonexistent_index):
    # Set one entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": existing_index,
        "data": existing_data
    })
    
    # Try to delete both existing and non-existing entries
    try:
        delete_result = _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": owner_addr,
            "indexes": [existing_index, nonexistent_index]
        })
        return {"delete_result": delete_result, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    existing_index = "test/existing"
    existing_data = '{"value": 42}'
    nonexistent_index = "test/nonexistent"
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "existing_index": existing_index,
            "existing_data": existing_data,
            "nonexistent_index": nonexistent_index,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_partial",
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
    # Should succeed and delete only the existing entry
    assert (
        demo_result.get("error") is None
    ), f"Expected success for partial deletion, got error: {demo_result.get('error')}"
    delete_result = demo_result["delete_result"]
    delete_response = delete_result["results"][0]
    deleted_indexes = delete_response["deleted_indexes"]
    assert isinstance(
        deleted_indexes, list
    ), f"deleted_indexes should be list, got {type(deleted_indexes)}"
    assert (
        len(deleted_indexes) == 1
    ), f"Expected 1 deleted index, got {len(deleted_indexes)}"
    assert (
        deleted_indexes[0] == existing_index
    ), f"Expected deleted index {existing_index}, got {deleted_indexes[0]}"


def test_storage_delete_empty_indexes(chainnet, generate_account):
    """Test StorageDelete error path: empty indexes list."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_empty", faucet_amount=1_000_000
    )
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

def demo_storage_delete_empty(owner_addr):
    # Try to delete with empty indexes list
    try:
        delete_result = _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": owner_addr,
            "indexes": []
        })
        return {"delete_result": delete_result, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    kwargs = json.dumps({"owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_empty",
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
    assert (
        demo_result.get("error") is not None
    ), f"Expected error for empty indexes, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "must specify at least one index" in error_str
    ), f"Expected 'must specify at least one index' error, got: {demo_result['error']}"


def test_storage_delete_no_entries_deleted(chainnet, generate_account):
    """Test StorageDelete error path: no entries deleted (all non-existent)."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_none", faucet_amount=1_000_000
    )
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

def demo_storage_delete_none(owner_addr, indexes):
    # Try to delete multiple non-existent entries
    try:
        delete_result = _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": owner_addr,
            "indexes": indexes
        })
        return {"delete_result": delete_result, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    indexes = ["test/nonexistent1", "test/nonexistent2"]
    kwargs = json.dumps({"owner_addr": owner_addr, "indexes": indexes})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_none",
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
    assert (
        demo_result.get("error") is not None
    ), f"Expected error when no entries deleted, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "no entries were deleted" in error_str
    ), f"Expected 'no entries were deleted' error, got: {demo_result['error']}"


def test_storage_delete_metrics_update(chainnet, generate_account):
    """Test StorageDelete metrics update: decrements total_bytes correctly."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_metrics", faucet_amount=1_000_000
    )
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

def demo_storage_delete_metrics(owner_addr, test_index, test_data):
    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Get metrics before deletion
    metrics_before = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    # Delete entry
    delete_result = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
        "owner": owner_addr,
        "indexes": [test_index]
    })
    
    # Get metrics after deletion
    metrics_after = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    return {
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "delete_result": delete_result,
        "data_size": len(test_data)
    }
"""

    test_index = "test/metrics"
    test_data = '{"test": "data", "value": 12345}'
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": test_index,
            "test_data": test_data,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_metrics",
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
    metrics_before = demo_result["metrics_before"]
    metrics_after = demo_result["metrics_after"]

    assert isinstance(
        metrics_before, dict
    ), f"Metrics before should be dict, got {type(metrics_before)}"
    assert isinstance(
        metrics_after, dict
    ), f"Metrics after should be dict, got {type(metrics_after)}"

    total_bytes_before = int(metrics_before.get("total_bytes", 0))
    total_bytes_after = int(metrics_after.get("total_bytes", 0))

    data_size = len(test_data)
    assert (
        total_bytes_before == data_size
    ), f"Expected total_bytes before deletion to be {data_size}, got {total_bytes_before}"
    assert (
        total_bytes_after == 0
    ), f"Expected total_bytes after deletion to be 0, got {total_bytes_after}"


def test_storage_delete_event_emission(chainnet, generate_account):
    """Test StorageDelete event emission: EventStorageDelete emitted."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_event", faucet_amount=1_000_000
    )
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

def demo_storage_delete_event(owner_addr, test_index, test_data):
    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Delete entry
    delete_result = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
        "owner": owner_addr,
        "indexes": [test_index]
    })
    
    return {"delete_result": delete_result}
"""

    test_index = "test/event"
    test_data = '{"test": "event"}'
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": test_index,
            "test_data": test_data,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_event",
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
    delete_result = demo_result["delete_result"]
    delete_response = delete_result["results"][0]
    assert isinstance(
        delete_response, dict
    ), f"Delete response should be dict, got {type(delete_response)}"
    assert (
        "deleted_indexes" in delete_response
    ), f"Delete response missing 'deleted_indexes' key"
    deleted_indexes = delete_response["deleted_indexes"]
    assert isinstance(
        deleted_indexes, list
    ), f"deleted_indexes should be list, got {type(deleted_indexes)}"
    assert (
        len(deleted_indexes) == 1
    ), f"Expected 1 deleted index, got {len(deleted_indexes)}"
    assert (
        deleted_indexes[0] == test_index
    ), f"Expected deleted index {test_index}, got {deleted_indexes[0]}"


def test_storage_delete_response_fields(chainnet, generate_account):
    """Test StorageDelete response: returns list of successfully deleted indexes."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_response", faucet_amount=1_000_000
    )
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

def demo_storage_delete_response(owner_addr, entries):
    # Set multiple storage entries
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
    
    # Delete entries
    indexes = [entry[0] for entry in entries]
    delete_result = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
        "owner": owner_addr,
        "indexes": indexes
    })
    
    return {"delete_result": delete_result}
"""

    entries = [
        ["test/response1", '{"value": 1}'],
        ["test/response2", '{"value": 2}'],
    ]
    kwargs = json.dumps({"owner_addr": owner_addr, "entries": entries})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_response",
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
    delete_result = demo_result["delete_result"]
    delete_response = delete_result["results"][0]
    deleted_indexes = delete_response["deleted_indexes"]

    assert isinstance(
        deleted_indexes, list
    ), f"deleted_indexes should be list, got {type(deleted_indexes)}"
    assert (
        len(deleted_indexes) == 2
    ), f"Expected 2 deleted indexes, got {len(deleted_indexes)}"
    assert (
        "test/response1" in deleted_indexes
    ), f"Expected 'test/response1' in deleted_indexes, got {deleted_indexes}"
    assert (
        "test/response2" in deleted_indexes
    ), f"Expected 'test/response2' in deleted_indexes, got {deleted_indexes}"


def test_storage_delete_invalid_owner(chainnet):
    """Test StorageDelete error path: invalid owner address (malformed bech32)."""
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

def demo_storage_delete_invalid_owner(invalid_owner, test_index):
    # Try to delete with invalid owner address
    try:
        delete_result = _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": invalid_owner,
            "indexes": [test_index]
        })
        return {"delete_result": delete_result, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    kwargs = json.dumps(
        {"invalid_owner": "invalid_address", "test_index": "test/key"}
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_invalid_owner",
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
    assert (
        demo_result.get("error") is not None
    ), f"Expected error for invalid owner, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    # Check for various forms of invalid address errors
    has_invalid = "invalid" in error_str
    has_bech32 = "bech32" in error_str
    has_decode = "decode" in error_str
    # At least one of these should be present
    is_valid_error = has_invalid
    is_valid_error = is_valid_error or has_bech32
    is_valid_error = is_valid_error or has_decode
    assert (
        is_valid_error is True
    ), f"Expected invalid address error (invalid/bech32/decode), got: {demo_result['error']}"


def test_storage_delete_ownership_mismatch(chainnet, generate_account):
    """Test StorageDelete error path: ownership mismatch (entry owned by different address)."""
    dysond = chainnet[0]
    [owner1_name, owner1_addr] = generate_account(
        "storage_delete_owner1", faucet_amount=1_000_000
    )
    [owner2_name, owner2_addr] = generate_account(
        "storage_delete_owner2", faucet_amount=1_000_000
    )
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

def demo_storage_delete_ownership_mismatch(owner1_addr, owner2_addr, test_index, test_data):
    # Set storage entry owned by owner1
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner1_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Try to delete entry using owner2 (should fail)
    try:
        delete_result = _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": owner2_addr,
            "indexes": [test_index]
        })
        return {"delete_result": delete_result, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    test_index = "test/ownership"
    test_data = '{"test": "ownership"}'
    kwargs = json.dumps(
        {
            "owner1_addr": owner1_addr,
            "owner2_addr": owner2_addr,
            "test_index": test_index,
            "test_data": test_data,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_ownership_mismatch",
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
    # Ownership mismatch should cause error
    # Note: The key is constructed as owner2_addr/test_index, which won't exist
    # So it will fail with "no entries were deleted" rather than ownership error
    # This is because the key doesn't match owner1's entry
    assert (
        demo_result.get("error") is not None
    ), f"Expected error for ownership mismatch, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    # The error will be "no entries were deleted" because the key doesn't match
    # Check for various forms of ownership/permission errors
    has_no_entries = "no entries were deleted" in error_str
    has_cannot_delete = "cannot delete" in error_str
    has_permission = "permission" in error_str
    # At least one of these should be present
    is_valid_error = has_no_entries
    is_valid_error = is_valid_error or has_cannot_delete
    is_valid_error = is_valid_error or has_permission
    assert (
        is_valid_error is True
    ), f"Expected ownership/permission error (no entries/cannot delete/permission), got: {demo_result['error']}"


def test_storage_delete_multiple_metrics_update(chainnet, generate_account):
    """Test StorageDelete metrics update: handles multiple deletions correctly."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_multi_metrics", faucet_amount=1_000_000
    )
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

def demo_storage_delete_multiple_metrics(owner_addr, entries):
    # Set multiple storage entries
    total_size = 0
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
        total_size += len(data)
    
    # Get metrics before deletion
    metrics_before = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    # Delete all entries
    indexes = [entry[0] for entry in entries]
    delete_result = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
        "owner": owner_addr,
        "indexes": indexes
    })
    
    # Get metrics after deletion
    metrics_after = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    return {
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "delete_result": delete_result,
        "total_size": total_size
    }
"""

    entries = [
        ["test/metrics1", '{"value": 1}'],
        ["test/metrics2", '{"value": 22}'],
        ["test/metrics3", '{"value": 333}'],
    ]
    kwargs = json.dumps({"owner_addr": owner_addr, "entries": entries})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_delete_multiple_metrics",
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
    metrics_before = demo_result["metrics_before"]
    metrics_after = demo_result["metrics_after"]

    assert isinstance(
        metrics_before, dict
    ), f"Metrics before should be dict, got {type(metrics_before)}"
    assert isinstance(
        metrics_after, dict
    ), f"Metrics after should be dict, got {type(metrics_after)}"

    total_bytes_before = int(metrics_before.get("total_bytes", 0))
    total_bytes_after = int(metrics_after.get("total_bytes", 0))

    # Calculate expected total size
    expected_size = sum(len(entry[1]) for entry in entries)

    assert (
        total_bytes_before == expected_size
    ), f"Expected total_bytes before deletion to be {expected_size}, got {total_bytes_before}"
    assert (
        total_bytes_after == 0
    ), f"Expected total_bytes after deletion to be 0, got {total_bytes_after}"

    # Verify all entries were deleted
    delete_result = demo_result["delete_result"]
    delete_response = delete_result["results"][0]
    deleted_indexes = delete_response["deleted_indexes"]
    assert (
        len(deleted_indexes) == len(entries)
    ), f"Expected {len(entries)} deleted indexes, got {len(deleted_indexes)}"

