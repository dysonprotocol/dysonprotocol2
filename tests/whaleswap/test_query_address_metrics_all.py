"""
Query coverage for whaleswap address metrics endpoints.

Exercise both AddressMetrics and AddressMetricsAll CLI queries.
"""

import json


def test_query_address_metrics_all(chainnet):
    """Ensure the new AddressMetricsAll query returns the expected structure."""
    dysond = chainnet[0]
    gov_response = dysond("query", "auth", "module-account", "gov")
    account = gov_response["account"]
    assert isinstance(account, dict), (
        f"Gov account response must be dict. Full response: {json.dumps(gov_response, indent=2)}"
    )
    account_value = account["value"]
    assert isinstance(account_value, dict), (
        f"Gov account value must be dict. Full account: {json.dumps(account, indent=2)}"
    )
    gov_address = account_value["address"]
    assert isinstance(gov_address, str), (
        f"Gov address must be string. account_value: {json.dumps(account_value, indent=2)}"
    )

    metrics_all = dysond("query", "whaleswap", "address-metrics-all")
    assert isinstance(metrics_all, dict), (
        f"address-metrics-all must return dict. Response: {json.dumps(metrics_all, indent=2)}"
    )
    metrics_list = metrics_all.get("metrics", [])
    assert isinstance(metrics_list, list), (
        f"Metrics list must be list. Response: {json.dumps(metrics_all, indent=2)}"
    )
    assert "pagination" in metrics_all, (
        f"address-metrics-all missing pagination key. Response: {json.dumps(metrics_all, indent=2)}"
    )

    metrics_single = dysond(
        "query",
        "whaleswap",
        "address-metrics",
        "--address",
        gov_address,
    )
    assert isinstance(metrics_single, dict), (
        f"address-metrics must return dict. Response: {json.dumps(metrics_single, indent=2)}"
    )
    assert "metrics" in metrics_single, (
        f"address-metrics missing metrics field. Response: {json.dumps(metrics_single, indent=2)}"
    )
    single_metrics = metrics_single["metrics"]
    assert isinstance(single_metrics, dict), (
        f"Single metrics must be dict. Response: {json.dumps(metrics_single, indent=2)}"
    )
    assert single_metrics["address"] == gov_address, (
        f"Query should echo requested address. Expected {gov_address}, "
        f"got {single_metrics['address']}."
    )

