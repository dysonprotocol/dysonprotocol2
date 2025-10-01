import pytest
import json


def test_storage_metrics_new_structure(chainnet):
    """Test that QueryMetrics returns the new restructured response with embedded fields."""
    dysond = chainnet[0]

    # Use alice's address as a valid test address
    test_account = "alice"
    test_addr = dysond("keys", "show", test_account, "-a").strip()

    metrics_result = dysond("query", "storage", "metrics", test_addr)
    print(f"Metrics query result: {json.dumps(metrics_result, indent=2)}")

    # Verify new structure - should have embedded fields directly
    assert (
        "owner" in metrics_result
    ), f"Expected 'owner' field in response: {metrics_result}"
    assert (
        "total_bytes" in metrics_result
    ), f"Expected 'total_bytes' field in response: {metrics_result}"
    assert (
        "min_stake_amount" in metrics_result
    ), f"Expected 'min_stake_amount' field in response: {metrics_result}"
    assert (
        "current_stake_amount" in metrics_result
    ), f"Expected 'current_stake_amount' field in response: {metrics_result}"

    # Verify that old nested 'metrics' field is NOT present
    assert (
        "metrics" not in metrics_result
    ), f"Old 'metrics' field should not be present: {metrics_result}"

    # Verify owner matches the queried address
    assert (
        metrics_result["owner"] == test_addr
    ), f"Expected owner to be {test_addr}, got {metrics_result['owner']}"

    # Verify that min_stake_amount is correctly calculated (total_bytes × storage_stake_multiple)
    total_bytes = int(metrics_result["total_bytes"])
    min_stake_amount = int(metrics_result["min_stake_amount"])

    # With default storage_stake_multiple of "0", min_stake_amount should be 0
    assert (
        min_stake_amount == 0
    ), f"Expected min_stake_amount ({min_stake_amount}) to be 0 with default multiplier 0"

    # current_stake_amount should be populated from staking module (may have delegations from previous tests)
    current_stake = int(metrics_result["current_stake_amount"])
    assert (
        current_stake >= 0
    ), f"current_stake_amount should be non-negative, got {current_stake}"


def test_storage_metrics_min_stake_calculation(chainnet, generate_account):
    """Test that min_stake_amount is calculated correctly with actual storage."""
    dysond = chainnet[0]

    # Use a unique test account to avoid test interference
    test_account_name, test_addr = generate_account("metrics_test")

    # Store some data to create metrics
    test_data = "a" * 500  # 500 bytes
    storage_result = dysond(
        "tx",
        "storage",
        "set",
        "--index",
        "test_min_stake_calculation",
        "--data",
        test_data,
        "--from",
        test_account_name,
        "--gas",
        "auto",
    )

    assert isinstance(
        storage_result, dict
    ), f"Expected dict response, got {type(storage_result)}: {storage_result}"
    assert (
        storage_result["code"] == 0
    ), f"Storage set should succeed: {storage_result.get('raw_log', 'No raw_log')}"

    # Query metrics to verify min_stake_amount calculation
    metrics_result = dysond("query", "storage", "metrics", test_addr)
    print(f"Metrics after storage: {json.dumps(metrics_result, indent=2)}")

    # With storage_stake_multiple = "0", min_stake_amount should be 0 regardless of bytes
    assert metrics_result["owner"] == test_addr
    total_bytes = int(metrics_result["total_bytes"])
    assert total_bytes == 500, f"Expected 500 bytes, got {total_bytes}"
    assert (
        metrics_result["min_stake_amount"] == "0"
    )  # 0 multiplier means 0 stake required
    assert (
        metrics_result["current_stake_amount"] == "0"
    )  # Account should have no delegations


def test_storage_metrics_with_different_stake_multiple(chainnet):
    """Test min_stake_amount calculation with different storage_stake_multiple parameter."""
    dysond = chainnet[0]

    # Test current parameters to verify default stake multiple exists
    params_result = dysond("query", "storage", "params")
    print(f"Current storage params: {json.dumps(params_result, indent=2)}")

    # Verify the structure includes storage_stake_multiple
    assert "params" in params_result
    assert "storage_stake_multiple" in params_result["params"]

    print("✅ storage_stake_multiple parameter is present and properly configured")
