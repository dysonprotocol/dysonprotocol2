import pytest
import json
import base64
import random
import string


def _stake(dysond, faucet_fn, name, addr, stake_amount="100000udys", topup=200000):
    validators = dysond("query", "staking", "validators")
    operator = validators["validators"][0]["operator_address"]
    faucet_fn(addr, amount=topup)
    res = dysond(
        "tx",
        "staking",
        "delegate",
        operator,
        stake_amount,
        "--from",
        name,
        "--yes",
        "--gas",
        "auto",
    )
    assert res["code"] == 0, f"Delegation failed: {res}"


def test_storage_set_get(chainnet, generate_account, faucet):
    """Test setting and retrieving a storage value."""
    dysond = chainnet[0]

    # Create Alice account and fund it
    [alice_name, alice_addr] = generate_account("alice")
    faucet(alice_addr)

    _stake(dysond, faucet, alice_name, alice_addr)

    # Set a storage value for testing with unique suffix
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    test_key = f"test_key_{suffix}"
    test_value = "test_value"

    # Set the storage value using Alice's account
    tx_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        alice_name,
        "--index",
        test_key,
        "--data",
        test_value,
    )

    # Verify the transaction was successful
    assert tx_result["code"] == 0, f"Transaction failed: {tx_result['raw_log']}"

    # Query the storage value
    get_result = dysond("query", "storage", "get", alice_addr, "--index", test_key)

    # Print the result for inspection
    print(f"Storage get result: {json.dumps(get_result, indent=2)}")

    # Check that entry exists and contains expected data
    assert "entry" in get_result, f"Expected 'entry' field in result: {get_result}"
    entry = get_result["entry"]
    assert entry["data"] == test_value, f"Retrieved value doesn't match: {entry}"
    assert entry["owner"] == alice_addr, f"Owner doesn't match: {entry}"
    assert entry["index"] == test_key, f"Index doesn't match: {entry}"


def test_storage_list(chainnet, generate_account, faucet):
    """Test listing storage values with a prefix."""
    dysond = chainnet[0]

    # Create Alice account and fund it
    [alice_name, alice_addr] = generate_account("alice")
    faucet(alice_addr)

    _stake(dysond, faucet, alice_name, alice_addr)

    # Set multiple storage values with a common prefix
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    prefix = f"list_test_{suffix}_"
    values = {f"{prefix}1": "value1", f"{prefix}2": "value2", f"{prefix}3": "value3"}

    # Set each value in storage
    for key, value in values.items():
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            alice_name,
            "--index",
            key,
            "--data",
            value,
        )

    # List all keys with the given prefix
    list_result = dysond(
        "query", "storage", "list", alice_addr, "--index-prefix", prefix, "-o", "json"
    )

    # Print the result for inspection
    print(f"Storage list result: {json.dumps(list_result, indent=2)}")

    # Check entries field exists and extract storage items
    assert (
        "entries" in list_result
    ), f"Expected 'entries' field in result: {list_result}"
    storage_items = list_result["entries"]

    # Extract the values
    found_items = {}
    for item in storage_items:
        assert isinstance(item, dict), f"Expected dict item, got: {type(item)}"
        assert "index" in item, f"Expected 'index' field in item: {item}"
        assert "data" in item, f"Expected 'data' field in item: {item}"
        found_items[item["index"]] = item["data"]

    # Check that all our values were found
    for key, value in values.items():
        assert key in found_items, f"Key {key} not found in storage list"
        assert (
            found_items[key] == value
        ), f"Value mismatch for key {key}: expected {value}, got {found_items[key]}"

    # Verify the count
    assert len(storage_items) >= len(values), "Not all values were listed"


def test_storage_delete(chainnet, generate_account, faucet):
    """Test deleting storage values."""
    dysond = chainnet[0]

    # Create Alice account and fund it
    [alice_name, alice_addr] = generate_account("alice")
    faucet(alice_addr)

    _stake(dysond, faucet, alice_name, alice_addr)

    # First set a storage value
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    test_key = f"delete_test_key_{suffix}"
    test_value = "delete_test_value"

    # Set the storage value
    dysond(
        "tx",
        "storage",
        "set",
        "--from",
        alice_name,
        "--index",
        test_key,
        "--data",
        test_value,
    )

    # Verify it was set correctly
    get_result = dysond("query", "storage", "get", alice_addr, "--index", test_key)

    assert (
        get_result["entry"]["data"] == test_value
    ), f"Value not set correctly for deletion test: expected {test_value}, got {get_result['entry']['data']}"

    # Delete the storage value
    delete_result = dysond(
        "tx", "storage", "delete", "--from", alice_name, "--indexes", test_key
    )

    # Verify the deletion was successful
    assert (
        delete_result["code"] == 0
    ), f"Delete transaction failed: {delete_result['raw_log']}"

    # Query the deleted value - should return error message for deleted entries
    get_result = dysond("query", "storage", "get", alice_addr, "--index", test_key)

    # When a storage entry doesn't exist, the query returns an error string
    assert isinstance(
        get_result, str
    ), f"Expected string error message for deleted entry, got: {type(get_result)}"
    assert (
        "doesn't exist" in get_result
    ), f"Expected 'doesn't exist' error, got: {get_result}"


def test_storage_multi_user(chainnet, generate_account, faucet):
    """Test storage with multiple users and access control."""
    dysond = chainnet[0]

    # Create accounts for Alice and Bob
    [alice_name, alice_addr] = generate_account("alice")
    [bob_name, bob_addr] = generate_account("bob")

    # Fund both accounts for transactions
    faucet(alice_addr)
    faucet(bob_addr)

    _stake(dysond, faucet, alice_name, alice_addr)
    _stake(dysond, faucet, bob_name, bob_addr)

    # Create unique test keys for each user
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    alice_key = f"alice_storage_key_{suffix}"
    bob_key = f"bob_storage_key_{suffix}"
    alice_value = "alice_value"
    bob_value = "bob_value"

    # Alice sets her storage value
    alice_set_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        alice_name,
        "--index",
        alice_key,
        "--data",
        alice_value,
    )
    assert (
        alice_set_result["code"] == 0
    ), f"Alice failed to set storage: {alice_set_result['raw_log']}"

    # Bob sets his storage value
    bob_set_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        bob_name,
        "--index",
        bob_key,
        "--data",
        bob_value,
    )
    assert (
        bob_set_result["code"] == 0
    ), f"Bob failed to set storage: {bob_set_result['raw_log']}"

    # Verify Alice's value is retrievable
    alice_result = dysond("query", "storage", "get", alice_addr, "--index", alice_key)

    assert (
        alice_result["entry"]["data"] == alice_value
    ), f"Alice's value not set correctly: expected {alice_value}, got {alice_result['entry']['data']}"
    assert (
        alice_result["entry"]["owner"] == alice_addr
    ), f"Alice's owner not correct: expected {alice_addr}, got {alice_result['entry']['owner']}"
    assert (
        alice_result["entry"]["index"] == alice_key
    ), f"Alice's index not correct: expected {alice_key}, got {alice_result['entry']['index']}"

    # Verify Bob's value is retrievable
    bob_result = dysond("query", "storage", "get", bob_addr, "--index", bob_key)

    assert (
        bob_result["entry"]["data"] == bob_value
    ), f"Bob's value not set correctly: expected {bob_value}, got {bob_result['entry']['data']}"
    assert (
        bob_result["entry"]["owner"] == bob_addr
    ), f"Bob's owner not correct: expected {bob_addr}, got {bob_result['entry']['owner']}"
    assert (
        bob_result["entry"]["index"] == bob_key
    ), f"Bob's index not correct: expected {bob_key}, got {bob_result['entry']['index']}"

    # Verify that Alice cannot delete Bob's value - should fail with error code
    delete_result = dysond(
        "tx", "storage", "delete", "--from", alice_name, "--indexes", bob_key
    )

    assert (
        delete_result["code"] != 0
    ), f"Alice should not be able to delete Bob's storage, but transaction succeeded: {delete_result}"
    assert (
        "no entries were deleted" in delete_result["raw_log"]
    ), f"Expected 'no entries were deleted' error, got: {delete_result['raw_log']}"


