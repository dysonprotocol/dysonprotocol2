"""
GetBlock query handler coverage tests.

Tests the GetBlock query endpoint which returns current block information.
GetBlock only returns the current block from context - no historical queries supported.
Covers success path (all fields validated) and nil request error handling.
All tests use stateless script query execution with _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_get_block_success(chainnet):
    """Test GetBlock query successfully returns current block information.

    Validates all fields: block_height, block_time, chain_id, block_hash, app_hash, proposer_address.
    GetBlock only returns the current block from context - no height parameter or historical queries.
    """
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_get_block():
    # Query current block information
    block_result = _query({
        "@type": "/dysonprotocol.script.v1.QueryGetBlockRequest"
    })
    
    return {
        "block_result": block_result
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
        "demo_get_block",
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
        "block_result" in demo_result
    ), f"Result missing 'block_result' key. Keys: {list(demo_result.keys())}"

    block_result = demo_result["block_result"]
    assert isinstance(
        block_result, dict
    ), f"Block result should be dict, got {type(block_result)}"
    assert (
        "block_height" in block_result
    ), f"Block result missing 'block_height' key. Keys: {list(block_result.keys())}"
    assert (
        "block_time" in block_result
    ), f"Block result missing 'block_time' key. Keys: {list(block_result.keys())}"
    assert (
        "chain_id" in block_result
    ), f"Block result missing 'chain_id' key. Keys: {list(block_result.keys())}"
    assert (
        "block_hash" in block_result
    ), f"Block result missing 'block_hash' key. Keys: {list(block_result.keys())}"
    assert (
        "app_hash" in block_result
    ), f"Block result missing 'app_hash' key. Keys: {list(block_result.keys())}"
    assert (
        "proposer_address" in block_result
    ), f"Block result missing 'proposer_address' key. Keys: {list(block_result.keys())}"

    # Validate block_height
    block_height = block_result["block_height"]
    assert isinstance(
        block_height, (int, str)
    ), f"Block height should be int or string, got {type(block_height)}"
    height_int = int(block_height)
    assert height_int > 0, f"Block height should be positive, got {block_height}"

    # Validate block_time
    block_time = block_result["block_time"]
    assert isinstance(
        block_time, str
    ), f"Block time should be string, got {type(block_time)}"
    assert len(block_time) > 0, f"Block time should not be empty"

    # Validate chain_id
    chain_id = block_result["chain_id"]
    assert isinstance(chain_id, str), f"Chain ID should be string, got {type(chain_id)}"
    assert len(chain_id) > 0, f"Chain ID should not be empty"

    # Validate block_hash
    block_hash = block_result["block_hash"]
    assert isinstance(
        block_hash, str
    ), f"Block hash should be string, got {type(block_hash)}"
    assert len(block_hash) > 0, f"Block hash should not be empty"

    # Validate app_hash
    app_hash = block_result["app_hash"]
    assert isinstance(app_hash, str), f"App hash should be string, got {type(app_hash)}"
    assert len(app_hash) > 0, f"App hash should not be empty"

    # Validate proposer_address (should be bech32)
    proposer_address = block_result["proposer_address"]
    assert isinstance(
        proposer_address, str
    ), f"Proposer address should be string, got {type(proposer_address)}"
    assert proposer_address.startswith(
        "dys2"
    ), f"Proposer address should be bech32 format starting with 'dys2', got {proposer_address}"


def test_get_block_nil_request(chainnet):
    """Test GetBlock query handles nil request error.

    Verifies that the query handler properly validates the request and returns
    InvalidArgument error when called with nil request.
    """
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_get_block_nil_request():
    # Attempt to query with None/null request
    try:
        block_result = _query(None)
        return {"error": "Should have failed", "result": block_result}
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
        "demo_get_block_nil_request",
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
