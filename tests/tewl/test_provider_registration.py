"""
Test provider registration for TEWL (Tool for External World Lookups).

Stateless tests using query script run with --extra-code.
"""

import json


def test_get_initial_state(chainnet, tewl_script_code):
    """Test getting initial protocol state."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_get_state():
    return {"state": _get_state()}
"""
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
        "demo_get_state",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    state = result_data["result"]["state"]

    assert state["next_request_id"] == 1
    assert state["min_bond"] == "1000000"
    assert state["active_request_id"] is None


def test_provider_index(chainnet, tewl_script_code):
    """Test provider index generation."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_provider_index():
    idx = _provider_index("dys1abc123")
    return {"index": idx}
"""
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
        "demo_provider_index",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["index"] == "p/dys1abc123"


def test_get_provider_not_found(chainnet, tewl_script_code):
    """Test get_provider returns None for non-existent provider."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_get_nonexistent():
    provider = get_provider("dys1nonexistent")
    return {"provider": provider}
"""
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
        "demo_get_nonexistent",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["provider"] is None


def test_status_constants(chainnet, tewl_script_code):
    """Test status constants are defined."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_statuses():
    return {
        "active": STATUS_ACTIVE,
        "inactive": STATUS_INACTIVE,
        "jailed": STATUS_JAILED
    }
"""
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
        "demo_statuses",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    assert result["active"] == "active"
    assert result["inactive"] == "inactive"
    assert result["jailed"] == "jailed"


def test_get_active_providers_empty(chainnet, tewl_script_code):
    """Test get_active_providers returns empty list when no providers."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_active_providers():
    return {"providers": get_active_providers()}
"""
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
        "demo_active_providers",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["providers"] == []