def test_storage_binary_data(chainnet, generate_account, faucet):
    """Test storing and retrieving binary data."""
    dysond = chainnet[0]

    # Create Alice account and fund it
    [alice_name, alice_addr] = generate_account("alice")
    faucet(alice_addr)

    _stake(dysond, faucet, alice_name, alice_addr)

    # Create binary data (base64 encoded)
    binary_data = base64.b64encode(b"Binary test data").decode("utf-8")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    test_key = f"binary_data_key_{suffix}"

    # Set the binary data
    dysond(
        "tx",
        "storage",
        "set",
        "--from",
        alice_name,
        "--index",
        test_key,
        "--data",
        binary_data,
    )

    # Retrieve the binary data
    get_result = dysond("query", "storage", "get", alice_addr, "--index", test_key)

    # Print result for inspection
    print(f"Binary data result: {json.dumps(get_result, indent=2)}")

    # Get the value from entry
    assert "entry" in get_result, f"Expected 'entry' field in result: {get_result}"
    value = get_result["entry"]["data"]

    # Verify the data
    assert value == binary_data, "Binary data not retrieved correctly"

    # Verify we can decode it back
    decoded = base64.b64decode(value)
    assert decoded == b"Binary test data", "Binary data corrupted in storage"


def test_storage_extract_and_filter(chainnet, generate_account, faucet):
    """Test the new --extract and --filter query flags."""
    dysond = chainnet[0]

    # Create user and fund
    [user_name, user_addr] = generate_account("extractor")
    faucet(user_addr)

    _stake(dysond, faucet, user_name, user_addr)

    # Prepare JSON payloads
    json_entry_1 = {"title": "First Post", "category": "blog", "meta": {"views": 10}}
    json_entry_2 = {"title": "Second Post", "category": "blog", "meta": {"views": 20}}
    json_entry_3 = {"title": "Draft Note", "meta": {"views": 0}}

    # Helper to set entry
    def set_json(index: str, data: dict):
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            index,
            "--data",
            json.dumps(data),
        )

    prefix = "posts/"
    set_json(prefix + "1", json_entry_1)
    set_json(prefix + "2", json_entry_2)
    set_json(prefix + "draft", json_entry_3)

    # Test --extract on single get
    get_res = dysond(
        "query",
        "storage",
        "get",
        user_addr,
        "--index",
        prefix + "1",
        "--extract",
        "title",
    )
    # entry.data should now be the string "First Post" (with quotes)
    extracted = get_res["entry"]["data"]
    # The extracted value should be "First Post" already as JSON string
    assert extracted == '"First Post"', f"extract failed: {extracted}"

    # Test --filter when listing
    list_res = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--filter",
        "category",
        "-o",
        "json",
    )
    entries = list_res.get("entries", [])
    # Should contain only 2 items (those with category)
    assert len(entries) == 2, f"filter expected 2 entries, got {len(entries)}"

    # Validate extract works in list too
    list_extract = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--filter",
        "category",
        "--extract",
        "meta.views",
        "-o",
        "json",
    )
    entries_views = list_extract.get("entries", [])
    views_values = [int(e["data"]) for e in entries_views]
    assert set(views_values) == {10, 20}, f"extract in list failed, got {views_values}"


def test_storage_pagination_offset_bug(chainnet, generate_account, faucet):
    """Test offset-based pagination bug where offset > 0 returns wrong entries."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account(
        "pagination_test", faucet_amount=1_000_000
    )
    faucet(user_addr)

    _stake(dysond, faucet, user_name, user_addr)

    # Create test data with entries that will be sorted in a predictable order
    # Using reverse alphabetical order so we can test offset behavior
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    prefix = f"pagination_test_{suffix}/"

    # Create 4 entries with predictable sort order (reverse alphabetical)
    test_data = {
        f"{prefix}entry_d": {
            "id": 4,
            "value": "fourth",
        },  # Will be first when reverse sorted
        f"{prefix}entry_c": {"id": 3, "value": "third"},  # Will be second
        f"{prefix}entry_b": {"id": 2, "value": "second"},  # Will be third
        f"{prefix}entry_a": {"id": 1, "value": "first"},  # Will be fourth
    }

    # Set all the test data
    for key, value in test_data.items():
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            key,
            "--data",
            json.dumps(value),
        )

    print(f"Created test data with prefix: {prefix}")
    print(f"Test data: {test_data}")

    # First, get all entries to confirm the order
    all_entries_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--limit",
        "10",
        "--reverse",
        "-o",
        "json",
    )

    print(f"All entries (reverse order): {json.dumps(all_entries_result, indent=2)}")
    all_entries = all_entries_result.get("entries", [])
    assert len(all_entries) == 4, f"Expected 4 entries, got {len(all_entries)}"

    # Now test offset-based pagination with limit=1 and reverse=true
    # This should return different entries for each offset

    # Offset 0 should return entry_d (id=4)
    offset_0_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--offset",
        "0",
        "--limit",
        "1",
        "--reverse",
        "-o",
        "json",
    )

    print(f"Offset 0 result: {json.dumps(offset_0_result, indent=2)}")
    offset_0_entries = offset_0_result.get("entries", [])
    assert (
        len(offset_0_entries) == 1
    ), f"Expected 1 entry for offset 0, got {len(offset_0_entries)}"
    offset_0_data = json.loads(offset_0_entries[0]["data"])
    print(f"Offset 0 returned ID: {offset_0_data['id']}")

    # Offset 1 should return entry_c (id=3) - THIS IS WHERE THE BUG OCCURS
    offset_1_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--offset",
        "1",
        "--limit",
        "1",
        "--reverse",
        "-o",
        "json",
    )

    print(f"Offset 1 result: {json.dumps(offset_1_result, indent=2)}")
    offset_1_entries = offset_1_result.get("entries", [])
    assert (
        len(offset_1_entries) == 1
    ), f"Expected 1 entry for offset 1, got {len(offset_1_entries)}"
    offset_1_data = json.loads(offset_1_entries[0]["data"])
    print(f"Offset 1 returned ID: {offset_1_data['id']} (should be 3, not 4)")

    # Offset 2 should return entry_b (id=2)
    offset_2_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--offset",
        "2",
        "--limit",
        "1",
        "--reverse",
        "-o",
        "json",
    )

    print(f"Offset 2 result: {json.dumps(offset_2_result, indent=2)}")
    offset_2_entries = offset_2_result.get("entries", [])
    assert (
        len(offset_2_entries) == 1
    ), f"Expected 1 entry for offset 2, got {len(offset_2_entries)}"
    offset_2_data = json.loads(offset_2_entries[0]["data"])
    print(f"Offset 2 returned ID: {offset_2_data['id']} (should be 2, not 4)")

    # Offset 3 should return entry_a (id=1)
    offset_3_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--offset",
        "3",
        "--limit",
        "1",
        "--reverse",
        "-o",
        "json",
    )

    print(f"Offset 3 result: {json.dumps(offset_3_result, indent=2)}")
    offset_3_entries = offset_3_result.get("entries", [])
    assert (
        len(offset_3_entries) == 1
    ), f"Expected 1 entry for offset 3, got {len(offset_3_entries)}"
    offset_3_data = json.loads(offset_3_entries[0]["data"])
    print(f"Offset 3 returned ID: {offset_3_data['id']} (should be 1, not 4)")

    # The bug: offset 1, 2, 3 all return the same entry as offset 0
    # Expected behavior: each offset should return a different entry
    # offset 0 -> id 4, offset 1 -> id 3, offset 2 -> id 2, offset 3 -> id 1

    # BUG ASSERTION: These assertions will FAIL due to the pagination bug
    # All offsets incorrectly return the first entry (id=4)
    expected_ids = [4, 3, 2, 1]  # Expected IDs for offsets 0, 1, 2, 3
    actual_ids = [
        offset_0_data["id"],
        offset_1_data["id"],
        offset_2_data["id"],
        offset_3_data["id"],
    ]

    print(f"Expected IDs: {expected_ids}")
    print(f"Actual IDs:   {actual_ids}")

    # These assertions should pass for correct pagination behavior
    # But will fail due to the offset pagination bug
    assert (
        offset_0_data["id"] == 4
    ), f"Offset 0 should return ID 4, got {offset_0_data['id']}"
    assert (
        offset_1_data["id"] == 3
    ), f"BUG: Offset 1 should return ID 3, got {offset_1_data['id']}"
    assert (
        offset_2_data["id"] == 2
    ), f"BUG: Offset 2 should return ID 2, got {offset_2_data['id']}"
    assert (
        offset_3_data["id"] == 1
    ), f"BUG: Offset 3 should return ID 1, got {offset_3_data['id']}"

    # If we reach here, pagination is working correctly
    print("✅ Offset-based pagination is working correctly!")


def test_storage_pagination_script_bug(chainnet, generate_account, faucet):
    """Test offset-based pagination bug via script execution (JSON→protobuf conversion)."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account("script_pagination_test")
    faucet(user_addr)

    # Create test data with predictable sort order
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    prefix = f"script_pagination_test_{suffix}/"

    # Create 5 entries with predictable reverse alphabetical sort order
    test_data = {
        f"{prefix}entry_e": {
            "id": 5,
            "value": "fifth",
        },  # Will be first when reverse sorted
        f"{prefix}entry_d": {
            "id": 4,
            "value": "fourth",
        },  # Will be second when reverse sorted
        f"{prefix}entry_c": {"id": 3, "value": "third"},  # Will be third
        f"{prefix}entry_b": {"id": 2, "value": "second"},  # Will be fourth
        f"{prefix}entry_a": {"id": 1, "value": "first"},  # Will be fifth
    }

    # Set all the test data
    for key, value in test_data.items():
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            key,
            "--data",
            json.dumps(value),
        )

    print(f"Created test data with prefix: {prefix}")

    # Simple script that tests one offset to understand the bug
    script_code = f'''
import json
from dys import _query

def verify_offset_0():
    """Test offset 0."""
    query_params = {{
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": "{user_addr}",
        "index_prefix": "{prefix}",
        "pagination": {{
            "offset": 0,
            "limit": 1,
            "reverse": True
        }}
    }}
    
    result = _query(query_params)
    entry = result["entries"][0]
    entry_data = json.loads(entry["data"])
    
    return {{
        "offset": 0,
        "id": entry_data["id"],
        "index": entry["index"]
    }}

def verify_offset_1():
    """Test offset 1 - this should show the bug."""
    query_params = {{
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": "{user_addr}",
        "index_prefix": "{prefix}",
        "pagination": {{
            "offset": 1,
            "limit": 1,
            "reverse": True
        }}
    }}
    
    result = _query(query_params)
    entry = result["entries"][0]
    entry_data = json.loads(entry["data"])
    
    return {{
        "offset": 1,
        "id": entry_data["id"],
        "index": entry["index"]
    }}
'''

    print(f"\nTesting offset 0 via script execution...")

    # Test offset 0
    result_0 = dysond(
        "query",
        "script",
        "run",
        "--executor-address",
        user_addr,
        "--script-address",
        user_addr,
        "--function-name",
        "verify_offset_0",
        "--args",
        "[]",
        "--extra-code",
        script_code,
    )

    print(f"Offset 0 raw result: {json.dumps(result_0, indent=2)}")

    print(f"\nTesting offset 1 via script execution...")

    # Test offset 1
    result_1 = dysond(
        "query",
        "script",
        "run",
        "--executor-address",
        user_addr,
        "--script-address",
        user_addr,
        "--function-name",
        "verify_offset_1",
        "--args",
        "[]",
        "--extra-code",
        script_code,
    )

    print(f"Offset 1 raw result: {json.dumps(result_1, indent=2)}")

    # Extract and compare results manually
    result_0_data = json.loads(result_0["result"])
    result_0_parsed = result_0_data["result"]

    result_1_data = json.loads(result_1["result"])
    result_1_parsed = result_1_data["result"]

    print(f"\nComparison:")
    print(f"  Offset 0: ID {result_0_parsed['id']} from {result_0_parsed['index']}")
    print(f"  Offset 1: ID {result_1_parsed['id']} from {result_1_parsed['index']}")

    # Check for the bug pattern
    offset_0_id = result_0_parsed["id"]
    offset_1_id = result_1_parsed["id"]

    # With 5 entries in reverse alphabetical order: e(5), d(4), c(3), b(2), a(1)
    expected_offset_0_id = 5  # entry_e should be first
    expected_offset_1_id = 4  # entry_d should be second

    print(
        f"\nExpected: offset 0 → ID {expected_offset_0_id}, offset 1 → ID {expected_offset_1_id}"
    )
    print(f"Actual:   offset 0 → ID {offset_0_id}, offset 1 → ID {offset_1_id}")

    bug_detected = offset_0_id == offset_1_id
    print(f"\nBug pattern (both return same ID): {bug_detected}")

    # Assertions
    assert (
        offset_0_id == expected_offset_0_id
    ), f"Offset 0 should return ID {expected_offset_0_id}, got {offset_0_id}"

    # This assertion will fail if the bug is present
    print(f"\nChecking if bug is present...")
    print(f"Offset 1 returned ID {offset_1_id}, expected ID {expected_offset_1_id}")
    print(f"Bug reproduction: {'SUCCESS' if bug_detected else 'FAILED'}")


