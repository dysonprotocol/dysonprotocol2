"""
ResolveName query handler coverage tests.

Tests the ResolveName query endpoint which resolves nameservice names to addresses
or returns addresses directly if already an address. Supports iterative resolution
following name chains.

Covers success paths (name resolves to address, address returns itself) and error paths
(empty name_or_address, name not found). All tests use stateless script query execution.
"""

import json
import pytest
import secrets
import re
from deep_parse import deep_parse


def test_resolve_name_success(chainnet, generate_account):
    """Test ResolveName query successfully resolves a registered name to address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    # Generate a unique name
    name_suffix = secrets.token_hex(4)
    name = f"test-{name_suffix}.dys"
    salt = secrets.token_hex(8)

    extra_code = f"""
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {{"denom": m.group(2), "amount": m.group(1)}}

def demo_resolve_name_success(name, salt, alice_addr):
    owner = get_executor_address()
    
    # Compute commitment hash
    hexhash = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    }})["hex_hash"]
    
    # Commit
    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin("10udys"),
    }})
    
    # Reveal (creates the name NFT)
    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    }})
    
    # Set destination to alice_addr
    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": alice_addr,
    }})
    
    # Now resolve the name
    resolve_result = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
        "name_or_address": name
    }})
    
    return {{
        "resolve_result": resolve_result
    }}
"""

    kwargs = json.dumps({"name": name, "salt": salt, "alice_addr": alice_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_resolve_name_success",
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
        "resolve_result" in demo_result
    ), f"Result missing 'resolve_result' key. Keys: {list(demo_result.keys())}"

    resolve_result = demo_result["resolve_result"]
    assert isinstance(
        resolve_result, dict
    ), f"Resolve result should be dict, got {type(resolve_result)}"
    assert (
        "address" in resolve_result
    ), f"Resolve result missing 'address' key. Keys: {list(resolve_result.keys())}"

    resolved_address = resolve_result["address"]
    assert isinstance(
        resolved_address, str
    ), f"Resolved address should be string, got {type(resolved_address)}"
    assert (
        resolved_address == alice_addr
    ), f"Resolved address should be {alice_addr}, got {resolved_address}"


def test_resolve_name_address_returns_itself(chainnet, generate_account):
    """Test ResolveName query returns address directly when passed an address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    extra_code = """
from dys import _query

def demo_resolve_name_address(alice_addr):
    # Resolve an address (should return itself)
    resolve_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
        "name_or_address": alice_addr
    })
    
    return {
        "resolve_result": resolve_result
    }
"""

    kwargs = json.dumps({"alice_addr": alice_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_resolve_name_address",
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
    resolve_result = demo_result["resolve_result"]
    resolved_address = resolve_result["address"]
    assert (
        resolved_address == alice_addr
    ), f"Address should return itself. Expected {alice_addr}, got {resolved_address}"


def test_resolve_name_not_found(chainnet):
    """Test ResolveName query returns error for non-existent name."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    non_existent_name = "nonexistent12345.dys"

    extra_code = """
from dys import _query

def demo_resolve_name_not_found(name):
    try:
        resolve_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
            "name_or_address": name
        })
        return {"error": "Should have failed", "result": resolve_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"name": non_existent_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_resolve_name_not_found",
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
        "not found" in error_msg.lower()
    ), f"Error message should mention 'not found'. Got: {error_msg}"


def test_resolve_name_empty_name_or_address(chainnet):
    """Test ResolveName query returns error for empty name_or_address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_resolve_name_empty():
    try:
        resolve_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
            "name_or_address": ""
        })
        return {"error": "Should have failed", "result": resolve_result}
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
        "demo_resolve_name_empty",
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
        "name_or_address" in error_msg.lower() and "empty" in error_msg.lower()
    ), f"Error message should mention 'name_or_address cannot be empty'. Got: {error_msg}"


def test_resolve_name_nil_request(chainnet):
    """Test ResolveName query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_resolve_name_nil_request():
    try:
        resolve_result = _query(None)
        return {"error": "Should have failed", "result": resolve_result}
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
        "demo_resolve_name_nil_request",
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
