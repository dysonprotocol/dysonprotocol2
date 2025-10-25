"""
Test storage metrics functionality.

This module tests the QueryMetrics RPC endpoint and metrics tracking
for StorageSet and StorageDelete operations.
"""

import pytest
import json
import random
import string


def test_metrics_empty_address(chainnet, generate_account):
    """Test metrics query for address with no storage."""
    dysond = chainnet[0]
    [test_name, test_address] = generate_account(
        "metrics_test", faucet_amount=1_000_000
    )

    result = dysond("query", "storage", "metrics", test_address)

    # Verify new flat structure (task 19-2)
    assert "owner" in result
    assert "total_bytes" in result
    assert "min_stake_amount" in result  # New field from task 19-2
    assert "current_stake_amount" in result  # New field from task 19-2
    assert result["owner"] == test_address
    assert result["total_bytes"] == "0"
    assert result["min_stake_amount"] == "0"  # 0 bytes × 1.0 multiplier = 0


def test_metrics_single_storage_entry(chainnet, generate_account):
    """Test metrics after adding a single storage entry."""
    dysond = chainnet[0]
    [test_name, test_address] = generate_account(
        "metrics_test", faucet_amount=2_000_000
    )

    # Get a validator to delegate to for stake validation
    validators_result = dysond("query", "staking", "validators")
    assert (
        len(validators_result["validators"]) > 0
    ), "Need at least one validator for delegation test"
    validator_addr = validators_result["validators"][0]["operator_address"]

    # Delegate sufficient tokens to cover storage requirements
    delegation_amount = "1000000udys"  # 1 dys, more than enough for small storage
    delegate_result = dysond(
        "tx",
        "staking",
        "delegate",
        validator_addr,
        delegation_amount,
        "--from",
        test_name,
    )

    assert isinstance(
        delegate_result, dict
    ), f"Expected dict response, got {type(delegate_result)}: {delegate_result}"
    assert (
        "code" in delegate_result
    ), f"Missing 'code' field in response: {delegate_result}"
    assert (
        delegate_result["code"] == 0
    ), f"Delegation should succeed: {delegate_result.get('raw_log', 'No raw_log')}"

    test_data = "Hello, World!"
    expected_bytes = len(test_data.encode("utf-8"))

    # Add storage entry
    result = dysond(
        "tx",
        "storage",
        "set",
        "--index",
        "test/greeting",
        "--data",
        test_data,
        "--from",
        test_name,
    )
    assert result["code"] == 0, f"Storage set failed: {result}"

    # Query metrics
    result = dysond("query", "storage", "metrics", test_address)

    # Verify new flat structure (task 19-2)
    assert "owner" in result
    assert "total_bytes" in result
    assert "min_stake_amount" in result
    assert result["owner"] == test_address
    assert int(result["total_bytes"]) == expected_bytes


def test_metrics_multiple_storage_entries(chainnet, generate_account):
    """Test metrics after adding multiple storage entries."""
    dysond = chainnet[0]
    [test_name, test_address] = generate_account(
        "metrics_test", faucet_amount=1_000_000
    )

    entries = [
        ("test/entry1", "First entry data"),
        ("test/entry2", "Second entry with more data"),
        ("config/settings", '{"theme": "dark", "language": "en"}'),
    ]

    total_expected_bytes = 0

    # Add multiple storage entries
    for index, data in entries:
        result = dysond(
            "tx",
            "storage",
            "set",
            "--index",
            index,
            "--data",
            data,
            "--from",
            test_name,
        )
        assert result["code"] == 0, f"Storage set failed for {index}: {result}"
        total_expected_bytes += len(data.encode("utf-8"))

    # Query metrics
    result = dysond("query", "storage", "metrics", test_address)

    # Verify new flat structure (task 19-2)
    assert "owner" in result
    assert "total_bytes" in result
    assert "min_stake_amount" in result
    assert result["owner"] == test_address
    assert int(result["total_bytes"]) == total_expected_bytes