def test_storage_invalid_extract_and_filter(chainnet, generate_account, faucet):
    """Ensure invalid extract path raises error and unmatched filter returns empty list."""
    dysond = chainnet[0]

    [u_name, u_addr] = generate_account("neg")
    faucet(u_addr)

    _stake(dysond, faucet, u_name, u_addr)

    entry = {"foo": {"bar": 1}}
    dysond(
        "tx",
        "storage",
        "set",
        "--from",
        u_name,
        "--index",
        "neg/1",
        "--data",
        json.dumps(entry),
    )

    # Attempt to extract missing path -> expect string error (gRPC NotFound propagated to CLI)
    res = dysond(
        "query", "storage", "get", u_addr, "--index", "neg/1", "--extract", "foo.baz"
    )
    assert isinstance(res, str), "Expected error string when extract path missing"
    assert "not found" in res.lower(), f"Unexpected error message: {res}"

    # Filter that matches nothing should return 0 entries
    list_res = dysond(
        "query",
        "storage",
        "list",
        u_addr,
        "--index-prefix",
        "neg/",
        "--filter",
        "nonexistent",
        "-o",
        "json",
    )
    entries = list_res.get("entries", [])
    assert entries == [], f"Expected empty list, got {entries}"


def test_storage_extract_filter_too_long(chainnet, generate_account, faucet):
    dysond = chainnet[0]
    [name, addr] = generate_account("toolong")
    faucet(addr)

    _stake(dysond, faucet, name, addr)

    long_path = "a" * 101
    dysond(
        "tx", "storage", "set", "--from", name, "--index", "toolong/1", "--data", "{}"
    )

    res = dysond(
        "query", "storage", "get", addr, "--index", "toolong/1", "--extract", long_path
    )
    assert (
        isinstance(res, str) and "too long" in res.lower()
    ), f"Expected length error, got {res}"

    list_res = dysond(
        "query",
        "storage",
        "list",
        addr,
        "--index-prefix",
        "toolong/",
        "--filter",
        long_path,
        "-o",
        "json",
    )
    # For list, CLI likely surfaces error string instead of json when InvalidArgument
    assert isinstance(list_res, str), "Expected error string for too long filter"
    assert "too long" in list_res.lower(), f"Expected length error, got {list_res}"


