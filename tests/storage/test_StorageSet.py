"""
StorageSet message handler coverage tests.

Tests the StorageSet message handler which sets storage entries with stake validation,
size limits, and metadata tracking. Covers all validation paths and success cases.
"""

import json
import pytest
import hashlib
import base64


def test_storage_set_success_create(chainnet, generate_account, faucet):
    """Test StorageSet creates new entry successfully."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_create", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Set storage entry
    test_index = "test/create"
    test_data = '{"message": "hello", "value": 42}'

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

    # Validate transaction success
    assert (
        tx_result.get("code", 1) == 0
    ), f"Storage set failed: {json.dumps(tx_result, indent=2)}"

    # Verify entry was created
    get_response = dysond("query", "storage", "get", owner_addr, "--index", test_index)
    assert isinstance(
        get_response, dict
    ), f"Get response should be dict, got {type(get_response)}"
    assert "entry" in get_response, f"Get response missing 'entry' key"

    entry = get_response["entry"]
    assert (
        entry["data"] == test_data
    ), f"Data mismatch: expected {test_data}, got {entry['data']}"
    assert (
        entry["owner"] == owner_addr
    ), f"Owner mismatch: expected {owner_addr}, got {entry['owner']}"
    assert (
        entry["index"] == test_index
    ), f"Index mismatch: expected {test_index}, got {entry['index']}"


def test_storage_set_success_update(chainnet, generate_account, faucet):
    """Test StorageSet updates existing entry successfully."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_update", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Create initial entry
    test_index = "test/update"
    initial_data = '{"value": 1}'

    tx_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        test_index,
        "--data",
        initial_data,
    )
    assert (
        tx_result.get("code", 1) == 0
    ), f"Initial storage set failed: {json.dumps(tx_result, indent=2)}"

    # Update entry
    updated_data = '{"value": 2, "updated": true}'
    tx_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        test_index,
        "--data",
        updated_data,
    )
    assert (
        tx_result.get("code", 1) == 0
    ), f"Storage update failed: {json.dumps(tx_result, indent=2)}"

    # Verify entry was updated
    get_response = dysond("query", "storage", "get", owner_addr, "--index", test_index)
    entry = get_response["entry"]
    assert (
        entry["data"] == updated_data
    ), f"Data should be updated: expected {updated_data}, got {entry['data']}"


def test_storage_set_empty_index(chainnet, generate_account, faucet):
    """Test StorageSet fails with empty index."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_empty_idx", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Attempt to set with empty index
    result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        "",
        "--data",
        '{"test": "data"}',
    )

    # Should fail
    assert (
        result.get("code", 0) != 0
    ), f"Storage set should fail with empty index: {json.dumps(result, indent=2)}"
    assert (
        "index cannot be empty" in result.get("raw_log", "").lower()
    ), f"Expected empty index error, got: {result.get('raw_log', '')}"


def test_storage_set_invalid_index_chars(chainnet, generate_account, faucet):
    """Test StorageSet fails with non-printable ASCII in index."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_invalid_idx", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Attempt to set with non-printable ASCII (newline character)
    invalid_index = "test/key\nwith/newline"

    result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        invalid_index,
        "--data",
        '{"test": "data"}',
    )

    # Should fail
    assert (
        result.get("code", 0) != 0
    ), f"Storage set should fail with invalid index chars: {json.dumps(result, indent=2)}"
    assert (
        "printable ascii" in result.get("raw_log", "").lower()
    ), f"Expected printable ASCII error, got: {result.get('raw_log', '')}"


