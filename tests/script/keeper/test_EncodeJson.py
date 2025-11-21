"""
EncodeJson query handler coverage tests.

Tests the EncodeJson query endpoint which encodes JSON strings to protobuf bytes.
Covers success path, invalid JSON, oversized payload, and nil request error handling.
All tests use stateless script query execution with _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_encode_json_success(chainnet):
    """Test EncodeJson query successfully encodes valid JSON message."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query
import json

def demo_encode_json():
    # Encode a valid Cosmos SDK message
    test_msg = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": "dys1example",
        "to_address": "dys1example",
        "amount": [{"denom": "udys", "amount": "100"}]
    }
    
    encode_result = _query({
        "@type": "/dysonprotocol.script.v1.QueryEncodeJsonRequest",
        "json": json.dumps(test_msg)
    })
    
    return {
        "encode_result": encode_result
    }
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
        "demo_encode_json",
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
        "encode_result" in demo_result
    ), f"Result missing 'encode_result' key. Keys: {list(demo_result.keys())}"

    encode_result = demo_result["encode_result"]
    assert isinstance(
        encode_result, dict
    ), f"Encode result should be dict, got {type(encode_result)}"
    assert (
        "bytes" in encode_result
    ), f"Encode result missing 'bytes' key. Keys: {list(encode_result.keys())}"

    bytes_field = encode_result["bytes"]
    assert isinstance(
        bytes_field, str
    ), f"Bytes field should be base64 string, got {type(bytes_field)}"
    assert (
        len(bytes_field) > 0
    ), f"Bytes field should not be empty. Result: {json.dumps(encode_result, indent=2)}"


def test_encode_json_invalid_json(chainnet):
    """Test EncodeJson query handles invalid JSON payload."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_encode_invalid_json():
    # Attempt to encode invalid JSON
    try:
        encode_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryEncodeJsonRequest",
            "json": "{invalid json}"
        })
        return {"error": "Should have failed", "result": encode_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_encode_invalid_json",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"
    assert (
        "error" in demo_result
    ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
    error_str = demo_result["error"]
    assert isinstance(error_str, str), f"Error should be string, got {type(error_str)}"
    assert (
        len(error_str) > 0
    ), f"Error message should not be empty. Result: {json.dumps(demo_result, indent=2)}"


def test_encode_json_unknown_type(chainnet):
    """Test EncodeJson query handles unknown message type."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query
import json

def demo_encode_unknown_type():
    # Attempt to encode JSON with unknown type URL
    try:
        test_msg = {
            "@type": "/unknown.type.v1.MsgUnknown",
            "field": "value"
        }
        encode_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryEncodeJsonRequest",
            "json": json.dumps(test_msg)
        })
        return {"error": "Should have failed", "result": encode_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_encode_unknown_type",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"
    assert (
        "error" in demo_result
    ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
    error_str = demo_result["error"]
    assert isinstance(error_str, str), f"Error should be string, got {type(error_str)}"
    assert (
        len(error_str) > 0
    ), f"Error message should not be empty. Result: {json.dumps(demo_result, indent=2)}"


def test_encode_json_oversized_payload(chainnet):
    """Test EncodeJson query handles oversized payload (>10,000 characters)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_encode_oversized():
    # Create a JSON string > 10,000 characters
    large_json = '{"field": "' + 'x' * 10001 + '"}'
    
    try:
        encode_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryEncodeJsonRequest",
            "json": large_json
        })
        return {"error": "Should have failed", "result": encode_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_encode_oversized",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"
    assert (
        "error" in demo_result
    ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
    error_str = demo_result["error"]
    assert isinstance(error_str, str), f"Error should be string, got {type(error_str)}"
    assert (
        "too long" in error_str.lower()
    ), f"Expected 'too long' in error message, got: {error_str}"


def test_encode_json_nil_request(chainnet):
    """Test EncodeJson query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_encode_nil_request():
    # Attempt to query with None/null request
    try:
        encode_result = _query(None)
        return {"error": "Should have failed", "result": encode_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_encode_nil_request",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"