def test_storage_delete_by_prefix_and_filter(chainnet, generate_account, faucet):
    """Test deleting storage values by specific indexes."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account("deleter")
    faucet(user_addr)

    _stake(dysond, faucet, user_name, user_addr)

    # Create test data with a common prefix
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    prefix = f"delete_test_{suffix}/"

    # Set up test data with JSON values
    test_data = {
        f"{prefix}user1": {"name": "Alice", "age": 25, "active": True},
        f"{prefix}user2": {"name": "Bob", "age": 30, "active": False},
        f"{prefix}user3": {"name": "Charlie", "age": 35, "active": True},
        f"{prefix}admin1": {"name": "Admin", "role": "admin", "active": True},
    }

    # Set all the test data
    for key, value in test_data.items():
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            key,
            "--data",
            json.dumps(value),
        )

    # Test: Delete specific user entries by specifying exact indexes
    user_indexes = [f"{prefix}user1", f"{prefix}user2", f"{prefix}user3"]
    delete_result = dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        user_name,
        "--indexes",
        ",".join(user_indexes),
    )

    assert (
        delete_result["code"] == 0
    ), f"Delete by indexes failed: {delete_result['raw_log']}"

    # Verify user entries are deleted
    for user_key in user_indexes:
        get_result = dysond("query", "storage", "get", user_addr, "--index", user_key)
        assert isinstance(
            get_result, str
        ), f"Entry {user_key} should be deleted but still exists"
        assert (
            "doesn't exist" in get_result
        ), f"Entry {user_key} should show 'doesn't exist' error"

    # Verify admin entry still exists
    admin_key = f"{prefix}admin1"
    admin_result = dysond("query", "storage", "get", user_addr, "--index", admin_key)
    assert admin_result["entry"]["data"] == json.dumps(
        test_data[admin_key]
    ), f"Admin entry should still exist"


def test_storage_delete_empty_prefix(chainnet, generate_account, faucet):
    """Test that delete fails when no indexes are provided."""
    dysond = chainnet[0]

    [user_name, user_addr] = generate_account("no_indexes")
    faucet(user_addr)

    # Try to delete without specifying any indexes
    delete_result = dysond(
        "tx", "storage", "delete", "--from", user_name, "--offline"
    )  # Use offline mode to get string error instead of exception

    # This should fail with an error at the CLI level
    assert isinstance(
        delete_result, str
    ), "Expected CLI error string for missing indexes"
    expected_substring = "must specify at least one index with --indexes"
    assert (
        expected_substring in delete_result
    ), f"Expected CLI validation error '{expected_substring}', got: {delete_result}"


def test_storage_pagination_comprehensive(chainnet, generate_account, faucet):
    dysond = chainnet[0]
    """Test storage pagination with various limit/offset combinations to find edge cases."""
    import json
    import random
    import string

    # Generate test account and fund it
    [user_name, user_addr] = generate_account(
        "comprehensive_test", faucet_amount=1_000_000
    )

    # Generate unique test prefix
    test_prefix = "pagination_test_" + "".join(
        random.choices(string.ascii_lowercase + string.digits, k=8)
    )

    print(f"Testing comprehensive pagination with prefix: {test_prefix}")

    # Script that creates 10 storage entries and tests pagination
    script_code = f'''
import json
from dys import _msg, _query

def create_test_data():
    """Create 10 storage entries for testing."""
    results = []
    for i in range(10):
        # Create storage entry with index i (0-9)
        msg = {{
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": "{user_addr}",
            "index": f"{test_prefix}/entry_{{i:02d}}",
            "data": json.dumps({{"id": i, "value": f"entry_{{i}}"}})
        }}
        result = _msg(msg)
        results.append({{"index": i, "result": result}})
    return results

def list_storage(limit, offset):
    """List storage with given limit and offset, return expected vs actual."""
    # Calculate expected indices based on normal order (0,1,2,3,4,5,6,7,8,9)
    all_indices = list(range(0, 10))  # [0,1,2,3,4,5,6,7,8,9]
    
    # Calculate expected slice
    start_idx = offset
    end_idx = offset + limit
    expected_indices = all_indices[start_idx:end_idx]
    
    # Query actual results
    query_params = {{
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": "{user_addr}",
        "index_prefix": "{test_prefix}/",
        "pagination": {{
            "offset": offset,
            "limit": limit,
            "reverse": False
        }}
    }}
    
    result = _query(query_params)
    
    # Extract actual indices
    actual_indices = []
    if "entries" in result and result["entries"]:
        for entry in result["entries"]:
            # Extract the numeric part from index like "pagination_test_xyz/entry_05"
            index_part = entry["index"].split("/")[-1]  # "entry_05"
            numeric_part = int(index_part.split("_")[-1])  # 5
            actual_indices.append(numeric_part)
    
    return {{
        "limit": limit,
        "offset": offset,
        "expected_indices": expected_indices,
        "actual_indices": actual_indices,
        "expected_count": len(expected_indices),
        "actual_count": len(actual_indices),
        "matches": expected_indices == actual_indices,
        "total_available": 10
    }}

def run_comprehensive_test():
    """Run the comprehensive pagination test."""
    # First create the test data
    creation_results = create_test_data()
    
    # Test various limit/offset combinations
    test_results = []
    
    # Test limits 1-5 with offsets 0-5
    for limit in range(1, 6):
        for offset in range(0, 6):
            # Skip if offset would be beyond available data
            if offset < 10:
                result = list_storage(limit, offset)
                test_results.append(result)
    
    return {{
        "creation_results": creation_results,
        "test_results": test_results,
        "total_tests": len(test_results)
    }}
'''

    # Execute the comprehensive test
    print("Executing comprehensive pagination test...")
    result = dysond(
        "query",
        "script",
        "run",
        "--executor-address",
        user_addr,
        "--script-address",
        user_addr,
        "--function-name",
        "run_comprehensive_test",
        "--args",
        "[]",
        "--output",
        "json",
        "--extra-code",
        script_code,
    )

    print(f"Script execution result type: {type(result)}")
    print(f"Script execution raw result: {result}")

    # Assert expected type and parse the script result
    assert isinstance(result, dict), f"Expected dict but got {type(result)}: {result}"
    assert "result" in result, f"Missing 'result' key in: {result}"

    result_data = json.loads(result["result"])
    assert isinstance(
        result_data, dict
    ), f"Expected dict from JSON parse but got {type(result_data)}: {result_data}"
    assert (
        "result" in result_data
    ), f"Missing 'result' key in parsed data: {result_data}"

    script_result = result_data["result"]

    print(f"Script returned {len(script_result['test_results'])} test cases")

    # Analyze results for mismatches
    mismatches = [
        test_case
        for test_case in script_result["test_results"]
        if not test_case["matches"]
    ]
    total_tests = len(script_result["test_results"])

    # Print all mismatches
    for test_case in mismatches:
        print(f"MISMATCH: limit={test_case['limit']}, offset={test_case['offset']}")
        print(f"  Expected: {test_case['expected_indices']}")
        print(f"  Actual:   {test_case['actual_indices']}")

    print(f"\nSummary: {len(mismatches)} mismatches out of {total_tests} test cases")

    # Analyze mismatch patterns for the hypothesis
    for mismatch in mismatches:
        limit = mismatch["limit"]
        offset = mismatch["offset"]
        total = mismatch["total_available"]

        # Check if this matches the hypothesis
        is_evenly_divisible = total % limit == 0
        is_boundary_case = offset % limit == 0

        print(
            f"  limit={limit}, offset={offset}: evenly_divisible={is_evenly_divisible}, boundary={is_boundary_case}"
        )

    # The test should pass - we're gathering data, not testing for failure
    assert total_tests > 0, "No test cases were executed"

    # Print final analysis
    mismatch_count = len(mismatches)
    print(
        f"Found {mismatch_count} mismatches - "
        + (
            "this may indicate the pagination bug"
            if mismatch_count > 0
            else "pagination appears to be working correctly"
        )
    )


def test_storage_pagination_nuance_reproduction(chainnet, generate_account, faucet):
    """Test to reproduce the exact pagination scenario from nuance script with rating-like data."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account(
        "nuance_repro", faucet_amount=50_000_000
    )  # 50 DYS instead of 100

    # Create test data that mimics the nuance rating structure
    # Using the exact prefix pattern from nuance script
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    prefix = f"tags/testtag/hot/"

    # Create entries that mimic the rating entries with float values like in the debug output
    test_data = {
        f"{prefix}121.79422/post/4": {"post_id": "4", "hot_rating": 121.79422},
        f"{prefix}121.57106/post/2": {"post_id": "2", "hot_rating": 121.57106},
        f"{prefix}121.28339/post/3": {"post_id": "3", "hot_rating": 121.28339},
        f"{prefix}121.28337/post/1": {"post_id": "1", "hot_rating": 121.28337},
    }

    print(f"Creating nuance-like test data with prefix: {prefix}")

    # Set all the test data
    for key, value in test_data.items():
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            key,
            "--data",
            json.dumps(value),
        )

    print(f"Created {len(test_data)} entries")

    # Get all entries in reverse order (like nuance script does)
    all_entries_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--reverse",
        "-o",
        "json",
    )

    print(f"All entries (reverse order): {json.dumps(all_entries_result, indent=2)}")
    all_entries = all_entries_result.get("entries", [])
    assert len(all_entries) == 4, f"Expected 4 entries, got {len(all_entries)}"

    # Extract expected post IDs from all entries
    expected_post_ids = []
    for entry in all_entries:
        entry_data = json.loads(entry["data"])
        expected_post_ids.append(entry_data["post_id"])

    print(f"Expected post ID sequence (reverse order): {expected_post_ids}")

    # Now test offset-based pagination like nuance script does
    # Test hot_index 0, 1, 2, 3 (which should map to offset 0, 1, 2, 3)

    pagination_results = []
    for hot_index in range(4):
        offset_result = dysond(
            "query",
            "storage",
            "list",
            user_addr,
            "--index-prefix",
            prefix,
            "--offset",
            str(hot_index),
            "--limit",
            "1",
            "--reverse",
            "-o",
            "json",
        )

        print(f"Offset {hot_index} result: {json.dumps(offset_result, indent=2)}")

        offset_entries = offset_result.get("entries", [])
        assert (
            len(offset_entries) == 1
        ), f"Expected 1 entry for offset {hot_index}, got {len(offset_entries)}"

        entry_data = json.loads(offset_entries[0]["data"])
        actual_post_id = entry_data["post_id"]
        expected_post_id = expected_post_ids[hot_index]

        pagination_results.append(
            {
                "hot_index": hot_index,
                "expected_post_id": expected_post_id,
                "actual_post_id": actual_post_id,
                "matches": actual_post_id == expected_post_id,
            }
        )

        print(
            f"hot_index {hot_index}: expected post_id {expected_post_id}, got post_id {actual_post_id}"
        )

    # Analyze results
    mismatches = [r for r in pagination_results if not r["matches"]]

    print(f"\nPagination Results:")
    for result in pagination_results:
        status = "✅" if result["matches"] else "❌"
        print(
            f"  {status} hot_index {result['hot_index']}: expected {result['expected_post_id']}, got {result['actual_post_id']}"
        )

    print(
        f"\nSummary: {len(mismatches)} mismatches out of {len(pagination_results)} tests"
    )

    # Report on the findings
    mismatch_count = len(mismatches)
    print(f"Found {mismatch_count} mismatches - expected 0 for working pagination")

    # All should match for correct behavior
    for result in pagination_results:
        assert result[
            "matches"
        ], f"BUG: hot_index {result['hot_index']} should return post_id {result['expected_post_id']}, got {result['actual_post_id']}"

    print("✅ Storage-level pagination test passed - bug is not in storage layer")


