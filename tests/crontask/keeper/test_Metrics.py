"""
Metrics query handler coverage tests.

Tests the Metrics query endpoint which retrieves last-block operational metrics.
Covers success case with metrics validation.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
from deep_parse import deep_parse


def test_metrics_query(chainnet):
    """Test Metrics query returns last-block operational metrics."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_metrics_query():
    # Query operational metrics
    metrics_result = _query({
        "@type": "/dysonprotocol.crontask.v1.QueryMetricsRequest"
    })
    return {"metrics_result": metrics_result}
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
        "demo_metrics_query",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "metrics_result" in demo_result
    ), f"Result missing 'metrics_result' key. Keys: {list(demo_result.keys())}"

    metrics_result = demo_result["metrics_result"]
    assert isinstance(metrics_result, dict), f"Metrics result should be dict, got {type(metrics_result)}"
    assert "metrics" in metrics_result, f"Metrics result missing 'metrics' key. Keys: {list(metrics_result.keys())}"

    metrics = metrics_result["metrics"]
    assert isinstance(metrics, dict), f"Metrics should be dict, got {type(metrics)}"

    # Verify expected metrics structure (may be zero-initialized)
    expected_keys = ["executed_total_gas", "executed_total_fees", "executed_task_count", "pending_task_count", "pending_gas_requested", "pending_oldest_scheduled_ts"]
    for key in expected_keys:
        assert key in metrics, f"Metrics missing expected key '{key}'. Keys: {list(metrics.keys())}"
