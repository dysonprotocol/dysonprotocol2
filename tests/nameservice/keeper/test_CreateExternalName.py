"""
Test CreateExternalName message handler for nameservice keeper.

Tests the external name creation functionality which allows authorities
to create external domain names (e.g., example.com) without the
commit-reveal scheme required for regular .dys names.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_create_external_name_success(chainnet):
    """Test successful external name creation with valid authority."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_create_external_name(authority, name):
    # Create external name as authority
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({"authority": gov_addr, "name": "example.com"})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_create_external_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Validate sudo result - _sudo returns MsgSudoResponse on success
    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"sudo_result should be dict, got {type(sudo_result)}"
    assert (
        sudo_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo_result should be MsgSudoResponse, got {sudo_result.get('@type')}"
    assert (
        "results" in sudo_result
    ), f"sudo_result should have results field, got keys: {list(sudo_result.keys())}"


def test_create_external_name_empty_name(chainnet):
    """Test external name creation with empty name."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_empty_name(authority):
    # Try to create external name with empty name - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": ""
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({"authority": gov_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_empty_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error - should fail with empty name
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    # Should have exception for empty name
    assert result.get("exception") is not None, "Expected exception for empty name"
    exception_msg = result["exception"]["msg"]
    assert (
        "name cannot be empty" in exception_msg
    ), f"Expected 'name cannot be empty' in error message: {exception_msg}"


def test_create_external_name_invalid_authority(chainnet):
    """Test external name creation with invalid authority."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_invalid_authority(invalid_authority):
    # Try to create external name with invalid authority - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": invalid_authority,
        "name": "test.com"
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    # Use a random address that's not the authority
    invalid_authority = "dyson1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    kwargs = json.dumps({"invalid_authority": invalid_authority})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_invalid_authority",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error - should fail with invalid authority
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    # Should have exception for invalid authority
    assert (
        result.get("exception") is not None
    ), "Expected exception for invalid authority"
    exception_msg = result["exception"]["msg"]
    assert (
        "invalid authority" in exception_msg
    ), f"Expected 'invalid authority' in error message: {exception_msg}"


def test_create_external_name_valid_no_dots(chainnet):
    """Test external name creation with valid format (no dots - single word)."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_valid_no_dots(authority, name):
    # Create external name with single word format - should succeed
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({"authority": gov_addr, "name": "example"})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_valid_no_dots",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate result
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Check result - should succeed for valid single word format
    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"sudo_result should be dict, got {type(sudo_result)}"

    # Single word external names are valid - should succeed
    assert (
        sudo_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"Single word external name should be valid"


def test_create_external_name_invalid_name_format_starts_with_dot(chainnet):
    """Test external name creation with invalid name format (starts with dot)."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_invalid_name_format(authority, name):
    # Try to create external name with invalid format - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({"authority": gov_addr, "name": ".com"})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_invalid_name_format",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate result
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    # Should have exception for invalid name format
    assert (
        result.get("exception") is not None
    ), "Expected exception for invalid name format"
    exception_msg = result["exception"]["msg"]
    assert (
        "invalid external name format" in exception_msg
    ), f"Expected 'invalid external name format' in error message: {exception_msg}"


def test_create_external_name_name_already_exists(chainnet):
    """Test external name creation when name already exists."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_name_already_exists(authority, name):
    # First, create the external name
    sudo_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    # Try to create it again - should fail
    sudo_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    return {
        "sudo_result1": sudo_result1,
        "sudo_result2": sudo_result2
    }
"""

    kwargs = json.dumps({"authority": gov_addr, "name": "duplicate.com"})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_name_already_exists",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate result - should fail on second creation
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    # Should have exception for duplicate name
    assert result.get("exception") is not None, "Expected exception for duplicate name"
    exception_msg = result["exception"]["msg"]
    assert (
        "name is already registered" in exception_msg
    ), f"Expected 'name is already registered' in error message: {exception_msg}"


def test_create_external_name_valid_formats(chainnet):
    """Test external name creation with valid formats."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_valid_formats(authority, name):
    # Create external name with valid format
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    # Test simple domain
    kwargs = json.dumps({"authority": gov_addr, "name": "example.com"})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_valid_formats",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate success
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Validate sudo result - _sudo returns MsgSudoResponse on success
    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"sudo_result should be dict, got {type(sudo_result)}"
    assert (
        sudo_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo_result should be MsgSudoResponse, got {sudo_result.get('@type')}"
    assert (
        "results" in sudo_result
    ), f"sudo_result should have results field, got keys: {list(sudo_result.keys())}"


def test_create_external_name_valid_subdomain(chainnet):
    """Test external name creation with subdomain format."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_valid_subdomain(authority, name):
    # Create external name with subdomain format
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({"authority": gov_addr, "name": "sub.domain.org"})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_valid_subdomain",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate success
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Validate sudo result
    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"sudo_result should be dict, got {type(sudo_result)}"
    assert (
        sudo_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo_result should be MsgSudoResponse, got {sudo_result.get('@type')}"
    assert (
        "results" in sudo_result
    ), f"sudo_result should have results field, got keys: {list(sudo_result.keys())}"


def test_create_external_name_nil_request(chainnet):
    """Test external name creation with nil request - handled at framework level."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_nil_request():
    # Nil request is handled at framework level - just ensure no crash
    return {"status": "nil_request_handled_by_framework"}
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
        "demo_nil_request",
        "--kwargs",
        "{}",
        "--extra-code",
        extra_code,
    )

    # Parse and validate result
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"
    assert (
        demo_result.get("status") == "nil_request_handled_by_framework"
    ), f"Framework should handle nil request"


def test_create_external_name_reserved_name_allowed(chainnet):
    """Test CreateExternalName can create reserved names (governance bypass)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_name_allowed(authority):
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-governance.dys"
        }
    })
    
    # Step 2: Create external name with reserved name - should succeed (governance bypass)
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": "reserved-governance.dys"
    })
    
    # Step 3: Query the NFT to verify it was created
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "reserved-governance.dys"
    })
    
    return {
        "sudo_result": sudo_result,
        "nft_query": nft_query
    }
"""

    kwargs = json.dumps({"authority": gov_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_reserved_name_allowed",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate result
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Validate sudo result - should succeed
    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"sudo_result should be dict, got {type(sudo_result)}"
    assert (
        sudo_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo_result should be MsgSudoResponse, got {sudo_result.get('@type')}"

    # Verify NFT was created
    nft_query = demo_result["nft_query"]
    assert isinstance(
        nft_query, dict
    ), f"nft_query should be dict, got {type(nft_query)}"
    assert "nft" in nft_query, "Missing nft in query response"
    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["id"] == "reserved-governance.dys", (
        f"Expected NFT id 'reserved-governance.dys', got: {nft['id']}"
    )