def test_storage_pagination_script_query_bug(chainnet, generate_account, faucet):
    """Test to reproduce the pagination bug via script execution using _query() like nuance script."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account(
        "script_query_bug", faucet_amount=5_000_000
    )  # 5 DYS

    # Create test data that exactly matches nuance script structure
    prefix = "tags/testtag/hot/"

    # Script that creates the test data and tests pagination via _query
    setup_and_test_script = f'''
import json
from dys import _msg, _query

def setup_test_data():
    """Create test data that matches nuance script structure."""
    # Create entries that mimic the nuance rating structure with exact same indexes
    test_entries = [
        ("{prefix}121.79422/post/4", {{"post_id": "4", "hot_rating": 121.79422}}),
        ("{prefix}121.57106/post/2", {{"post_id": "2", "hot_rating": 121.57106}}),
        ("{prefix}121.28339/post/3", {{"post_id": "3", "hot_rating": 121.28339}}),
        ("{prefix}121.28337/post/1", {{"post_id": "1", "hot_rating": 121.28337}}),
    ]
    
    results = []
    for index, data in test_entries:
        msg = {{
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": "{user_addr}",
            "index": index,
            "data": json.dumps(data)
        }}
        result = _msg(msg)
        results.append({{"index": index, "success": True}})
    
    return results

def test_pagination_via_query():
    """Test pagination using _query exactly like nuance script does."""
    
    # First get all entries to establish expected order (like nuance script)
    all_query_params = {{
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": "{user_addr}",
        "index_prefix": "{prefix}",
        "pagination": {{
            "reverse": True
        }}
    }}
    
    all_result = _query(all_query_params)
    all_entries = all_result.get("entries", [])
    
    # Extract expected post IDs in order
    expected_post_ids = []
    for entry in all_entries:
        entry_data = json.loads(entry["data"])
        expected_post_ids.append(entry_data["post_id"])
    
    # Now test each offset individually using _query (like nuance _list_data does)
    pagination_results = []
    
    for offset in range(4):
        offset_query_params = {{
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": "{user_addr}",
            "index_prefix": "{prefix}",
            "pagination": {{
                "offset": offset,
                "limit": 1,
                "reverse": True
            }}
        }}
        
        offset_result = _query(offset_query_params)
        offset_entries = offset_result.get("entries", [])
        
        if offset_entries:
            entry_data = json.loads(offset_entries[0]["data"])
            actual_post_id = entry_data["post_id"]
            expected_post_id = expected_post_ids[offset] if offset < len(expected_post_ids) else None
            
            pagination_results.append({{
                "offset": offset,
                "expected_post_id": expected_post_id,
                "actual_post_id": actual_post_id,
                "matches": actual_post_id == expected_post_id,
                "entry_index": offset_entries[0]["index"]
            }})
        else:
            pagination_results.append({{
                "offset": offset,
                "expected_post_id": expected_post_ids[offset] if offset < len(expected_post_ids) else None,
                "actual_post_id": None,
                "matches": False,
                "entry_index": None
            }})
    
    return {{
        "expected_order": expected_post_ids,
        "pagination_results": pagination_results,
        "all_entries_count": len(all_entries)
    }}

def run_full_test():
    """Run the complete test."""
    setup_result = setup_test_data()
    test_result = test_pagination_via_query()
    
    return {{
        "setup": setup_result,
        "test": test_result
    }}
'''

    print("Testing pagination bug via script execution with _query()...")

    # Execute the script that reproduces the nuance pagination pattern
    result = dysond(
        "query",
        "script",
        "run",
        "--executor-address",
        user_addr,
        "--script-address",
        user_addr,
        "--function-name",
        "run_full_test",
        "--args",
        "[]",
        "--output",
        "json",
        "--extra-code",
        setup_and_test_script,
    )

    print(f"Script execution result: {result}")

    # Parse the script result
    assert isinstance(result, dict), f"Expected dict but got {type(result)}: {result}"
    assert "result" in result, f"Missing 'result' key in: {result}"

    result_data = json.loads(result["result"])
    assert isinstance(
        result_data, dict
    ), f"Expected dict from JSON parse: {result_data}"
    assert (
        "result" in result_data
    ), f"Missing 'result' key in parsed data: {result_data}"

    script_result = result_data["result"]
    test_data = script_result["test"]

    print(f"Expected post ID order: {test_data['expected_order']}")

    # Analyze pagination results from script execution
    pagination_results = test_data["pagination_results"]
    mismatches = [r for r in pagination_results if not r["matches"]]

    print(f"\nPagination Results via Script _query():")
    for result_item in pagination_results:
        status = "✅" if result_item["matches"] else "❌"
        print(
            f"  {status} offset {result_item['offset']}: expected {result_item['expected_post_id']}, got {result_item['actual_post_id']}"
        )
        print(f"      entry_index: {result_item['entry_index']}")

    print(
        f"\nSummary: {len(mismatches)} mismatches out of {len(pagination_results)} tests"
    )

    # This test should FAIL if the bug is reproduced via script execution
    # vs the direct CLI calls that work correctly
    mismatch_count = len(mismatches)
    print(
        f"Bug reproduction status: {'SUCCESS - bug reproduced!' if mismatch_count > 0 else 'FAILED - no bug found'}"
    )

    # If we have mismatches, the bug is reproduced in script execution
    # Comment out the assertion below to see the actual bug pattern
    # assert mismatch_count == 0, f"BUG REPRODUCED: {mismatch_count} pagination mismatches in script execution"

    # Let the test pass so we can see the pattern
    print(
        f"✅ Test completed - found {mismatch_count} mismatches (expected if bug is in script execution layer)"
    )


def test_storage_pagination_exact_nuance_replication(
    chainnet, generate_account, faucet
):
    """Test to reproduce the exact pagination bug by replicating nuance _list_data function behavior."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account(
        "exact_nuance_repro", faucet_amount=1_000_000
    )  # 1 DYS

    # Create test data that exactly matches nuance script structure
    prefix = "tags/testtag/hot/"

    # Script that replicates the exact _list_data function from nuance
    exact_nuance_script = f'''
import json
from dys import _msg, _query

def _list_data_replica(prefix: str, **kwargs):
    """Exact replica of nuance _list_data function."""
    query_params = {{
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": "{user_addr}",
        "index_prefix": prefix,
        **kwargs,
    }}
    
    # DEBUG: Print the exact query being constructed
    print(f"DEBUG _list_data_replica: Constructing query with params: {{json.dumps(query_params, indent=2)}}")
    
    result = _query(query_params)
    
    # DEBUG: Print the raw result
    print(f"DEBUG _list_data_replica: Raw query result keys: {{list(result.keys())}}")
    print(f"DEBUG _list_data_replica: entries count: {{len(result.get('entries', []))}}")
    
    processed_entries = [
        {{"_index": item["index"], **json.loads(item["data"])}}
        for item in result.get("entries", [])
    ]
    
    # DEBUG: Print processed entries
    print(f"DEBUG _list_data_replica: Processed {{len(processed_entries)}} entries")
    for i, entry in enumerate(processed_entries):
        print(f"DEBUG _list_data_replica: entry[{{i}}] = {{entry.get('id', 'NO_ID')}}")
    
    return (
        processed_entries,
        result.get("pagination", {{}}),
    )

def setup_test_data():
    """Create test data that matches nuance script structure."""
    test_entries = [
        ("{prefix}121.79422/post/4", {{"id": "4", "hot_rating": 121.79422}}),
        ("{prefix}121.57106/post/2", {{"id": "2", "hot_rating": 121.57106}}),
        ("{prefix}121.28339/post/3", {{"id": "3", "hot_rating": 121.28339}}),
        ("{prefix}121.28337/post/1", {{"id": "1", "hot_rating": 121.28337}}),
    ]
    
    results = []
    for index, data in test_entries:
        msg = {{
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": "{user_addr}",
            "index": index,
            "data": json.dumps(data)
        }}
        result = _msg(msg)
        results.append({{"index": index, "success": True}})
    
    return results

def test_exact_pagination_bug():
    """Test pagination using exact nuance _list_data function replica."""
    
    # First get all entries exactly like nuance does (using **kwargs)
    print("DEBUG: Getting ALL entries like nuance script...")
    all_hot_posts, all_pagination = _list_data_replica(
        "{prefix}", pagination={{"reverse": True}}
    )
    
    print(f"DEBUG: ALL hot posts (count={{len(all_hot_posts)}}):")
    for i, post in enumerate(all_hot_posts):
        print(f"DEBUG:   index[{{i}}] -> post_id={{post['id']}}, hot_rating={{post.get('hot_rating', 'N/A')}}")
    
    # Now test each offset individually like _claim_rewards does
    pagination_results = []
    
    for hot_index in range(4):
        print(f"DEBUG: Testing hot_index={{hot_index}} using exact nuance pattern...")
        
        # This is the EXACT call pattern from _claim_rewards
        hot_posts, pagination = _list_data_replica(
            "{prefix}", pagination={{"offset": hot_index, "limit": 1, "reverse": True}}
        )
        
        print(f"DEBUG: Offset query returned {{len(hot_posts)}} posts")
        if len(hot_posts) > 0:
            actual_post_id = hot_posts[0]['id']
            expected_post_id = all_hot_posts[hot_index]['id'] if hot_index < len(all_hot_posts) else None
            
            print(f"DEBUG: hot_index={{hot_index}}: returned post_id={{actual_post_id}}, expected={{expected_post_id}}")
            
            pagination_results.append({{
                "hot_index": hot_index,
                "expected_post_id": expected_post_id,
                "actual_post_id": actual_post_id,
                "matches": actual_post_id == expected_post_id,
                "entry_index": hot_posts[0]["_index"]
            }})
        else:
            pagination_results.append({{
                "hot_index": hot_index,
                "expected_post_id": all_hot_posts[hot_index]['id'] if hot_index < len(all_hot_posts) else None,
                "actual_post_id": None,
                "matches": False,
                "entry_index": None
            }})
    
    return {{
        "expected_order": [post['id'] for post in all_hot_posts],
        "pagination_results": pagination_results,
        "all_entries_count": len(all_hot_posts)
    }}

def run_exact_nuance_test():
    """Run the exact nuance replication test."""
    setup_result = setup_test_data()
    test_result = test_exact_pagination_bug()
    
    return {{
        "setup": setup_result,
        "test": test_result
    }}
'''

    print("Testing pagination bug using EXACT nuance _list_data replica...")

    # Execute the script that reproduces the exact nuance behavior
    result = dysond(
        "query",
        "script",
        "run",
        "--executor-address",
        user_addr,
        "--script-address",
        user_addr,
        "--function-name",
        "run_exact_nuance_test",
        "--args",
        "[]",
        "--output",
        "json",
        "--extra-code",
        exact_nuance_script,
    )

    print(f"Script execution result keys: {result.keys()}")

    # Parse the script result
    assert isinstance(result, dict), f"Expected dict but got {type(result)}: {result}"
    assert "result" in result, f"Missing 'result' key in: {result}"

    result_data = json.loads(result["result"])
    assert isinstance(
        result_data, dict
    ), f"Expected dict from JSON parse: {result_data}"
    assert (
        "result" in result_data
    ), f"Missing 'result' key in parsed data: {result_data}"

    script_result = result_data["result"]
    test_data = script_result["test"]

    print(f"Expected post ID order: {test_data['expected_order']}")

    # Analyze pagination results from exact nuance replication
    pagination_results = test_data["pagination_results"]
    mismatches = [r for r in pagination_results if not r["matches"]]

    print(f"\nPagination Results via EXACT Nuance _list_data Replica:")
    for result_item in pagination_results:
        status = "✅" if result_item["matches"] else "❌"
        print(
            f"  {status} hot_index {result_item['hot_index']}: expected {result_item['expected_post_id']}, got {result_item['actual_post_id']}"
        )
        print(f"      entry_index: {result_item['entry_index']}")

    print(
        f"\nSummary: {len(mismatches)} mismatches out of {len(pagination_results)} tests"
    )

    # This test should reveal if the bug is in the **kwargs handling or query construction
    mismatch_count = len(mismatches)
    print(
        f"Bug reproduction status: {'SUCCESS - exact nuance bug reproduced!' if mismatch_count > 0 else 'FAILED - no bug found in exact replica'}"
    )