def test_storage_set_size_limit(chainnet, generate_account, faucet):
    """Test StorageSet fails when data exceeds MaxStorageSize."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_size_limit", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Get current max storage size
    params = dysond("query", "storage", "params")["params"]
    max_size = int(params["max_storage_size"])

    # Attempt to set data exceeding limit
    oversized_data = "x" * (max_size + 1)

    result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        "test/oversized",
        "--data",
        oversized_data,
        "--gas",
        "auto",
    )

    # Should fail
    assert (
        result.get("code", 0) != 0
    ), f"Storage set should fail with oversized data: {json.dumps(result, indent=2)}"
    assert (
        "exceeds maximum allowed size" in result.get("raw_log", "").lower()
    ), f"Expected size limit error, got: {result.get('raw_log', '')}"


def test_storage_set_metadata(chainnet, generate_account, faucet):
    """Test StorageSet stores metadata (hash, height, timestamp) correctly."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_metadata", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Set storage entry
    test_index = "test/metadata"
    test_data = '{"test": "metadata"}'

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

    # Get entry and verify metadata
    get_response = dysond("query", "storage", "get", owner_addr, "--index", test_index)
    entry = get_response["entry"]

    # Verify hash format (sha256-<base64>)
    assert "hash" in entry, f"Entry missing 'hash' key. Keys: {list(entry.keys())}"
    assert entry["hash"].startswith(
        "sha256-"
    ), f"Hash should start with 'sha256-', got {entry['hash']}"

    # Verify hash calculation
    hash_bytes = hashlib.sha256(test_data.encode()).digest()
    expected_hash_b64 = base64.b64encode(hash_bytes).decode()
    expected_hash = f"sha256-{expected_hash_b64}"
    assert (
        entry["hash"] == expected_hash
    ), f"Hash mismatch: expected {expected_hash}, got {entry['hash']}"

    # Verify height and timestamp exist
    assert "updated_height" in entry, f"Entry missing 'updated_height' key"
    assert "updated_timestamp" in entry, f"Entry missing 'updated_timestamp' key"
    assert (
        int(entry["updated_height"]) > 0
    ), f"Updated height should be positive: {entry['updated_height']}"


def test_storage_set_metrics_update(chainnet, generate_account, faucet):
    """Test StorageSet updates storage metrics correctly."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_metrics", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Check initial metrics
    initial_metrics = dysond("query", "storage", "metrics", owner_addr)
    initial_bytes = int(initial_metrics["total_bytes"])

    # Set storage entry
    test_data = "x" * 100  # 100 bytes
    tx_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        "test/metrics",
        "--data",
        test_data,
    )
    assert (
        tx_result.get("code", 1) == 0
    ), f"Storage set failed: {json.dumps(tx_result, indent=2)}"

    # Check updated metrics
    updated_metrics = dysond("query", "storage", "metrics", owner_addr)
    updated_bytes = int(updated_metrics["total_bytes"])

    assert updated_bytes == initial_bytes + len(
        test_data.encode()
    ), f"Total bytes should increase by {len(test_data.encode())}: initial={initial_bytes}, updated={updated_bytes}"


def test_storage_set_event_emission(chainnet, generate_account, faucet):
    """Test StorageSet emits EventStorageUpdated event."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_event", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Set storage entry
    test_index = "test/event"
    test_data = '{"test": "event"}'

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

    # Check for event
    events = tx_result.get("events", [])
    storage_events = [
        e
        for e in events
        if e.get("type") == "dysonprotocol.storage.v1.EventStorageUpdated"
    ]
    assert (
        len(storage_events) > 0
    ), f"Missing EventStorageUpdated event. Events: {json.dumps(events, indent=2)}"

    # Verify event attributes
    event_attrs = {
        a.get("key"): a.get("value") for a in storage_events[0].get("attributes", [])
    }
    assert (
        event_attrs.get("address") == owner_addr
    ), f"Event address mismatch: expected {owner_addr}, got {event_attrs.get('address')}"
    assert (
        event_attrs.get("index") == test_index
    ), f"Event index mismatch: expected {test_index}, got {event_attrs.get('index')}"


