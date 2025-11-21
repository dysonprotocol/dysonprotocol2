"""
StorageDelete message handler coverage tests.

Tests the StorageDelete message handler which removes storage entries.
Covers all validation paths, success cases, ownership verification, and metrics updates.
"""

import json
import pytest


def test_storage_delete_success_single(chainnet, generate_account, faucet):
    """Test StorageDelete deletes single entry successfully."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_single", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Create storage entry
    test_index = "test/delete_single"
    test_data = '{"test": "delete"}'

    tx_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        test_index,
        "--data",
        test_data,
    )
    assert (
        tx_result.get("code", 1) == 0
    ), f"Storage set failed: {json.dumps(tx_result, indent=2)}"

    # Verify entry exists
    get_response = dysond("query", "storage", "get", owner_addr, "--index", test_index)
    assert "entry" in get_response, f"Entry should exist before deletion"

    # Delete entry
    delete_result = dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        owner_name,
        "--indexes",
        test_index,
    )

    # Validate transaction success
    assert (
        delete_result.get("code", 1) == 0
    ), f"Storage delete failed: {json.dumps(delete_result, indent=2)}"

    # Verify response contains deleted indexes
    assert (
        "deleted_indexes" in delete_result
    ), f"Delete response missing 'deleted_indexes' key"
    deleted_indexes = delete_result["deleted_indexes"]
    assert isinstance(
        deleted_indexes, list
    ), f"deleted_indexes should be list, got {type(deleted_indexes)}"
    assert (
        test_index in deleted_indexes
    ), f"Deleted index should include {test_index}, got {deleted_indexes}"

    # Verify entry no longer exists
    result = dysond("query", "storage", "get", owner_addr, "--index", test_index)
    assert isinstance(
        result, str
    ), f"Query should return error for deleted entry, got {type(result)}"
    assert (
        "doesn't exist" in result.lower() or "not found" in result.lower()
    ), f"Expected not found error, got: {result}"


def test_storage_delete_success_multiple(chainnet, generate_account, faucet):
    """Test StorageDelete deletes multiple entries successfully."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_multiple", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Create multiple storage entries
    indexes = ["test/delete1", "test/delete2", "test/delete3"]
    for index in indexes:
        tx_result = dysond(
            "tx",
            "storage",
            "set",
            "--from",
            owner_name,
            "--index",
            index,
            "--data",
            f'{{"index": "{index}"}}',
        )
        assert (
            tx_result.get("code", 1) == 0
        ), f"Storage set failed for {index}: {json.dumps(tx_result, indent=2)}"

    # Delete multiple entries
    delete_result = dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        owner_name,
        "--indexes",
        ",".join(indexes),
    )

    # Validate transaction success
    assert (
        delete_result.get("code", 1) == 0
    ), f"Storage delete failed: {json.dumps(delete_result, indent=2)}"

    # Verify response contains all deleted indexes
    assert (
        "deleted_indexes" in delete_result
    ), f"Delete response missing 'deleted_indexes' key"
    deleted_indexes = delete_result["deleted_indexes"]
    assert isinstance(
        deleted_indexes, list
    ), f"deleted_indexes should be list, got {type(deleted_indexes)}"
    assert len(deleted_indexes) == len(
        indexes
    ), f"Expected {len(indexes)} deleted indexes, got {len(deleted_indexes)}"

    for index in indexes:
        assert index in deleted_indexes, f"Deleted index should include {index}"


def test_storage_delete_empty_indexes(chainnet, generate_account, faucet):
    """Test StorageDelete fails with empty indexes list."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_empty", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Attempt to delete with empty indexes
    result = dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        owner_name,
        "--indexes",
        "",
    )

    # Should fail
    assert (
        result.get("code", 0) != 0
    ), f"Storage delete should fail with empty indexes: {json.dumps(result, indent=2)}"
    assert (
        "at least one index" in result.get("raw_log", "").lower()
    ), f"Expected empty indexes error, got: {result.get('raw_log', '')}"


def test_storage_delete_no_entries_deleted(chainnet, generate_account, faucet):
    """Test StorageDelete fails when no entries are deleted."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_none", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Attempt to delete non-existent entries
    result = dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        owner_name,
        "--indexes",
        "nonexistent/key1,nonexistent/key2",
    )

    # Should fail
    assert (
        result.get("code", 0) != 0
    ), f"Storage delete should fail when no entries deleted: {json.dumps(result, indent=2)}"
    assert (
        "no entries were deleted" in result.get("raw_log", "").lower()
    ), f"Expected no entries deleted error, got: {result.get('raw_log', '')}"