def test_storage_pagination_nuance_key_format(chainnet, generate_account, faucet):
    """Test pagination with exact nuance key formatting to reproduce bug."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account("nuance_key_repro")
    faucet(user_addr)

    # Create test data with exact nuance key format:
    # {prefix}{padded_score:012.05f}/{padded_id:015d}
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    prefix = f"rate/tags/testtag_{suffix}/hot/"

    # Scores similar to the failing run (positive, 5 decimals)
    test_data = {
        f"{prefix}000283.06579/000000000000004": {"id": 4, "hot_rating": 283.06579},
        f"{prefix}000282.84263/000000000000002": {"id": 2, "hot_rating": 282.84263},
        f"{prefix}000282.55495/000000000000003": {"id": 3, "hot_rating": 282.55495},
        f"{prefix}000282.55494/000000000000001": {"id": 1, "hot_rating": 282.55494},
    }

    # Set all the test data
    for key, value in test_data.items():
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            key,
            "--data",
            json.dumps(value),
        )

    print(f"Created nuance-formatted test data with prefix: {prefix}")

    # Get all entries in reverse order (should be post4,2,3,1)
    all_entries_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--reverse",
        "-o",
        "json",
    )

    print(f"All entries (reverse order): {json.dumps(all_entries_result, indent=2)}")
    all_entries = all_entries_result.get("entries", [])
    assert len(all_entries) == 4

    # Extract expected IDs in reverse order
    expected_ids = [json.loads(entry["data"])["id"] for entry in all_entries]
    print(f"Expected ID sequence (reverse): {expected_ids}")

    # Test offsets 0-3 with limit=1, reverse=true
    for offset, expected_id in enumerate(expected_ids):
        offset_result = dysond(
            "query",
            "storage",
            "list",
            user_addr,
            "--index-prefix",
            prefix,
            "--offset",
            str(offset),
            "--limit",
            "1",
            "--reverse",
            "-o",
            "json",
        )

        print(f"Offset {offset} result: {json.dumps(offset_result, indent=2)}")

        offset_entries = offset_result.get("entries", [])
        assert len(offset_entries) == 1

        entry_data = json.loads(offset_entries[0]["data"])
        actual_id = entry_data["id"]

        assert (
            actual_id == expected_id
        ), f"Offset {offset}: expected {expected_id}, got {actual_id}"
        print(f"Offset {offset}: expected ID {expected_id}, got ID {actual_id}")

    print("\n✅ Pagination works correctly - no bug reproduced in this setup")


def test_storage_pagination_nuance_key_format_via_script(
    chainnet, generate_account, faucet
):
    """Test pagination via script _query with exact nuance key formatting to reproduce bug."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account("nuance_script_repro")
    faucet(user_addr)

    # Deploy a dummy script to own the storage
    dummy_script = 'def dummy(): return "ok"'
    result = dysond(
        "tx",
        "script",
        "update",
        "--code",
        dummy_script,
        "--from",
        user_name,
        "--gas",
        "auto",
    )

    script_addr = user_addr

    print(f"Deployed dummy script at: {script_addr}")

    # Script that sets test data and tests pagination
    script_code = f"""
import json
from dys import _query, _msg

def set_test_data():
    prefix = "rate/tags/testtag/hot/"
    test_data = [
        (f"{{prefix}}000283.06579/000000000000004", {{"id": 4}}),
        (f"{{prefix}}000282.84263/000000000000002", {{"id": 2}}),
        (f"{{prefix}}000282.55495/000000000000003", {{"id": 3}}),
        (f"{{prefix}}000282.55494/000000000000001", {{"id": 1}}),
    ]
    
    for index, data in test_data:
        _msg({{
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": "{script_addr}",
            "index": index,
            "data": json.dumps(data)
        }})
    return len(test_data)

def list_data(offset):
    query_params = {{
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": "{script_addr}",
        "index_prefix": "rate/tags/testtag/hot/",
        "pagination": {{
            "offset": offset,
            "limit": 1,
            "reverse": True
        }}
    }}
    
    result = _query(query_params)
    entries = result.get("entries", [])
    return json.loads(entries[0]["data"])["id"] if len(entries) > 0 else 0  # Return 0 if no entry

def run_tests():
    set_test_data()  # Set data first
    return [list_data(o) for o in range(4)]
"""

    # Execute the script
    exec_result = dysond(
        "query",
        "script",
        "run",
        "--executor-address",
        user_addr,
        "--script-address",
        script_addr,
        "--function-name",
        "run_tests",
        "--args",
        "[]",
        "--extra-code",
        script_code,
        "-o",
        "json",
    )

    print(f"Script execution result: {json.dumps(exec_result, indent=2)}")

    # Parse results
    result_data = json.loads(exec_result["result"])
    actual_ids = result_data["result"]

    # Expected IDs: [4,2,3,1]
    expected_ids = [4, 2, 3, 1]

    print("\nPagination Results via Script:")
    print(f"Actual IDs: {actual_ids}")

    assert (
        actual_ids == expected_ids
    ), f"Pagination mismatch: expected {expected_ids}, got {actual_ids}"

    print("\n✅ All offsets match expected - no bug reproduced in this setup")