def test_storage_set_invalid_owner(chainnet):
    """Test StorageSet fails with invalid owner address."""
    dysond = chainnet[0]

    # Attempt to set with invalid owner address
    result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        "invalid_address",
        "--index",
        "test/key",
        "--data",
        '{"test": "data"}',
    )

    # Should fail (CLI will reject invalid key name)
    assert (
        result.get("code", 0) != 0
    ), f"Storage set should fail with invalid owner: {json.dumps(result, indent=2)}"


def test_storage_set_stake_validation_disabled(chainnet, generate_account, faucet):
    """Test StorageSet succeeds when stake validation is disabled (StorageStakeMultiple = 0)."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_no_stake", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Get current params
    params = dysond("query", "storage", "params")["params"]
    stake_multiple = params["storage_stake_multiple"]

    # If stake_multiple is "0", validation should be disabled
    if stake_multiple == "0":
        # Set storage entry without delegation
        tx_result = dysond(
            "tx",
            "storage",
            "set",
            "--from",
            owner_name,
            "--index",
            "test/no_stake",
            "--data",
            '{"test": "no stake validation"}',
        )
        # Should succeed when validation is disabled
        assert (
            tx_result.get("code", 1) == 0
        ), f"Storage set should succeed when stake validation is disabled: {json.dumps(tx_result, indent=2)}"


def test_storage_set_stake_validation_sufficient(chainnet, generate_account, faucet):
    """Test StorageSet succeeds when stake validation is enabled and owner has sufficient stake."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_sufficient_stake", faucet_amount=2_000_000
    )
    faucet(owner_addr)

    # Get current params
    params = dysond("query", "storage", "params")["params"]
    stake_multiple = float(params["storage_stake_multiple"])

    # Only test if stake validation is enabled
    if stake_multiple > 0:
        # Get validator to delegate to
        validators_result = dysond("query", "staking", "validators")
        assert len(validators_result["validators"]) > 0, "Need at least one validator"
        validator_addr = validators_result["validators"][0]["operator_address"]

        # Delegate sufficient tokens
        delegate_result = dysond(
            "tx",
            "staking",
            "delegate",
            validator_addr,
            "1000000udys",
            "--from",
            owner_name,
        )
        assert (
            delegate_result.get("code", 1) == 0
        ), f"Delegation failed: {json.dumps(delegate_result, indent=2)}"

        # Set storage entry (should succeed with sufficient stake)
        tx_result = dysond(
            "tx",
            "storage",
            "set",
            "--from",
            owner_name,
            "--index",
            "test/sufficient_stake",
            "--data",
            '{"test": "sufficient stake"}',
        )
        assert (
            tx_result.get("code", 1) == 0
        ), f"Storage set should succeed with sufficient stake: {json.dumps(tx_result, indent=2)}"


def test_storage_set_stake_validation_insufficient(chainnet, generate_account, faucet):
    """Test StorageSet fails when stake validation is enabled and owner has insufficient stake."""
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account(
        "storage_set_insufficient_stake", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Get current params
    params = dysond("query", "storage", "params")["params"]
    stake_multiple = float(params["storage_stake_multiple"])

    # Only test if stake validation is enabled
    if stake_multiple > 0:
        # Don't delegate any tokens (owner has no stake)
        # Attempt to set large storage entry that requires stake
        large_data = "x" * 10000  # 10KB - requires stake when multiplier > 0

        result = dysond(
            "tx",
            "storage",
            "set",
            "--from",
            owner_name,
            "--index",
            "test/insufficient_stake",
            "--data",
            large_data,
            "--gas",
            "auto",
        )

        # Should fail due to insufficient stake
        assert (
            result.get("code", 0) != 0
        ), f"Storage set should fail with insufficient stake: {json.dumps(result, indent=2)}"
        assert (
            "insufficient stake" in result.get("raw_log", "").lower()
            or "stake" in result.get("raw_log", "").lower()
        ), f"Expected insufficient stake error, got: {result.get('raw_log', '')}"