def test_metrics_update_existing_entry(chainnet, generate_account):
    """Test metrics when updating an existing storage entry."""
    dysond = chainnet[0]
    [test_name, test_address] = generate_account(
        "metrics_test", faucet_amount=1_000_000
    )

    initial_data = "Initial data"
    updated_data = "Updated data with more content"

    # Add initial storage entry
    result = dysond(
        "tx",
        "storage",
        "set",
        "--index",
        "test/updateable",
        "--data",
        initial_data,
        "--from",
        test_name,
    )
    assert result["code"] == 0, f"Initial storage set failed: {result}"

    # Verify initial metrics
    result = dysond("query", "storage", "metrics", test_address)
    assert int(result["total_bytes"]) == len(initial_data.encode("utf-8"))

    # Update the entry
    result = dysond(
        "tx",
        "storage",
        "set",
        "--index",
        "test/updateable",
        "--data",
        updated_data,
        "--from",
        test_name,
    )
    assert result["code"] == 0, f"Storage update failed: {result}"

    # Verify updated metrics
    result = dysond("query", "storage", "metrics", test_address)
    assert int(result["total_bytes"]) == len(updated_data.encode("utf-8"))


def test_metrics_delete_entries(chainnet, generate_account):
    """Test metrics after deleting storage entries."""
    dysond = chainnet[0]
    [test_name, test_address] = generate_account(
        "metrics_test", faucet_amount=1_000_000
    )

    entries = [
        ("test/temp1", "Temporary data 1"),
        ("test/temp2", "Temporary data 2"),
        ("test/permanent", "This will remain"),
    ]

    # Add storage entries
    for index, data in entries:
        result = dysond(
            "tx",
            "storage",
            "set",
            "--index",
            index,
            "--data",
            data,
            "--from",
            test_name,
        )
        assert result["code"] == 0, f"Storage set failed for {index}: {result}"

    # Verify total metrics
    total_bytes = sum(len(data.encode("utf-8")) for _, data in entries)
    result = dysond("query", "storage", "metrics", test_address)
    assert int(result["total_bytes"]) == total_bytes

    # Delete two entries
    result = dysond(
        "tx",
        "storage",
        "delete",
        "--indexes",
        "test/temp1,test/temp2",
        "--from",
        test_name,
    )
    assert result["code"] == 0, f"Storage delete failed: {result}"

    # Verify metrics after deletion
    remaining_bytes = len("This will remain".encode("utf-8"))
    result = dysond("query", "storage", "metrics", test_address)
    assert int(result["total_bytes"]) == remaining_bytes


def test_metrics_delete_all_entries(chainnet, generate_account):
    """Test metrics after deleting all storage entries."""
    dysond = chainnet[0]
    [test_name, test_address] = generate_account(
        "metrics_test", faucet_amount=1_000_000
    )

    # Add some storage entries
    entries = [
        ("test/delete1", "Data to delete 1"),
        ("test/delete2", "Data to delete 2"),
    ]

    for index, data in entries:
        result = dysond(
            "tx",
            "storage",
            "set",
            "--index",
            index,
            "--data",
            data,
            "--from",
            test_name,
        )
        assert result["code"] == 0, f"Storage set failed for {index}: {result}"

    # Verify metrics before deletion
    result = dysond("query", "storage", "metrics", test_address)
    assert int(result["total_bytes"]) > 0

    # Delete all entries
    indexes = ",".join(index for index, _ in entries)
    result = dysond(
        "tx",
        "storage",
        "delete",
        "--indexes",
        indexes,
        "--from",
        test_name,
    )
    assert result["code"] == 0, f"Storage delete failed: {result}"

    # Verify metrics after deletion
    result = dysond("query", "storage", "metrics", test_address)
    assert int(result["total_bytes"]) == 0


def test_metrics_cli_help(chainnet):
    """Test that the metrics CLI command has proper help."""
    dysond = chainnet[0]

    result = dysond("query", "storage", "metrics", "--help", raw=True)

    assert "Query storage metrics" in result
    assert "total bytes consumed" in result
    assert "Examples:" in result
