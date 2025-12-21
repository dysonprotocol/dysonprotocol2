"""
Test request creation for TEWL (Tool for External World Lookups).

Stateless tests using query script run with --extra-code.
"""

import json


VALID_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}

VALID_SCORER = """
def scorer(reveal, state):
    if state is None:
        state = {"result": None, "scores": {}}
    state["result"] = reveal["response"]
    state["scores"][reveal["provider"]] = 1.0
    return state
"""


def test_validate_scorer_success(chainnet, tewl_script_code):
    """Test scorer validation accepts valid scorer."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate_scorer():
    scorer = '''
def scorer(reveal, state):
    return state
'''
    try:
        _validate_scorer(scorer)
        return {"valid": True}
    except ValueError as e:
        return {"valid": False, "error": str(e)}
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
        "demo_validate_scorer",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["valid"] is True


def test_validate_scorer_missing_function(chainnet, tewl_script_code):
    """Test scorer validation rejects missing scorer function."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate_bad_scorer():
    scorer = '''
def other_func():
    pass
'''
    try:
        _validate_scorer(scorer)
        return {"valid": True}
    except ValueError as e:
        return {"valid": False, "error": str(e)}
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
        "demo_validate_bad_scorer",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["valid"] is False
    assert "scorer" in result_data["result"]["error"]


def test_validate_response_schema_valid(chainnet, tewl_script_code):
    """Test response schema validation accepts valid schema."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate_schema():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    try:
        _validate_response_schema(schema)
        return {"valid": True}
    except ValueError as e:
        return {"valid": False, "error": str(e)}
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
        "demo_validate_schema",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["valid"] is True


def test_validate_response_schema_invalid(chainnet, tewl_script_code):
    """Test response schema validation rejects invalid schema."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate_bad_schema():
    schema = "not a dict"
    try:
        _validate_response_schema(schema)
        return {"valid": True}
    except ValueError as e:
        return {"valid": False, "error": str(e)}
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
        "demo_validate_bad_schema",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["valid"] is False


def test_request_index(chainnet, tewl_script_code):
    """Test request index generation."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_request_index():
    return {"index": _request_index(42)}
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
        "demo_request_index",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["index"] == "r/42"


def test_request_statuses(chainnet, tewl_script_code):
    """Test request status constants."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_req_statuses():
    return {
        "pending": REQ_PENDING,
        "active": REQ_ACTIVE,
        "revealing": REQ_REVEALING,
        "resolved": REQ_RESOLVED,
        "failed": REQ_FAILED
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
        "demo_req_statuses",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    assert result["pending"] == "pending"
    assert result["active"] == "active"
    assert result["revealing"] == "revealing"
    assert result["resolved"] == "resolved"
    assert result["failed"] == "failed"
