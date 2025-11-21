"""
StorageGet query handler coverage tests.

Tests the StorageGet query endpoint which retrieves a single storage entry by owner and index.
Covers all validation paths, success cases, name resolution, and GJSON extraction.
All tests use stateless script query execution.
"""

import json
import pytest
from deep_parse import deep_parse


def test_storage_get_success(chainnet, generate_account):
    """Test StorageGet query with valid owner and index."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_get_test", faucet_amount=1_000_000
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

def demo_storage_get(owner_addr, test_index, test_data):
    # Set storage entry using _sudo
    set_result = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Query storage entry
    get_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
        "owner": owner_addr,
        "index": test_index
    })
    
    return {"set_result": set_result, "get_response": get_response}
"""

    test_index = "test/key"
    test_data = '{"message": "hello", "value": 42}'
    kwargs = json.dumps(
        {"owner_addr": owner_addr, "test_index": test_index, "test_data": test_data}
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
        "demo_storage_get",
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
    get_response = demo_result["get_response"]

    # Validate response structure (Type)
    assert isinstance(
        get_response, dict
    ), f"StorageGet response should be dict, got {type(get_response)}. Full response: {json.dumps(get_response, indent=2)}"
    assert (
        "entry" in get_response
    ), f"Response missing 'entry' key. Keys: {list(get_response.keys())}. Full response: {json.dumps(get_response, indent=2)}"

    entry = get_response["entry"]

    # Validate entry structure (Type + Shape)
    assert isinstance(entry, dict), f"Entry should be dict, got {type(entry)}"
    assert "owner" in entry, f"Entry missing 'owner' key. Keys: {list(entry.keys())}"
    assert "index" in entry, f"Entry missing 'index' key. Keys: {list(entry.keys())}"
    assert "data" in entry, f"Entry missing 'data' key. Keys: {list(entry.keys())}"

    # Validate values
    assert (
        entry["owner"] == owner_addr
    ), f"Owner mismatch: expected {owner_addr}, got {entry['owner']}"
    assert (
        entry["index"] == test_index
    ), f"Index mismatch: expected {test_index}, got {entry['index']}"
    # Data is returned as parsed JSON dict - compare parsed versions
    entry_data_parsed = (
        json.loads(entry["data"]) if isinstance(entry["data"], str) else entry["data"]
    )
    expected_data_parsed = json.loads(test_data)
    assert (
        entry_data_parsed == expected_data_parsed
    ), f"Data mismatch: expected {expected_data_parsed}, got {entry_data_parsed}"


def test_storage_get_with_extract(chainnet, generate_account):
    """Test StorageGet query with GJSON extract path."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_get_extract", faucet_amount=1_000_000
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

def demo_storage_get_extract(owner_addr, test_index, test_data, extract_path):
    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Query with extract path
    get_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
        "owner": owner_addr,
        "index": test_index,
        "extract": extract_path
    })
    
    return {"get_response": get_response}
"""

    test_index = "test/nested"
    test_data = '{"user": {"name": "alice", "age": 30}, "settings": {"theme": "dark"}}'
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": test_index,
            "test_data": test_data,
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
        "demo_storage_get_extract",
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
    get_response = demo_result["get_response"]

    assert isinstance(
        get_response, dict
    ), f"Response should be dict, got {type(get_response)}"
    assert (
        "entry" in get_response
    ), f"Response missing 'entry' key. Keys: {list(get_response.keys())}"

    entry = get_response["entry"]
    assert (
        entry["data"] == '"alice"'
    ), f"Extracted data mismatch: expected '\"alice\"', got {entry['data']}"


def test_storage_get_extract_not_found(chainnet, generate_account):
    """Test StorageGet query with extract path that doesn't exist."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_get_extract_err", faucet_amount=1_000_000
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

def demo_storage_get_extract_not_found(owner_addr, test_index, test_data, extract_path):
    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Query with non-existent extract path
    try:
        get_response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": owner_addr,
            "index": test_index,
            "extract": extract_path
        })
        return {"get_response": get_response, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    test_index = "test/simple"
    test_data = '{"value": 42}'
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": test_index,
            "test_data": test_data,
            "extract_path": "nonexistent.path",
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
        "demo_storage_get_extract_not_found",
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
    ), f"Expected error for non-existent extract path, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "extract path" in error_str
    ), f"Expected extract path error, got: {demo_result['error']}"
    assert (
        "not found" in error_str
    ), f"Expected 'not found' in error, got: {demo_result['error']}"


def test_storage_get_not_found(chainnet, generate_account):
    """Test StorageGet query with non-existent entry."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_get_notfound", faucet_amount=1_000_000
    )
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_storage_get_not_found(owner_addr, test_index):
    # Query non-existent entry
    try:
        get_response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": owner_addr,
            "index": test_index
        })
        return {"get_response": get_response, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    kwargs = json.dumps({"owner_addr": owner_addr, "test_index": "nonexistent/key"})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_get_not_found",
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
    ), f"Expected error for non-existent entry, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    # Error message contains "doesn't exist" (checking for the actual format)
    assert (
        "doesn" in error_str
    ), f"Expected 'doesn' in error message, got: {demo_result['error']}"
    assert (
        "exist" in error_str
    ), f"Expected 'exist' in error message, got: {demo_result['error']}"


