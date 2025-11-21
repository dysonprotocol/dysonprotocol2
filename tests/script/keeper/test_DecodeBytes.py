"""
DecodeBytes query handler coverage tests.

Tests the DecodeBytes query endpoint which decodes protobuf bytes to JSON strings.
Covers success path, invalid bytes, unknown type URL, oversized payload, and nil request error handling.
All tests use stateless script query execution with _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_decode_bytes_success(chainnet):
    """Test DecodeBytes query successfully decodes valid protobuf bytes."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query
import json

def demo_decode_bytes():
    # First encode a message to get valid protobuf bytes
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
    
    # Now decode the bytes back to JSON
    decode_result = _query({
        "@type": "/dysonprotocol.script.v1.QueryDecodeBytesRequest",
        "type_url": "/cosmos.bank.v1beta1.MsgSend",
        "bytes": encode_result["bytes"]
    })
    
    return {
        "decode_result": decode_result
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
        "demo_decode_bytes",
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
        "decode_result" in demo_result
    ), f"Result missing 'decode_result' key. Keys: {list(demo_result.keys())}"

    decode_result = demo_result["decode_result"]
    assert isinstance(
        decode_result, dict
    ), f"Decode result should be dict, got {type(decode_result)}"
    assert (
        "json" in decode_result
    ), f"Decode result missing 'json' key. Keys: {list(decode_result.keys())}"

    json_field = decode_result["json"]
    # deep_parse already parses JSON strings into dicts
    assert isinstance(
        json_field, dict
    ), f"JSON field should be dict (parsed by deep_parse), got {type(json_field)}"

    # Verify the decoded JSON contains the original message fields
    assert (
        "from_address" in json_field
    ), f"Decoded JSON missing 'from_address'. Keys: {list(json_field.keys())}"
    assert (
        json_field["from_address"] == "dys1example"
    ), f"Expected 'dys1example', got {json_field.get('from_address')}"


def test_decode_bytes_invalid_bytes(chainnet):
    """Test DecodeBytes query handles invalid protobuf bytes."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query
import base64

def demo_decode_invalid_bytes():
    # Attempt to decode invalid bytes (not valid protobuf)
    invalid_bytes = base64.b64encode(b"invalid protobuf data").decode('utf-8')
    
    try:
        decode_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryDecodeBytesRequest",
            "type_url": "/cosmos.bank.v1beta1.MsgSend",
            "bytes": invalid_bytes
        })
        return {"error": "Should have failed", "result": decode_result}
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
        "demo_decode_invalid_bytes",
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


def test_decode_bytes_unknown_type_url(chainnet):
    """Test DecodeBytes query handles unknown type URL."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query
import base64

def demo_decode_unknown_type():
    # Attempt to decode with unknown type URL
    some_bytes = base64.b64encode(b"some data").decode('utf-8')
    
    try:
        decode_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryDecodeBytesRequest",
            "type_url": "/unknown.type.v1.MsgUnknown",
            "bytes": some_bytes
        })
        return {"error": "Should have failed", "result": decode_result}
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
        "demo_decode_unknown_type",
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
        "failed to get message from type url" in error_str.lower()
    ), f"Expected 'failed to get message from type url' in error message, got: {error_str}"


def test_decode_bytes_oversized_payload(chainnet):
    """Test DecodeBytes query handles oversized payload (>10,000 bytes)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query
import base64

def demo_decode_oversized():
    # Create bytes > 10,000 bytes
    large_bytes = base64.b64encode(b'x' * 10001).decode('utf-8')
    
    try:
        decode_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryDecodeBytesRequest",
            "type_url": "/cosmos.bank.v1beta1.MsgSend",
            "bytes": large_bytes
        })
        return {"error": "Should have failed", "result": decode_result}
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
        "demo_decode_oversized",
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


def test_decode_bytes_nil_request(chainnet):
    """Test DecodeBytes query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_decode_nil_request():
    # Attempt to query with None/null request
    try:
        decode_result = _query(None)
        return {"error": "Should have failed", "result": decode_result}
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
        "demo_decode_nil_request",
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
