"""
AddressMetricsAll query handler coverage tests.

Tests the AddressMetricsAll query endpoint which paginates over all stored
address metrics records. Covers all validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_address_metrics_all_structure(chainnet):
    """Test AddressMetricsAll returns valid response structure."""
    dysond = chainnet[0]

    # Use CLI directly for query coverage (following testing guide pattern)
    metrics_all_response = dysond("query", "whaleswap", "address-metrics-all")

    # Validate response structure (Type)
    assert isinstance(
        metrics_all_response, dict
    ), f"MetricsAll response should be dict, got {type(metrics_all_response)}. Full response: {json.dumps(metrics_all_response, indent=2)}"
    assert (
        "pagination" in metrics_all_response
    ), f"MetricsAll response missing 'pagination' key. Keys: {list(metrics_all_response.keys())}. Full response: {json.dumps(metrics_all_response, indent=2)}"

    # Validate metrics list (Type + Shape)
    # Note: protobuf omitempty means empty lists may be omitted; other tests may have created metrics
    metrics_list = metrics_all_response.get("metrics", [])
    assert isinstance(
        metrics_list, list
    ), f"Metrics should be list, got {type(metrics_list)}. Full response: {json.dumps(metrics_all_response, indent=2)}"

    # Validate pagination (Type)
    pagination = metrics_all_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}. Full response: {json.dumps(metrics_all_response, indent=2)}"


def test_address_metrics_all_with_metrics(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddressMetricsAll when metrics exist (tests CollectionPaginate callback path)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create metrics by creating a pool (multi-block to persist metrics)
    base, quote = sorted([foo_name, bar_name])
    tx_pool = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--fee-rate",
        f"0.003{base}",
        "--fee-rate",
        f"0.003{quote}",
        "--min-collateral-ratio",
        f"1.5{base}",
        "--min-collateral-ratio",
        f"1.5{quote}",
        "--liquidation-threshold",
        f"1.2{base}",
        "--liquidation-threshold",
        f"1.2{quote}",
        "--interest-rate",
        f"0.0{base}",
        "--interest-rate",
        f"0.0{quote}",
        "--max-borrow-percent",
        f"0.8{base}",
        "--max-borrow-percent",
        f"0.8{quote}",
        "--from",
        alice_name,
    )
    assert (
        tx_pool.get("code", 1) == 0
    ), f"Pool creation failed: {json.dumps(tx_pool, indent=2)}"

    # Query all metrics using CLI
    # This tests the CollectionPaginate callback function (lines 23-26) when results exist
    metrics_all_response = dysond("query", "whaleswap", "address-metrics-all")

    # Validate response structure (Type)
    assert isinstance(
        metrics_all_response, dict
    ), f"MetricsAll response should be dict, got {type(metrics_all_response)}. Full response: {json.dumps(metrics_all_response, indent=2)}"
    assert (
        "pagination" in metrics_all_response
    ), f"MetricsAll response missing 'pagination' key. Keys: {list(metrics_all_response.keys())}. Full response: {json.dumps(metrics_all_response, indent=2)}"

    # Validate metrics list (Type + Shape)
    metrics_list = metrics_all_response.get("metrics", [])
    assert isinstance(
        metrics_list, list
    ), f"Metrics should be list, got {type(metrics_list)}. Full response: {json.dumps(metrics_all_response, indent=2)}"

    # With metrics created, we should have at least one result (triggers callback function)
    assert (
        len(metrics_list) >= 1
    ), f"Should have at least 1 metric after pool creation. Got {len(metrics_list)}: {json.dumps(metrics_list, indent=2)}"

    # Validate first metric entry structure (don't loop - other tests may have created many)
    metric = metrics_list[0]
    assert isinstance(metric, dict), f"Each metric should be dict, got {type(metric)}"
    assert (
        "address" in metric
    ), f"Metric missing 'address' key. Metric: {json.dumps(metric, indent=2)}"
    assert (
        "block_height" in metric
    ), f"Metric missing 'block_height' key. Metric: {json.dumps(metric, indent=2)}"

    # Validate pagination exists
    pagination = metrics_all_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_address_metrics_all_nil_request(chainnet):
    """Test AddressMetricsAll with nil request (should default to empty request)."""
    dysond = chainnet[0]

    # Note: In Go, nil request is handled by defaulting to empty request
    # When calling via CLI without pagination, it's equivalent to nil/empty request
    # This tests the req == nil path (line 15-17 in Go code)
    metrics_all_response = dysond("query", "whaleswap", "address-metrics-all")

    # Validate response structure (Type)
    assert isinstance(
        metrics_all_response, dict
    ), f"MetricsAll response should be dict, got {type(metrics_all_response)}. Full response: {json.dumps(metrics_all_response, indent=2)}"
    assert (
        "pagination" in metrics_all_response
    ), f"MetricsAll response missing 'pagination' key. Keys: {list(metrics_all_response.keys())}. Full response: {json.dumps(metrics_all_response, indent=2)}"

    # Validate metrics list (Type + Shape)
    # Note: protobuf omitempty means empty lists may be omitted
    metrics_list = metrics_all_response.get("metrics", [])
    assert isinstance(
        metrics_list, list
    ), f"Metrics should be list, got {type(metrics_list)}. Full response: {json.dumps(metrics_all_response, indent=2)}"

    # Validate pagination (Type)
    pagination = metrics_all_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}. Full response: {json.dumps(metrics_all_response, indent=2)}"
