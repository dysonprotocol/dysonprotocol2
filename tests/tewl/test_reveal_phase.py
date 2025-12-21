"""
Test reveal phase for TEWL (Tool for External World Lookups).

Stateless tests using query script run with --extra-code.
"""

import json


def test_validate_against_schema_valid_string(chainnet, tewl_script_code):
    """Test schema validation for valid string."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    data = {"answer": "hello"}
    return {"valid": _validate_against_schema(data, schema)}
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
        "demo_validate",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["valid"] is True


def test_validate_against_schema_invalid_type(chainnet, tewl_script_code):
    """Test schema validation rejects wrong type."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    data = {"answer": 123}  # number instead of string
    return {"valid": _validate_against_schema(data, schema)}
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
        "demo_validate",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["valid"] is False


def test_validate_against_schema_number(chainnet, tewl_script_code):
    """Test schema validation for number type."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate():
    schema = {"type": "object", "properties": {"value": {"type": "number"}}}
    valid_int = {"value": 42}
    valid_float = {"value": 3.14}
    invalid = {"value": "not a number"}
    return {
        "valid_int": _validate_against_schema(valid_int, schema),
        "valid_float": _validate_against_schema(valid_float, schema),
        "invalid": _validate_against_schema(invalid, schema)
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
        "demo_validate",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    assert result["valid_int"] is True
    assert result["valid_float"] is True
    assert result["invalid"] is False


def test_validate_against_schema_nested(chainnet, tewl_script_code):
    """Test schema validation for nested objects."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate():
    schema = {
        "type": "object",
        "properties": {
            "outer": {
                "type": "object",
                "properties": {
                    "inner": {"type": "string"}
                }
            }
        }
    }
    valid = {"outer": {"inner": "hello"}}
    invalid = {"outer": {"inner": 123}}
    return {
        "valid": _validate_against_schema(valid, schema),
        "invalid": _validate_against_schema(invalid, schema)
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
        "demo_validate",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    assert result["valid"] is True
    assert result["invalid"] is False
