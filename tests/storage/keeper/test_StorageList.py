"""
StorageList query handler coverage tests.

Tests the StorageList query endpoint which lists storage entries with prefix filtering,
GJSON filtering/extraction, and pagination. Covers all validation paths and success cases.
All tests use stateless script query execution.
"""

import json
import pytest
from deep_parse import deep_parse


def test_storage_list_success(chainnet):
    """Test StorageList query with valid owner."""
    dysond = chainnet[0]
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list(owner_addr, entries):
    # Create multiple storage entries using _sudo
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
    
    # Query all entries
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr
    })
    
    return {"list_response": list_response}
"""

    entries = [
        ["test/entry1", '{"value": 1}'],
        ["test/entry2", '{"value": 2}'],
        ["other/entry3", '{"value": 3}'],
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
        "demo_storage_list",
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
    list_response = demo_result["list_response"]

    # Validate response structure
    assert isinstance(
        list_response, dict
    ), f"Response should be dict, got {type(list_response)}"
    assert (
        "entries" in list_response
    ), f"Response missing 'entries' key. Keys: {list(list_response.keys())}"
    assert (
        "pagination" in list_response
    ), f"Response missing 'pagination' key. Keys: {list(list_response.keys())}"

    entries_list = list_response["entries"]
    assert isinstance(
        entries_list, list
    ), f"Entries should be list, got {type(entries_list)}"
    assert len(entries_list) >= len(
        entries
    ), f"Expected at least {len(entries)} entries, got {len(entries_list)}"


def test_storage_list_with_prefix(chainnet):
    """Test StorageList query with index_prefix filter."""
    dysond = chainnet[0]
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_prefix(owner_addr, entries, prefix):
    # Create entries with different prefixes
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
    
    # Query with prefix filter
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "index_prefix": prefix
    })
    
    return {"list_response": list_response}
"""

    entries = [
        ["test/entry1", '{"value": 1}'],
        ["test/entry2", '{"value": 2}'],
        ["other/entry3", '{"value": 3}'],
    ]
    kwargs = json.dumps(
        {"owner_addr": owner_addr, "entries": entries, "prefix": "test/"}
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
        "demo_storage_list_prefix",
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
    list_response = demo_result["list_response"]

    assert isinstance(
        list_response, dict
    ), f"Response should be dict, got {type(list_response)}"
    assert (
        "entries" in list_response
    ), f"Response missing 'entries' key. Keys: {list(list_response.keys())}"

    entries_list = list_response["entries"]
    assert isinstance(
        entries_list, list
    ), f"Entries should be list, got {type(entries_list)}"

    # All entries should have test/ prefix
    for entry in entries_list:
        assert entry["index"].startswith(
            "test/"
        ), f"Entry index should start with 'test/': {entry['index']}"


def test_storage_list_with_filter(chainnet):
    """Test StorageList query with GJSON filter."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_filter(owner_addr, entries, prefix, filter_expr):
    # Create entries with different values
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
    
    # Query with filter for status == "active"
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "index_prefix": prefix,
        "filter": filter_expr
    })
    
    return {"list_response": list_response}
"""

    entries = [
        ["test/entry1", '{"status": "active", "value": 10}'],
        ["test/entry2", '{"status": "inactive", "value": 20}'],
        ["test/entry3", '{"status": "active", "value": 30}'],
    ]
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "prefix": "test/",
            "filter_expr": 'status=="active"',
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
        "demo_storage_list_filter",
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
    list_response = demo_result["list_response"]

    assert isinstance(
        list_response, dict
    ), f"Response should be dict, got {type(list_response)}"
    assert (
        "entries" in list_response
    ), f"Response missing 'entries' key. Keys: {list(list_response.keys())}"

    entries_list = list_response["entries"]
    assert isinstance(
        entries_list, list
    ), f"Entries should be list, got {type(entries_list)}"

    # All entries should match filter
    for entry in entries_list:
        # Data may be returned as parsed JSON dict or string
        entry_data = (
            json.loads(entry["data"])
            if isinstance(entry["data"], str)
            else entry["data"]
        )
        assert (
            entry_data["status"] == "active"
        ), f"Entry should have status 'active': {entry_data}"


def test_storage_list_with_extract(chainnet):
    """Test StorageList query with GJSON extract."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_extract(owner_addr, entries, prefix, extract_path):
    # Create entries
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
    
    # Query with extract path
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "index_prefix": prefix,
        "extract": extract_path
    })
    
    return {"list_response": list_response}
"""

    entries = [
        ["test/entry1", '{"user": {"name": "alice"}, "value": 1}'],
        ["test/entry2", '{"user": {"name": "bob"}, "value": 2}'],
    ]
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "prefix": "test/",
            "extract_path": "user.name",
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
        "demo_storage_list_extract",
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
    list_response = demo_result["list_response"]

    assert isinstance(
        list_response, dict
    ), f"Response should be dict, got {type(list_response)}"
    assert (
        "entries" in list_response
    ), f"Response missing 'entries' key. Keys: {list(list_response.keys())}"

    entries_list = list_response["entries"]
    assert isinstance(
        entries_list, list
    ), f"Entries should be list, got {type(entries_list)}"
    assert len(entries_list) == 2, f"Expected 2 entries, got {len(entries_list)}"

    # Data should be extracted
    assert (
        entries_list[0]["data"] == '"alice"'
    ), f"First entry should have extracted name 'alice', got {entries_list[0]['data']}"
    assert (
        entries_list[1]["data"] == '"bob"'
    ), f"Second entry should have extracted name 'bob', got {entries_list[1]['data']}"


def test_storage_list_pagination_offset(chainnet):
    """Test StorageList query with offset pagination."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_pagination_offset(owner_addr, prefix, offset, limit):
    # Create multiple entries
    for i in range(5):
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": f"{prefix}entry{i}",
            "data": f'{{"value": {i}}}'
        })
    
    # Query with offset and limit
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "index_prefix": prefix,
        "pagination": {
            "offset": offset,
            "limit": limit
        }
    })
    
    return {"list_response": list_response}
"""

    kwargs = json.dumps(
        {"owner_addr": owner_addr, "prefix": "test/", "offset": 2, "limit": 2}
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
        "demo_storage_list_pagination_offset",
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
    list_response = demo_result["list_response"]

    assert isinstance(
        list_response, dict
    ), f"Response should be dict, got {type(list_response)}"
    assert (
        "entries" in list_response
    ), f"Response missing 'entries' key. Keys: {list(list_response.keys())}"

    entries_list = list_response["entries"]
    assert isinstance(
        entries_list, list
    ), f"Entries should be list, got {type(entries_list)}"
    assert (
        len(entries_list) == 2
    ), f"Expected 2 entries with limit=2, got {len(entries_list)}"


def test_storage_list_pagination_key(chainnet):
    """Test StorageList query with key-based pagination."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_pagination_key(owner_addr, prefix, limit):
    # Create multiple entries
    for i in range(5):
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": f"{prefix}entry{i}",
            "data": f'{{"value": {i}}}'
        })
    
    # Query first page
    first_page = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "index_prefix": prefix,
        "pagination": {
            "limit": limit
        }
    })
    
    # Get next key from pagination
    next_key = first_page.get("pagination", {}).get("next_key")
    
    # Query second page using next_key
    second_page = None
    if next_key:
        second_page = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": owner_addr,
            "index_prefix": prefix,
            "pagination": {
                "key": next_key,
                "limit": limit
            }
        })
    
    return {"first_page": first_page, "second_page": second_page}
"""

    kwargs = json.dumps({"owner_addr": owner_addr, "prefix": "test/", "limit": 2})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_list_pagination_key",
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
    first_page = demo_result["first_page"]
    second_page = demo_result["second_page"]

    assert isinstance(
        first_page, dict
    ), f"First page should be dict, got {type(first_page)}"
    assert "entries" in first_page, f"First page missing 'entries' key"
    assert "pagination" in first_page, f"First page missing 'pagination' key"

    first_entries = first_page["entries"]
    assert (
        len(first_entries) == 2
    ), f"Expected 2 entries in first page, got {len(first_entries)}"

    # Get next key from pagination
    pagination = first_page["pagination"]
    assert "next_key" in pagination, f"Pagination missing 'next_key'"

    next_key = pagination["next_key"]
    assert next_key, f"next_key should not be empty"

    assert second_page is not None, f"Second page should exist"
    assert isinstance(
        second_page, dict
    ), f"Second page should be dict, got {type(second_page)}"
    assert "entries" in second_page, f"Second page missing 'entries' key"

    second_entries = second_page["entries"]
    assert (
        len(second_entries) >= 1
    ), f"Expected at least 1 entry in second page, got {len(second_entries)}"

    # Entries should be different
    first_indices = {e["index"] for e in first_entries}
    second_indices = {e["index"] for e in second_entries}
    assert first_indices.isdisjoint(
        second_indices
    ), f"Page entries should not overlap: {first_indices} vs {second_indices}"


def test_storage_list_invalid_pagination(chainnet):
    """Test StorageList query with both offset and key specified (invalid)."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_storage_list_invalid_pagination(owner_addr, offset, page_key):
    # Query with both offset and key (should fail)
    try:
        list_response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": owner_addr,
            "pagination": {
                "offset": offset,
                "key": page_key
            }
        })
        return {"list_response": list_response, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    kwargs = json.dumps({"owner_addr": owner_addr, "offset": 1, "page_key": "test"})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_list_invalid_pagination",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should have error
    assert (
        demo_result.get("error") is not None
    ), f"Expected error for invalid pagination, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "either offset or key is expected" in error_str
    ), f"Expected pagination conflict error, got: {demo_result['error']}"


def test_storage_list_filter_too_long(chainnet):
    """Test StorageList query with filter path exceeding 100 character limit."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_storage_list_filter_too_long(owner_addr, long_filter):
    # Query with too long filter path
    try:
        list_response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": owner_addr,
            "filter": long_filter
        })
        return {"list_response": list_response, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    long_filter = "a" * 101
    kwargs = json.dumps({"owner_addr": owner_addr, "long_filter": long_filter})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_list_filter_too_long",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should have error
    assert (
        demo_result.get("error") is not None
    ), f"Expected error for too long filter, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "filter path too long" in error_str
    ), f"Expected filter path length error, got: {demo_result['error']}"