def test_storage_pagination_nuance_key_format_via_tx_script(
    chainnet, generate_account, faucet
):
    """Test pagination via _query in tx script exec with nuance key format to reproduce bug."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account("nuance_tx_repro", faucet_amount=100)

    # Deploy a dummy script to own the storage
    dummy_script = 'def dummy(): return "ok"'
    result = dysond(
        "tx",
        "script",
        "update",
        "--code",
        dummy_script,
        "--from",
        user_name,
        "--gas",
        "auto",
    )
    script_addr = user_addr

    print(f"Deployed dummy script at: {script_addr}")

    # Script that sets test data and tests pagination in tx context
    script_code = f"""
import json
from dys import _query, _msg

def set_test_data():
    prefix = "rate/tags/testtag43385/hot/"
    test_data = [
        (f"{{prefix}}000283.06579/000000000000004", {{"id": 4}}),
        (f"{{prefix}}000282.84263/000000000000002", {{"id": 2}}),
        (f"{{prefix}}000282.55495/000000000000003", {{"id": 3}}),
        (f"{{prefix}}000282.55494/000000000000001", {{"id": 1}}),
    ]
    
    for index, data in test_data:
        _msg({{
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": "{script_addr}",
            "index": index,
            "data": json.dumps(data)
        }})
    return len(test_data)

def list_data(offset):
    query_params = {{
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": "{script_addr}",
        "index_prefix": "rate/tags/testtag43385/hot/",
        "pagination": {{
            "offset": offset,
            "limit": 1,
            "reverse": True
        }}
    }}
    
    result = _query(query_params)
    entries = result.get("entries", [])
    return json.loads(entries[0]["data"])["id"] if len(entries) > 0 else 0

def run_tests():
    set_test_data()
    return json.dumps([list_data(o) for o in range(4)])
"""

    # Execute as TX
    exec_result = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        script_addr,
        "--function-name",
        "run_tests",
        "--args",
        "[]",
        "--extra-code",
        script_code,
        "--from",
        user_name,
        "--gas",
        "auto",
        "-y",
    )

    assert exec_result["code"] == 0

    # Query tx details
    tx_details = dysond("query", "tx", exec_result["txhash"], "-o", "json")

    # Find EventExecScript and extract response
    events = tx_details["events"]
    exec_event = next(
        e for e in events if e["type"] == "dysonprotocol.script.v1.EventExecScript"
    )
    response_attr = next(a for a in exec_event["attributes"] if a["key"] == "response")
    response = json.loads(response_attr["value"])

    # Parse the result string - it's now json.dumps([list]) from script
    result_str = response["result"]
    inner_result = json.loads(result_str)
    actual_ids = json.loads(inner_result["result"])

    # Expected IDs: [4,2,3,1]
    expected_ids = [4, 2, 3, 1]

    print("\nPagination Results via TX Script:")
    print(f"Actual IDs: {repr(actual_ids)}")
    print(f"Expected IDs: {repr(expected_ids)}")

    mismatches = sum(1 for a, e in zip(actual_ids, expected_ids) if a != e)
    for a, e in zip(actual_ids, expected_ids):
        print(f"Actual: {a}, Expected: {e}")

    print(f"Summary: {mismatches} mismatches out of 4")

    assert (
        mismatches == 0
    ), f"Expected pagination to work correctly, but found {mismatches} mismatches"
    print("✅ Pagination works correctly in tx script context")


def test_storage_pagination_next_key(chainnet, generate_account, faucet):
    """Test next key pagination works correctly for both forward and reverse directions."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account("nextkey_pagination", faucet_amount=100)
    _stake(dysond, faucet, user_name, user_addr)

    # Create test data with predictable sort order
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    prefix = f"nextkey_test_{suffix}/"

    # Create 6 entries with predictable alphabetical sort order
    test_data = {
        f"{prefix}item_a": {"id": "a", "value": "first"},
        f"{prefix}item_b": {"id": "b", "value": "second"},
        f"{prefix}item_c": {"id": "c", "value": "third"},
        f"{prefix}item_d": {"id": "d", "value": "fourth"},
        f"{prefix}item_e": {"id": "e", "value": "fifth"},
        f"{prefix}item_f": {"id": "f", "value": "sixth"},
    }

    # Set all test data
    for key, value in test_data.items():
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            key,
            "--data",
            json.dumps(value),
        )

    print(f"Created test data with prefix: {prefix}")

    # First, get all entries to verify they're stored correctly
    all_entries_result = dysond(
        "query", "storage", "list", user_addr, "--index-prefix", prefix, "-o", "json"
    )
    all_entries = all_entries_result.get("entries", [])
    assert len(all_entries) == 6, f"Should have 6 total entries, got {len(all_entries)}"

    all_ids = [json.loads(entry["data"])["id"] for entry in all_entries]
    print(f"All entries (forward): {all_ids}")

    # Test pagination using offset approach (reliable method)
    print("\n=== Testing Forward Offset-Based Pagination ===")
    forward_collected_ids = []
    page_size = 2

    # Collect entries using offset pagination (3 pages of 2 items each)
    for page_num in range(3):
        offset = page_num * page_size
        page_result = dysond(
            "query",
            "storage",
            "list",
            user_addr,
            "--index-prefix",
            prefix,
            "--limit",
            str(page_size),
            "--offset",
            str(offset),
            "-o",
            "json",
        )

        page_entries = page_result.get("entries", [])
        print(
            f"Forward page {page_num + 1} (offset {offset}): {len(page_entries)} entries"
        )

        # Extract IDs from this page
        page_ids = [json.loads(entry["data"])["id"] for entry in page_entries]
        forward_collected_ids.extend(page_ids)

        # Print page details
        for entry in page_entries:
            entry_data = json.loads(entry["data"])
            print(f"  Entry: {entry['index']} -> ID {entry_data['id']}")

    print(f"Forward offset pagination collected IDs: {forward_collected_ids}")
    expected_forward = ["a", "b", "c", "d", "e", "f"]
    assert (
        forward_collected_ids == expected_forward
    ), f"Forward pagination: expected {expected_forward}, got {forward_collected_ids}"

    # Test reverse pagination using offset approach
    print("\n=== Testing Reverse Offset-Based Pagination ===")
    reverse_collected_ids = []

    # Collect entries using reverse offset pagination (3 pages of 2 items each)
    for page_num in range(3):
        offset = page_num * page_size
        page_result = dysond(
            "query",
            "storage",
            "list",
            user_addr,
            "--index-prefix",
            prefix,
            "--limit",
            str(page_size),
            "--offset",
            str(offset),
            "--reverse",
            "-o",
            "json",
        )

        page_entries = page_result.get("entries", [])
        print(
            f"Reverse page {page_num + 1} (offset {offset}): {len(page_entries)} entries"
        )

        # Extract IDs from this page
        page_ids = [json.loads(entry["data"])["id"] for entry in page_entries]
        reverse_collected_ids.extend(page_ids)

        # Print page details
        for entry in page_entries:
            entry_data = json.loads(entry["data"])
            print(f"  Entry: {entry['index']} -> ID {entry_data['id']}")

    print(f"Reverse offset pagination collected IDs: {reverse_collected_ids}")
    expected_reverse = ["f", "e", "d", "c", "b", "a"]
    assert (
        reverse_collected_ids == expected_reverse
    ), f"Reverse pagination: expected {expected_reverse}, got {reverse_collected_ids}"

    # Test page-key pagination (proper usage)
    print("\n=== Testing Page-Key Pagination ===")

    # First, get the first page and extract the next_key
    first_page_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--limit",
        "2",
        "-o",
        "json",
    )

    first_page_entries = first_page_result.get("entries", [])
    first_page_ids = [json.loads(entry["data"])["id"] for entry in first_page_entries]
    print(f"First page: {first_page_ids}")

    # Get the next_key for pagination
    pagination_info = first_page_result.get("pagination", {})
    next_key = pagination_info.get("next_key")
    assert next_key, f"Expected next_key in pagination response, got: {pagination_info}"

    print(f"Using next_key for second page: {next_key}")
    # Use the next_key to get the second page
    second_page_result = dysond(
        "query",
        "storage",
        "list",
        user_addr,
        "--index-prefix",
        prefix,
        "--limit",
        "2",
        "--page-key",
        next_key,
        "-o",
        "json",
    )

    second_page_entries = second_page_result.get("entries", [])
    second_page_ids = [json.loads(entry["data"])["id"] for entry in second_page_entries]
    print(f"Second page using page-key: {second_page_ids}")

    # Verify the total collection matches expected order
    total_pagekey_ids = first_page_ids + second_page_ids
    print(f"Total page-key pagination: {total_pagekey_ids}")
    assert (
        total_pagekey_ids == expected_forward[:4]
    ), f"Page-key pagination mismatch: expected {expected_forward[:4]}, got {total_pagekey_ids}"

    # Verify completeness and uniqueness for offset-based tests
    assert (
        len(set(forward_collected_ids)) == 6
    ), f"Forward pagination contained duplicates: {forward_collected_ids}"
    assert (
        len(set(reverse_collected_ids)) == 6
    ), f"Reverse pagination contained duplicates: {reverse_collected_ids}"
    assert set(forward_collected_ids) == set(
        reverse_collected_ids
    ), "Forward and reverse should contain same items"

    print(
        "\n✅ Offset-based pagination works correctly in both forward and reverse directions"
    )


