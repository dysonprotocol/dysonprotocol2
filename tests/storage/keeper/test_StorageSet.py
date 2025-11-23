"""
StorageSet message handler coverage tests.

Tests the StorageSet message handler which sets storage entries with stake validation,
size limits, and metadata tracking. Covers metrics calculation and stake validation paths.
All tests use stateless script query execution with _sudo calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_storage_set_metrics_update_entry_update(chainnet):
    """Test StorageSet updates total_bytes correctly when updating an existing entry."""
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

def demo_storage_set_metrics_update(owner_addr, index, initial_data, updated_data):
    # Create initial entry
    set_result1 = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": index,
        "data": initial_data
    })
    
    # Query metrics after initial creation
    metrics1 = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    # Update entry with different size data
    set_result2 = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": index,
        "data": updated_data
    })
    
    # Query metrics after update
    metrics2 = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    return {
        "set_result1": set_result1,
        "set_result2": set_result2,
        "metrics1": metrics1,
        "metrics2": metrics2,
        "initial_size": len(initial_data),
        "updated_size": len(updated_data)
    }
"""

    test_index = "test/metrics/update"
    initial_data = '{"value": 1}'  # 13 bytes
    updated_data = '{"value": 100, "extra": "data"}'  # 28 bytes

    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "index": test_index,
            "initial_data": initial_data,
            "updated_data": updated_data,
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
        "demo_storage_set_metrics_update",
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
    metrics1 = demo_result["metrics1"]
    metrics2 = demo_result["metrics2"]

    # Verify initial metrics
    assert isinstance(metrics1, dict), f"Metrics1 should be dict, got {type(metrics1)}"
    assert (
        "total_bytes" in metrics1
    ), f"Metrics1 missing 'total_bytes' key. Keys: {list(metrics1.keys())}"
    initial_total_bytes = metrics1["total_bytes"]

    # Verify updated metrics
    assert isinstance(metrics2, dict), f"Metrics2 should be dict, got {type(metrics2)}"
    assert (
        "total_bytes" in metrics2
    ), f"Metrics2 missing 'total_bytes' key. Keys: {list(metrics2.keys())}"
    updated_total_bytes = metrics2["total_bytes"]

    # Calculate expected delta
    initial_size = demo_result["initial_size"]
    updated_size = demo_result["updated_size"]
    expected_delta = updated_size - initial_size

    # Verify metrics updated correctly
    # When updating an entry, total_bytes should change by (new_size - old_size)
    actual_delta = int(updated_total_bytes) - int(initial_total_bytes)
    assert (
        actual_delta == expected_delta
    ), f"Metrics delta mismatch: expected {expected_delta} (updated_size {updated_size} - initial_size {initial_size}), got {actual_delta} (updated_total_bytes {updated_total_bytes} - initial_total_bytes {initial_total_bytes})"


def test_storage_set_stake_validation_calculates_total_bytes(chainnet):
    """Test StorageSet stake validation calculates new total bytes correctly.

    This test verifies that when StorageSet calculates stake requirements,
    it correctly computes the new total bytes by subtracting old entry size
    and adding new entry size. This calculation happens regardless of whether
    stake validation is enabled or disabled.
    """
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

def demo_storage_set_stake_calc(owner_addr, index1, data1, index2, data2):
    # Get initial metrics
    metrics_before = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    # Create first entry
    set_result1 = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": index1,
        "data": data1
    })
    
    # Get metrics after first entry
    metrics_after1 = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    # Create second entry
    set_result2 = _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": index2,
        "data": data2
    })
    
    # Get metrics after second entry
    metrics_after2 = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    return {
        "metrics_before": metrics_before,
        "metrics_after1": metrics_after1,
        "metrics_after2": metrics_after2,
        "data1_size": len(data1),
        "data2_size": len(data2)
    }
"""

    test_index1 = "test/stake/calc1"
    test_index2 = "test/stake/calc2"
    data1 = '{"entry": 1}'  # 13 bytes
    data2 = '{"entry": 2, "more": "data"}'  # 27 bytes

    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "index1": test_index1,
            "data1": data1,
            "index2": test_index2,
            "data2": data2,
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
        "demo_storage_set_stake_calc",
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
    metrics_after1 = demo_result["metrics_after1"]
    metrics_after2 = demo_result["metrics_after2"]

    # Verify metrics progression
    assert isinstance(
        metrics_before, dict
    ), f"Metrics_before should be dict, got {type(metrics_before)}"
    assert "total_bytes" in metrics_before, f"Metrics_before missing 'total_bytes' key"
    total_bytes_before = int(metrics_before["total_bytes"])

    assert isinstance(
        metrics_after1, dict
    ), f"Metrics_after1 should be dict, got {type(metrics_after1)}"
    assert "total_bytes" in metrics_after1, f"Metrics_after1 missing 'total_bytes' key"
    total_bytes_after1 = int(metrics_after1["total_bytes"])

    assert isinstance(
        metrics_after2, dict
    ), f"Metrics_after2 should be dict, got {type(metrics_after2)}"
    assert "total_bytes" in metrics_after2, f"Metrics_after2 missing 'total_bytes' key"
    total_bytes_after2 = int(metrics_after2["total_bytes"])

    data1_size = demo_result["data1_size"]
    data2_size = demo_result["data2_size"]

    # Verify first entry increments total_bytes correctly
    delta1 = total_bytes_after1 - total_bytes_before
    assert (
        delta1 == data1_size
    ), f"First entry delta mismatch: expected {data1_size}, got {delta1} (total_bytes_before={total_bytes_before}, total_bytes_after1={total_bytes_after1})"

    # Verify second entry increments total_bytes correctly
    delta2 = total_bytes_after2 - total_bytes_after1
    assert (
        delta2 == data2_size
    ), f"Second entry delta mismatch: expected {data2_size}, got {delta2} (total_bytes_after1={total_bytes_after1}, total_bytes_after2={total_bytes_after2})"

    # Verify final total is sum of both entries
    expected_total = total_bytes_before + data1_size + data2_size
    assert (
        total_bytes_after2 == expected_total
    ), f"Final total mismatch: expected {expected_total}, got {total_bytes_after2}"