def test_storage_list_extract_too_long(chainnet):
    """Test StorageList query with extract path exceeding 100 character limit."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_storage_list_extract_too_long(owner_addr, long_extract):
    # Query with too long extract path
    try:
        list_response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": owner_addr,
            "extract": long_extract
        })
        return {"list_response": list_response, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    long_extract = "a" * 101
    kwargs = json.dumps({"owner_addr": owner_addr, "long_extract": long_extract})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_list_extract_too_long",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should have error
    assert (
        demo_result.get("error") is not None
    ), f"Expected error for too long extract, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "extract path too long" in error_str
    ), f"Expected extract path length error, got: {demo_result['error']}"


def test_storage_list_index_normalization(chainnet):
    """Test StorageList query normalizes index by removing owner prefix."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_index_normalization(owner_addr, test_index, test_data):
    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Query entries
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr
    })
    
    return {"list_response": list_response}
"""

    test_index = "test/normalized"
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": test_index,
            "test_data": '{"test": "normalization"}',
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
        "demo_storage_list_index_normalization",
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
    list_response = demo_result["list_response"]

    assert isinstance(
        list_response, dict
    ), f"Response should be dict, got {type(list_response)}"
    assert "entries" in list_response, f"Response missing 'entries' key"

    entries_list = list_response["entries"]
    matching_entries = [
        e
        for e in entries_list
        if e["index"] == test_index or e["index"].endswith(test_index)
    ]
    assert len(matching_entries) > 0, f"Expected entry with index {test_index}"

    for entry in matching_entries:
        # Index in response should not include owner prefix
        assert not entry["index"].startswith(
            owner_addr
        ), f"Index should not start with owner address: {entry['index']}"


def test_storage_list_reverse_pagination(chainnet):
    """Test StorageList query with reverse pagination."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_reverse(owner_addr, prefix, limit):
    # Create multiple entries
    for i in range(5):
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": f"{prefix}entry{i}",
            "data": f'{{"value": {i}}}'
        })
    
    # Query with reverse pagination
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "index_prefix": prefix,
        "pagination": {
            "limit": limit,
            "reverse": True
        }
    })
    
    return {"list_response": list_response}
