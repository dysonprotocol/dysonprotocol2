"""
ComputeHash query handler coverage tests.

Tests the ComputeHash query endpoint which computes the hash for name registration
using the commit-reveal scheme. The hash is computed as SHA256(name:committer:salt).

Covers success path (valid inputs) and error paths (empty name, empty salt, empty committer).
All tests use stateless script query execution with _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_compute_hash_success(chainnet):
    """Test ComputeHash query successfully computes hash for valid inputs."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded test address
    alice_addr = "dys216vwht46aw58efaxx"

    name = "testname.dys"
    salt = "randomsalt123"
    committer = alice_addr

    extra_code = """
from dys import _query

def demo_compute_hash(name, salt, committer):
    # Query hash computation
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": committer
    })
    
    return {
        "hash_result": hash_result
    }
"""

    kwargs = json.dumps({"name": name, "salt": salt, "committer": committer})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_compute_hash",
        "--kwargs",
        kwargs,
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
        "hash_result" in demo_result
    ), f"Result missing 'hash_result' key. Keys: {list(demo_result.keys())}"

    hash_result = demo_result["hash_result"]
    assert isinstance(
        hash_result, dict
    ), f"Hash result should be dict, got {type(hash_result)}"
    assert (
        "hex_hash" in hash_result
    ), f"Hash result missing 'hex_hash' key. Keys: {list(hash_result.keys())}"

    hex_hash = hash_result["hex_hash"]
    assert isinstance(hex_hash, str), f"Hex hash should be string, got {type(hex_hash)}"
    assert (
        len(hex_hash) == 64
    ), f"Hex hash should be 64 characters (SHA256), got {len(hex_hash)}"
    assert all(
        c in "0123456789abcdef" for c in hex_hash
    ), f"Hex hash should contain only hex characters, got {hex_hash}"


def test_compute_hash_empty_name(chainnet, generate_account):
    """Test ComputeHash query returns error for empty name."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    salt = "randomsalt123"
    committer = alice_addr

    extra_code = """
from dys import _query

def demo_compute_hash_empty_name(salt, committer):
    try:
        hash_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
            "name": "",
            "salt": salt,
            "committer": committer
        })
        return {"error": "Should have failed", "hash_result": hash_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"salt": salt, "committer": committer})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_compute_hash_empty_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        "expected" in demo_result
    ), f"Expected error but got success. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result["expected"] is True
    error_msg = demo_result.get("error", "")
    assert (
        "name cannot be empty" in error_msg.lower()
    ), f"Error message should mention 'name cannot be empty'. Got: {error_msg}"


def test_compute_hash_empty_salt(chainnet, generate_account):
    """Test ComputeHash query returns error for empty salt."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    name = "testname.dys"
    committer = alice_addr

    extra_code = """
from dys import _query

def demo_compute_hash_empty_salt(name, committer):
    try:
        hash_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
            "name": name,
            "salt": "",
            "committer": committer
        })
        return {"error": "Should have failed", "hash_result": hash_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"name": name, "committer": committer})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_compute_hash_empty_salt",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        "expected" in demo_result
    ), f"Expected error but got success. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result["expected"] is True
    error_msg = demo_result.get("error", "")
    assert (
        "salt cannot be empty" in error_msg.lower()
    ), f"Error message should mention 'salt cannot be empty'. Got: {error_msg}"


def test_compute_hash_empty_committer(chainnet):
    """Test ComputeHash query returns error for empty committer."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    name = "testname.dys"
    salt = "randomsalt123"

    extra_code = """
from dys import _query

def demo_compute_hash_empty_committer(name, salt):
    try:
        hash_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
            "name": name,
            "salt": salt,
            "committer": ""
        })
        return {"error": "Should have failed", "hash_result": hash_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"name": name, "salt": salt})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_compute_hash_empty_committer",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert (
        "expected" in demo_result
    ), f"Expected error but got success. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result["expected"] is True
    error_msg = demo_result.get("error", "")
    assert (
        "committer" in error_msg.lower()
    ), f"Error message should mention 'committer'. Got: {error_msg}"
    assert (
        "empty" in error_msg.lower()
    ), f"Error message should mention 'empty'. Got: {error_msg}"


def test_compute_hash_deterministic(chainnet, generate_account):
    """Test ComputeHash returns the same hash for the same inputs."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    name = "testname.dys"
    salt = "randomsalt123"
    committer = alice_addr

    extra_code = """
from dys import _query

def demo_compute_hash_deterministic(name, salt, committer):
    # Query hash computation twice with same inputs
    hash_result1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": committer
    })
    
    hash_result2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": committer
    })
    
    return {
        "hash1": hash_result1["hex_hash"],
        "hash2": hash_result2["hex_hash"]
    }
"""

    kwargs = json.dumps({"name": name, "salt": salt, "committer": committer})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_compute_hash_deterministic",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    hash1 = demo_result["hash1"]
    hash2 = demo_result["hash2"]
    assert (
        hash1 == hash2
    ), f"Hash should be deterministic. Got hash1={hash1}, hash2={hash2}"


def test_compute_hash_nil_request(chainnet):
    """Test ComputeHash query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_compute_hash_nil_request():
    # Attempt to query with None/null request
    try:
        hash_result = _query(None)
        return {"error": "Should have failed", "result": hash_result}
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
        "demo_compute_hash_nil_request",
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
