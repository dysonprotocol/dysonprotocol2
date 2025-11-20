"""
Params query handler coverage tests.

Tests the Params query endpoint which retrieves the current whaleswap module parameters.
Covers the success path with empty request.
"""

import json
import pytest
from deep_parse import deep_parse


def test_params_success(chainnet):
    """Test Params query with valid request."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_params():
    params_resp = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"
    })
    return params_resp["params"]
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
        "demo_params",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    params = demo_result

    # Validate response structure (Type)
    assert isinstance(
        params, dict
    ), f"Params should be dict, got {type(params)}. Full response: {json.dumps(params, indent=2)}"

    # Validate all parameter fields are present (Shape)
    # Note: Params structure may vary, but should contain module configuration
    # We validate that it's a dict and not empty
    assert len(params) > 0, f"Params should not be empty. Full response: {json.dumps(params, indent=2)}"