"""

    kwargs = json.dumps(
        {"owner_addr": owner_addr, "prefix": "test/reverse/", "limit": 3}
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
        "demo_storage_list_reverse",
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
    list_response = demo_result["list_response"]

    assert isinstance(
        list_response, dict
    ), f"Response should be dict, got {type(list_response)}"
    assert (
        "entries" in list_response
    ), f"Response missing 'entries' key. Keys: {list(list_response.keys())}"

    entries_list = list_response["entries"]
    assert isinstance(
        entries_list, list
    ), f"Entries should be list, got {type(entries_list)}"
    assert (
        len(entries_list) == 3
    ), f"Expected 3 entries with limit=3, got {len(entries_list)}"

    # Verify entries are in reverse order (last entries first)
    # Entries should be entry4, entry3, entry2 (reverse of entry0, entry1, entry2)
    indices = [e["index"] for e in entries_list]
    first_index = indices[0]
    assert (
        "entry4" in first_index
    ), f"First entry in reverse should be entry4 (last entry). Got indices: {indices}"


def test_storage_list_count_total(chainnet):
    """Test StorageList query with count_total requested."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_count_total(owner_addr, prefix, limit):
    # Create multiple entries
    for i in range(5):
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": f"{prefix}entry{i}",
            "data": f'{{"value": {i}}}'
        })
    
    # Query with count_total requested
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "index_prefix": prefix,
        "pagination": {
            "limit": limit,
            "count_total": True
        }
    })
    
    return {"list_response": list_response}