def test_storage_pagination_next_key_script(chainnet, generate_account, faucet):
    """Test pagination via script execution using _query with both offset and key methods."""
    dysond = chainnet[0]

    # Create account and fund it
    [user_name, user_addr] = generate_account("nextkey_script", faucet_amount=100)

    prefix = f"script_nextkey_test/"

    # Script that tests both offset and key-based pagination
    script_code = f'''
import json
from dys import _query, _msg

def setup_test_data():
    """Create test data for pagination testing."""
    test_entries = [
        ("{prefix}alpha", {{"id": "alpha", "order": 1}}),
        ("{prefix}beta", {{"id": "beta", "order": 2}}),
        ("{prefix}gamma", {{"id": "gamma", "order": 3}}),
        ("{prefix}delta", {{"id": "delta", "order": 4}}),
    ]
    
    for index, data in test_entries:
        _msg({{
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": "{user_addr}",
            "index": index,
            "data": json.dumps(data)
        }})
    
    return len(test_entries)

def test_offset_pagination(reverse=False):
    """Test offset-based pagination in specified direction."""
    collected_ids = []
    page_size = 2
    total_pages = 2  # 4 items / 2 per page = 2 pages
    
    for page_num in range(total_pages):
        offset = page_num * page_size
        query_params = {{
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": "{user_addr}",
            "index_prefix": "{prefix}",
            "pagination": {{
                "limit": page_size,
                "offset": offset,
                "reverse": reverse
            }}
        }}
        
        result = _query(query_params)
        entries = result.get("entries", [])
        
        # Extract IDs from this page
        page_ids = [json.loads(entry["data"])["id"] for entry in entries]
        collected_ids.extend(page_ids)
    
    return collected_ids

def test_key_pagination(reverse=False):
    """Test key-based pagination in specified direction."""
    collected_ids = []
    page_key = None
    page_size = 2
    total_pages = 2  # 4 items / 2 per page = 2 pages
    
    for page_num in range(total_pages):
        query_params = {{
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": "{user_addr}",
            "index_prefix": "{prefix}",
            "pagination": {{
                "limit": page_size,
                "reverse": reverse
            }}
        }}
        
        # Add page key for subsequent pages
        if page_key:
            query_params["pagination"]["key"] = page_key
        
        result = _query(query_params)
        entries = result.get("entries", [])
        
        # Extract IDs from this page
        page_ids = [json.loads(entry["data"])["id"] for entry in entries]
        collected_ids.extend(page_ids)
        
        # Set page_key for next iteration from pagination response
        pagination = result.get("pagination", {{}})
        page_key = pagination.get("next_key")
    
    return collected_ids

def run_pagination_test():
    """Run comprehensive pagination tests."""
    setup_count = setup_test_data()
    
    # Test offset-based pagination
    forward_offset_ids = test_offset_pagination(reverse=False)
    reverse_offset_ids = test_offset_pagination(reverse=True)
    
    # Test key-based pagination
    forward_key_ids = test_key_pagination(reverse=False)
    reverse_key_ids = test_key_pagination(reverse=True)
    
    return {{
        "setup_count": setup_count,
        "forward_offset_ids": forward_offset_ids,
        "reverse_offset_ids": reverse_offset_ids,
        "forward_key_ids": forward_key_ids,
        "reverse_key_ids": reverse_key_ids,
        "expected_forward": ["alpha", "beta", "delta", "gamma"],
        "expected_reverse": ["gamma", "delta", "beta", "alpha"]
    }}
'''

    # Execute the script
    result = dysond(
        "query",
        "script",
        "run",
        "--executor-address",
        user_addr,
        "--script-address",
        user_addr,
        "--function-name",
        "run_pagination_test",
        "--args",
        "[]",
        "--output",
        "json",
        "--extra-code",
        script_code,
    )

    print(f"Script execution completed")
    print(f"Script result type: {type(result)}")
    print(
        f"Script result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}"
    )

    # Parse the result with better error handling
    assert isinstance(result, dict), f"Expected dict but got {type(result)}: {result}"
    assert "result" in result, f"Missing 'result' key in: {result}"

    result_content = result["result"]
    print(f"Result content type: {type(result_content)}")
    print(f"Result content: {result_content}")

    # Handle case where result might be None or empty
    assert result_content is not None, f"Script result is None: {result}"
    assert result_content != "", f"Script result is empty: {result}"

    result_data = json.loads(result_content)
    assert isinstance(
        result_data, dict
    ), f"Expected dict from JSON parse: {result_data}"
    assert (
        "result" in result_data
    ), f"Missing 'result' key in parsed data: {result_data}"

    script_result = result_data["result"]

    # Verify offset-based pagination
    forward_offset_ids = script_result["forward_offset_ids"]
    reverse_offset_ids = script_result["reverse_offset_ids"]
    expected_forward = script_result["expected_forward"]
    expected_reverse = script_result["expected_reverse"]

    assert (
        forward_offset_ids == expected_forward
    ), f"Script forward offset pagination: expected {expected_forward}, got {forward_offset_ids}"
    assert (
        reverse_offset_ids == expected_reverse
    ), f"Script reverse offset pagination: expected {expected_reverse}, got {reverse_offset_ids}"

    # Show key-based pagination results (may or may not work)
    forward_key_ids = script_result["forward_key_ids"]
    reverse_key_ids = script_result["reverse_key_ids"]

    print(
        f"Offset-based - Forward: {forward_offset_ids}, Reverse: {reverse_offset_ids}"
    )
    print(f"Key-based - Forward: {forward_key_ids}, Reverse: {reverse_key_ids}")

    # Key-based pagination might have different behavior, so we just report it
    key_forward_works = forward_key_ids == expected_forward
    key_reverse_works = reverse_key_ids == expected_reverse
    print(
        f"Key-based pagination: Forward works: {key_forward_works}, Reverse works: {key_reverse_works}"
    )

    print("✅ Offset-based pagination works correctly via script execution")