def test_storage_delete_metrics_update(chainnet, generate_account, faucet):
    """Test StorageDelete updates storage metrics correctly."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_metrics", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Create storage entries
    test_data1 = "x" * 100  # 100 bytes
    test_data2 = "y" * 200  # 200 bytes

    tx_result1 = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        "test/metrics1",
        "--data",
        test_data1,
    )
    assert (
        tx_result1.get("code", 1) == 0
    ), f"Storage set failed: {json.dumps(tx_result1, indent=2)}"

    tx_result2 = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        "test/metrics2",
        "--data",
        test_data2,
    )
    assert (
        tx_result2.get("code", 1) == 0
    ), f"Storage set failed: {json.dumps(tx_result2, indent=2)}"

    # Check metrics before deletion
    metrics_before = dysond("query", "storage", "metrics", owner_addr)
    bytes_before = int(metrics_before["total_bytes"])

    # Delete one entry
    delete_result = dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        owner_name,
        "--indexes",
        "test/metrics1",
    )
    assert (
        delete_result.get("code", 1) == 0
    ), f"Storage delete failed: {json.dumps(delete_result, indent=2)}"

    # Check metrics after deletion
    metrics_after = dysond("query", "storage", "metrics", owner_addr)
    bytes_after = int(metrics_after["total_bytes"])

    assert bytes_after == bytes_before - len(
        test_data1.encode()
    ), f"Total bytes should decrease by {len(test_data1.encode())}: before={bytes_before}, after={bytes_after}"


def test_storage_delete_event_emission(chainnet, generate_account, faucet):
    """Test StorageDelete emits EventStorageDelete event."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_event", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Create storage entries
    indexes = ["test/event1", "test/event2"]
    for index in indexes:
        tx_result = dysond(
            "tx",
            "storage",
            "set",
            "--from",
            owner_name,
            "--index",
            index,
            "--data",
            f'{{"index": "{index}"}}',
        )
        assert (
            tx_result.get("code", 1) == 0
        ), f"Storage set failed for {index}: {json.dumps(tx_result, indent=2)}"

    # Delete entries
    delete_result = dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        owner_name,
        "--indexes",
        ",".join(indexes),
    )
    assert (
        delete_result.get("code", 1) == 0
    ), f"Storage delete failed: {json.dumps(delete_result, indent=2)}"

    # Check for event
    events = delete_result.get("events", [])
    storage_events = [
        e
        for e in events
        if e.get("type") == "dysonprotocol.storage.v1.EventStorageDelete"
    ]
    assert (
        len(storage_events) > 0
    ), f"Missing EventStorageDelete event. Events: {json.dumps(events, indent=2)}"

    # Verify event attributes
    event_attrs = {
        a.get("key"): a.get("value") for a in storage_events[0].get("attributes", [])
    }
    assert (
        event_attrs.get("owner") == owner_addr
    ), f"Event owner mismatch: expected {owner_addr}, got {event_attrs.get('owner')}"


def test_storage_delete_partial_deletion(chainnet, generate_account, faucet):
    """Test StorageDelete handles partial deletion (some exist, some don't)."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_delete_partial", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Create one entry
    existing_index = "test/existing"
    tx_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        existing_index,
        "--data",
        '{"test": "data"}',
    )
    assert (
        tx_result.get("code", 1) == 0
    ), f"Storage set failed: {json.dumps(tx_result, indent=2)}"

    # Attempt to delete existing and non-existent entries
    delete_result = dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        owner_name,
        "--indexes",
        f"{existing_index},test/nonexistent",
    )

    # Should succeed (non-existent entries are skipped)
    assert (
        delete_result.get("code", 1) == 0
    ), f"Storage delete should succeed with partial deletion: {json.dumps(delete_result, indent=2)}"

    # Verify only existing entry was deleted
    assert (
        "deleted_indexes" in delete_result
    ), f"Delete response missing 'deleted_indexes' key"
    deleted_indexes = delete_result["deleted_indexes"]
    assert (
        existing_index in deleted_indexes
    ), f"Deleted indexes should include {existing_index}"
    assert (
        "test/nonexistent" not in deleted_indexes
    ), f"Non-existent index should not be in deleted_indexes"