"""

    kwargs = json.dumps({"owner_addr": owner_addr, "prefix": "test/count/", "limit": 2})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_list_count_total",
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
    list_response = demo_result["list_response"]

    assert isinstance(
        list_response, dict
    ), f"Response should be dict, got {type(list_response)}"
    assert (
        "pagination" in list_response
    ), f"Response missing 'pagination' key. Keys: {list(list_response.keys())}"

    pagination = list_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"
    assert (
        "total" in pagination
    ), f"Pagination missing 'total' key when count_total=True. Keys: {list(pagination.keys())}"

    total = pagination["total"]
    assert isinstance(
        total, (str, int)
    ), f"Total should be string or int, got {type(total)}"
    assert int(total) == 5, f"Expected total=5 entries, got {total}"


def test_storage_list_filter_comparison_operators(chainnet):
    """Test StorageList query with GJSON filter comparison operators (==, !=, <, <=, >, >=)."""
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_filter_ops(owner_addr, entries, filter_expr):
    # Create entries with numeric values
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
    
    # Query with filter
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "filter": filter_expr
    })
    
    return {"list_response": list_response}
"""

    entries = [
        ["test/entry1", '{"value": 10}'],
        ["test/entry2", '{"value": 20}'],
        ["test/entry3", '{"value": 30}'],
        ["test/entry4", '{"value": 40}'],
    ]

    # Test == operator
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "filter_expr": "value==20",
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
        "demo_storage_list_filter_ops",
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
    entries_list = demo_result["list_response"]["entries"]
    assert (
        len(entries_list) == 1
    ), f"Expected 1 entry with value==20, got {len(entries_list)}"
    entry_data = (
        json.loads(entries_list[0]["data"])
        if isinstance(entries_list[0]["data"], str)
        else entries_list[0]["data"]
    )
    assert (
        entry_data["value"] == 20
    ), f"Entry should have value 20, got {entry_data['value']}"

    # Test != operator
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "filter_expr": "value!=20",
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
        "demo_storage_list_filter_ops",
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
    entries_list = demo_result["list_response"]["entries"]
    assert (
        len(entries_list) == 3
    ), f"Expected 3 entries with value!=20, got {len(entries_list)}"
    for entry in entries_list:
        entry_data = (
            json.loads(entry["data"])
            if isinstance(entry["data"], str)
            else entry["data"]
        )
        assert (
            entry_data["value"] != 20
        ), f"Entry should not have value 20, got {entry_data['value']}"

    # Test < operator
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "filter_expr": "value<30",
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
        "demo_storage_list_filter_ops",
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
    entries_list = demo_result["list_response"]["entries"]
    assert (
        len(entries_list) == 2
    ), f"Expected 2 entries with value<30, got {len(entries_list)}"
    for entry in entries_list:
        entry_data = (
            json.loads(entry["data"])
            if isinstance(entry["data"], str)
            else entry["data"]
        )
        assert (
            entry_data["value"] < 30
        ), f"Entry should have value < 30, got {entry_data['value']}"

    # Test <= operator
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "filter_expr": "value<=20",
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
        "demo_storage_list_filter_ops",
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
    entries_list = demo_result["list_response"]["entries"]
    assert (
        len(entries_list) == 2
    ), f"Expected 2 entries with value<=20, got {len(entries_list)}"
    for entry in entries_list:
        entry_data = (
            json.loads(entry["data"])
            if isinstance(entry["data"], str)
            else entry["data"]
        )
        assert (
            entry_data["value"] <= 20
        ), f"Entry should have value <= 20, got {entry_data['value']}"

    # Test > operator
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "filter_expr": "value>20",
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
        "demo_storage_list_filter_ops",
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
    entries_list = demo_result["list_response"]["entries"]
    assert (
        len(entries_list) == 2
    ), f"Expected 2 entries with value>20, got {len(entries_list)}"
    for entry in entries_list:
        entry_data = (
            json.loads(entry["data"])
            if isinstance(entry["data"], str)
            else entry["data"]
        )
        assert (
            entry_data["value"] > 20
        ), f"Entry should have value > 20, got {entry_data['value']}"

    # Test >= operator
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "filter_expr": "value>=30",
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
        "demo_storage_list_filter_ops",
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
    entries_list = demo_result["list_response"]["entries"]
    assert (
        len(entries_list) == 2
    ), f"Expected 2 entries with value>=30, got {len(entries_list)}"
    for entry in entries_list:
        entry_data = (
            json.loads(entry["data"])
            if isinstance(entry["data"], str)
            else entry["data"]
        )
        assert (
            entry_data["value"] >= 30
        ), f"Entry should have value >= 30, got {entry_data['value']}"


