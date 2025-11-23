"""
AddressMetrics query handler coverage tests.

Tests the AddressMetrics query endpoint which retrieves lifetime activity
metrics for a specific address. Covers all validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_address_metrics_success_zero_state(chainnet):
    """Test AddressMetrics with valid address returning zero-value metrics."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded address with no activity
    fresh_addr = "dys216vwht46aw58efaxx"

    extra_code = """
from dys import _query

def demo_address_metrics(address):
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": address
    })
    return {"result": result}
"""

    kwargs = json.dumps({"address": fresh_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_address_metrics",
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
        result is not None
    ), f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    assert (
        "result" in demo_result
    ), f"Script should return result. Result: {json.dumps(demo_result, indent=2)}"
    metrics_response = demo_result["result"]

    # Validate response structure (Type)
    assert isinstance(
        metrics_response, dict
    ), f"Metrics response should be dict, got {type(metrics_response)}"
    assert (
        "metrics" in metrics_response
    ), f"Metrics response missing 'metrics' key. Keys: {list(metrics_response.keys())}"

    metrics = metrics_response["metrics"]

    # Validate metrics structure (Type + Shape)
    assert isinstance(metrics, dict), f"Metrics should be dict, got {type(metrics)}"
    assert (
        "address" in metrics
    ), f"Metrics missing 'address' key. Keys: {list(metrics.keys())}"
    assert (
        "block_height" in metrics
    ), f"Metrics missing 'block_height' key. Keys: {list(metrics.keys())}"

    # Validate values
    assert (
        metrics["address"] == fresh_addr
    ), f"Address mismatch: expected {fresh_addr}, got {metrics['address']}"
    assert isinstance(
        metrics["block_height"], (int, str)
    ), f"Block height should be int or str, got {type(metrics['block_height'])}"
    assert (
        int(metrics["block_height"]) > 0
    ), f"Block height should be positive, got {metrics['block_height']}"


def test_address_metrics_success_with_activity(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddressMetrics with valid address that has activity."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
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

def demo_address_metrics_with_activity(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool to generate activity
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.0"},
            {"denom": quote, "amount": "0.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    # Query metrics after activity
    metrics_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    return {
        "pool_id": pool_result["results"][0]["pool_id"],
        "metrics": metrics_result
    }
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_address_metrics_with_activity",
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
    assert (
        "metrics" in demo_result
    ), f"Script should return metrics. Result: {json.dumps(demo_result, indent=2)}"

    metrics_response = demo_result["metrics"]
    assert isinstance(
        metrics_response, dict
    ), f"Metrics response should be dict, got {type(metrics_response)}"
    assert (
        "metrics" in metrics_response
    ), f"Metrics response missing 'metrics' key. Keys: {list(metrics_response.keys())}"

    metrics = metrics_response["metrics"]
    assert isinstance(metrics, dict), f"Metrics should be dict, got {type(metrics)}"
    assert (
        metrics["address"] == alice_addr
    ), f"Address mismatch: expected {alice_addr}, got {metrics['address']}"
    assert (
        int(metrics.get("pools_created", 0)) == 1
    ), f"Should have 1 pool created. Metrics: {json.dumps(metrics, indent=2)}"


def test_address_metrics_empty_address(chainnet):
    """Test AddressMetrics with empty address string."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_address():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": ""
    })
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_empty_address",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for empty address. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "address required" in exception_str
    ), f"Expected 'address required' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"


def test_address_metrics_invalid_bech32(chainnet):
    """Test AddressMetrics with invalid bech32 address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_invalid_address():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": "invalid_bech32_address_12345"
    })
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_invalid_address",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for invalid address. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "invalid address" in exception_str
    ), f"Expected 'invalid address' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"
