"""
QueryAddressMetrics coverage for whaleswap leverage suite.

Verifies the keeper returns zeroed metrics for inactive accounts and
rejects invalid query parameters, exercising getOrCreateMetrics along
with the AddressMetrics query validation path.
"""

import json
from deep_parse import deep_parse


def test_address_metrics_zero_state(chainnet, generate_account):
    """Querying metrics for a fresh address should return zero counters."""
    dysond = chainnet[0]
    _, fresh_addr = generate_account("metrics_zero", faucet_amount=1000000)

    metrics_resp = dysond(
        "query",
        "whaleswap",
        "address-metrics",
        f"--address={fresh_addr}",
    )
    assert isinstance(
        metrics_resp, dict
    ), f"address-metrics response must be dict: {json.dumps(metrics_resp, indent=2)}"
    metrics = metrics_resp.get("metrics")
    assert isinstance(
        metrics, dict
    ), f"metrics payload missing: {json.dumps(metrics_resp, indent=2)}"
    assert (
        metrics.get("address") == fresh_addr
    ), f"address echo mismatch: {json.dumps(metrics, indent=2)}"

    zero_fields = [
        "pools_created",
        "liquidity_adds",
        "liquidity_removes",
        "positions_opened",
        "positions_closed",
        "offers_created",
        "offers_closed",
        "offers_cancelled",
        "auctions_created",
    ]
    for field in zero_fields:
        value = int(metrics.get(field, 0))
        assert value == 0, f"{field} should be zero: {json.dumps(metrics, indent=2)}"


def test_address_metrics_invalid_address(chainnet):
    """Invalid bech32 addresses should fail validation."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _query

def demo_invalid_address():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": "invalid_bech32"
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
    ), f"expected invalid address error: {json.dumps(query_result, indent=2)}"
    assert (
        "invalid address" in str(query_result["exception"]).lower()
    ), f"missing invalid address detail: {json.dumps(query_result, indent=2)}"


def test_address_metrics_missing_address(chainnet):
    """Empty address strings should return ErrInvalidRequest."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _query

def demo_missing_address():
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
        "demo_missing_address",
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert isinstance(
        parsed, dict
    ), f"deep_parse should return dict: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is not None
    ), f"expected address required error: {json.dumps(query_result, indent=2)}"
    assert (
        "address required" in str(query_result["exception"]).lower()
    ), f"missing address required detail: {json.dumps(query_result, indent=2)}"