def test_storage_list_filter_pattern_matching(chainnet):
    """Test StorageList query with GJSON filter pattern matching (% for like).

    Based on GJSON documentation (https://github.com/tidwall/gjson):
    - % operator is for pattern matching (like)
    - Uses * as wildcard for matching patterns
    - Pattern syntax: field%"pattern*" matches strings starting with "pattern"
    """
    dysond = chainnet[0]
    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"
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

def demo_storage_list_filter_pattern(owner_addr, entries, filter_expr):
    # Create entries with string values
    for index, data in entries:
        _sudo({
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": owner_addr,
            "index": index,
            "data": data
        })
    
    # Query with pattern filter
    list_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner_addr,
        "filter": filter_expr
    })
    
    return {"list_response": list_response}
"""

    entries = [
        ["test/entry1", '{"name": "alice", "email": "alice@example.com"}'],
        ["test/entry2", '{"name": "bob", "email": "bob@test.com"}'],
        ["test/entry3", '{"name": "charlie", "email": "charlie@example.org"}'],
        ["test/entry4", '{"name": "dave", "email": "dave@other.com"}'],
    ]

    # Test % (like) operator - match names starting with "al"
    # GJSON pattern matching: field%"pattern*" matches strings starting with "pattern"
    # Using "al*" to match names starting with "al" (alice matches, charlie doesn't)
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "entries": entries,
            "filter_expr": 'name%"al*"',
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
        "demo_storage_list_filter_pattern",
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
    entries_list = demo_result["list_response"]["entries"]
    # Pattern "al*" should match names starting with "al" (alice)
    assert (
        len(entries_list) == 1
    ), f"Expected 1 entry with name starting with 'al', got {len(entries_list)}"
    entry_data = (
        json.loads(entries_list[0]["data"])
        if isinstance(entries_list[0]["data"], str)
        else entries_list[0]["data"]
    )
    assert entry_data["name"].startswith(
        "al"
    ), f"Entry name should start with 'al', got {entry_data['name']}"
    assert entry_data["name"] == "alice", f"Expected 'alice', got {entry_data['name']}"