def test_storage_get_extract_too_long(chainnet, generate_account):
    """Test StorageGet query with extract path exceeding 100 character limit."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_get_long_extract", faucet_amount=1_000_000
    )
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_storage_get_extract_too_long(owner_addr, test_index, long_extract):
    # Query with too long extract path
    try:
        get_response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": owner_addr,
            "index": test_index,
            "extract": long_extract
        })
        return {"get_response": get_response, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    long_extract = "a" * 101
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": "test/key",
            "long_extract": long_extract,
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
        "demo_storage_get_extract_too_long",
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
    ), f"Expected error for too long extract path, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "extract path too long" in error_str
    ), f"Expected extract path length error, got: {demo_result['error']}"


def test_storage_get_name_resolution(chainnet, generate_account, register_name):
    """Test StorageGet query with nameservice name resolution."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_get_name", faucet_amount=1_000_000
    )
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Register nameservice name (this needs to persist, so use tx)
    ns_name = register_name(dysond, owner_name, owner_addr)
    set_dest = dysond(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        ns_name,
        "--destination",
        owner_addr,
        "--from",
        owner_name,
    )
    assert (
        set_dest.get("code", 1) == 0
    ), f"set-destination failed: {json.dumps(set_dest, indent=2)}"

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_storage_get_name_resolution(owner_addr, ns_name, test_index, test_data):
    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Query using nameservice name
    get_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
        "owner": ns_name,
        "index": test_index
    })
    
    return {"get_response": get_response}
"""

    test_index = "test/name_resolution"
    test_data = '{"test": "name resolution"}'
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "ns_name": ns_name,
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
        "demo_storage_get_name_resolution",
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
    get_response = demo_result["get_response"]

    assert isinstance(
        get_response, dict
    ), f"Response should be dict, got {type(get_response)}"
    assert (
        "entry" in get_response
    ), f"Response missing 'entry' key. Keys: {list(get_response.keys())}"

    entry = get_response["entry"]
    assert (
        entry["owner"] == owner_addr
    ), f"Owner should be resolved address: expected {owner_addr}, got {entry['owner']}"
    # Data is returned as parsed JSON dict - compare parsed versions
    entry_data_parsed = (
        json.loads(entry["data"]) if isinstance(entry["data"], str) else entry["data"]
    )
    expected_data_parsed = json.loads(test_data)
    assert (
        entry_data_parsed == expected_data_parsed
    ), f"Data mismatch: expected {expected_data_parsed}, got {entry_data_parsed}"


def test_storage_get_invalid_owner(chainnet):
    """Test StorageGet query with invalid/unresolvable owner."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_storage_get_invalid_owner(invalid_owner, test_index):
    # Query with invalid owner address
    try:
        get_response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": invalid_owner,
            "index": test_index
        })
        return {"get_response": get_response, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    kwargs = json.dumps({"invalid_owner": "invalid_address", "test_index": "test/key"})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_storage_get_invalid_owner",
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
    ), f"Expected error for invalid owner, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "failed to resolve owner" in error_str
    ), f"Expected resolution error, got: {demo_result['error']}"


def test_storage_get_index_normalization(chainnet, generate_account):
    """Test StorageGet query normalizes index by removing owner prefix."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_get_norm", faucet_amount=1_000_000
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

def demo_storage_get_index_normalization(owner_addr, test_index, prefixed_index, test_data):
    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Query with index that includes owner prefix (should be normalized)
    get_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
        "owner": owner_addr,
        "index": prefixed_index
    })
    
    return {"get_response": get_response}
"""

    test_index = "test/normalized"
    test_data = '{"test": "normalization"}'
    prefixed_index = f"{owner_addr}/{test_index}"
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": test_index,
            "prefixed_index": prefixed_index,
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
        "demo_storage_get_index_normalization",
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
    get_response = demo_result["get_response"]

    assert isinstance(
        get_response, dict
    ), f"Response should be dict, got {type(get_response)}"
    assert (
        "entry" in get_response
    ), f"Response missing 'entry' key. Keys: {list(get_response.keys())}"

    entry = get_response["entry"]
    # Index in response should not include owner prefix
    assert (
        entry["index"] == test_index
    ), f"Index should be normalized: expected {test_index}, got {entry['index']}"
    assert not entry["index"].startswith(
        owner_addr
    ), f"Index should not start with owner address: {entry['index']}"
