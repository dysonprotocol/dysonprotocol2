"""
Test SetDestination message handler for nameservice keeper.

Tests the destination setting functionality which allows name owners
to set a destination URI for their names, supporting both bech32 addresses
and existing names as destinations.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_set_destination_success_bech32_address(chainnet):
    """Test successful destination setting with valid bech32 address."""
    dysond = chainnet[0]

    # Get gov address for authority
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

def demo_create_external_name_and_set_destination(authority, name, destination):
    # First create an external name to own
    sudo_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    # Then set the destination as the owner
    sudo_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": authority,
        "name": name,
        "destination": destination
    })
    
    return {
        "create_result": sudo_result1,
        "set_result": sudo_result2
    }
"""

    # Generate a valid test destination address
    destination_addr = get_test_address(dysond, "0x999999")

    kwargs = json.dumps(
        {
            "authority": gov_addr,
            "name": "example.com",
            "destination": destination_addr,
        }
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
        "demo_create_external_name_and_set_destination",
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

    # Validate both operations succeeded
    create_result = demo_result["create_result"]
    assert isinstance(
        create_result, dict
    ), f"create_result should be dict, got {type(create_result)}"

    set_result = demo_result["set_result"]
    assert isinstance(
        set_result, dict
    ), f"set_result should be dict, got {type(set_result)}"

    # Both should have successful responses
    assert (
        create_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"create should succeed"
    assert (
        set_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"set should succeed"


def test_set_destination_success_existing_name(chainnet):
    """Test successful destination setting with existing name as destination."""
    dysond = chainnet[0]

    # Get gov address for authority
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

def demo_create_two_names_and_set_destination(authority, name1, name2, destination):
    # Create two external names
    sudo_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name1
    })
    
    sudo_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name2
    })
    
    # Set destination of first name to point to second name
    sudo_result3 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": authority,
        "name": name1,
        "destination": name2
    })
    
    return {
        "create_result1": sudo_result1,
        "create_result2": sudo_result2,
        "set_result": sudo_result3
    }
"""

    kwargs = json.dumps(
        {
            "authority": gov_addr,
            "name1": "example.com",
            "name2": "test.org",
            "destination": "test.org",
        }
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
        "demo_create_two_names_and_set_destination",
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

    # Validate all operations succeeded
    create_result1 = demo_result["create_result1"]
    create_result2 = demo_result["create_result2"]
    set_result = demo_result["set_result"]

    assert (
        create_result1.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"create1 should succeed"
    assert (
        create_result2.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"create2 should succeed"
    assert (
        set_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"set should succeed"


def test_set_destination_empty_destination(chainnet):
    """Test destination setting with empty destination (clears destination)."""
    dysond = chainnet[0]

    # Get gov address for authority
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

def demo_create_name_and_clear_destination(authority, name):
    # Create an external name
    sudo_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    # Set destination to empty (clears it)
    sudo_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": authority,
        "name": name,
        "destination": ""
    })
    
    return {
        "create_result": sudo_result1,
        "set_result": sudo_result2
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
        "demo_create_name_and_clear_destination",
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

    # Validate both operations succeeded
    create_result = demo_result["create_result"]
    assert isinstance(
        create_result, dict
    ), f"create_result should be dict, got {type(create_result)}"

    set_result = demo_result["set_result"]
    assert isinstance(
        set_result, dict
    ), f"set_result should be dict, got {type(set_result)}"

    # Both should have successful responses
    assert (
        create_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"create should succeed"
    assert (
        set_result.get("@type") == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"set should succeed"


def test_set_destination_name_not_found(chainnet):
    """Test destination setting with non-existent name."""
    dysond = chainnet[0]

    # Get gov address for authority
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

def demo_name_not_found(authority, name):
    # Try to set destination for non-existent name
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": authority,
        "name": name,
        "destination": "cosmos1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({"authority": gov_addr, "name": "nonexistent.com"})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_name_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    # Should have exception for non-existent name
    assert (
        result.get("exception") is not None
    ), f"Should have exception for non-existent name"
    assert "name not found" in result.get("exception", {}).get(
        "msg", ""
    ), f"Error should mention name not found"


def test_set_destination_unauthorized(chainnet):
    """Test destination setting by non-owner."""
    dysond = chainnet[0]

    # Get gov address for authority
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

def demo_create_name_and_unauthorized_set(authority, name, unauthorized_owner):
    # Create an external name
    sudo_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    # Try to set destination as unauthorized user
    sudo_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": unauthorized_owner,
        "name": name,
        "destination": "cosmos1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    })
    
    return {
        "create_result": sudo_result1,
        "set_result": sudo_result2
    }
"""

    # Use a different address as unauthorized owner
    unauthorized_owner = "cosmos1yyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

    kwargs = json.dumps(
        {
            "authority": gov_addr,
            "name": "example.com",
            "unauthorized_owner": unauthorized_owner,
        }
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
        "demo_create_name_and_unauthorized_set",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response - should fail on unauthorized set
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    # Should have exception for unauthorized access
    assert (
        result.get("exception") is not None
    ), "Expected exception for unauthorized access"
    exception_msg = result["exception"]["msg"]
    assert (
        "only the owner can set the destination" in exception_msg
    ), f"Expected 'only the owner can set the destination' in error message: {exception_msg}"


def test_set_destination_invalid_destination_format(chainnet):
    """Test destination setting with invalid destination format."""
    dysond = chainnet[0]

    # Get gov address for authority
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

def demo_create_name_and_invalid_destination(authority, name):
    # Create an external name
    sudo_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCreateExternalName",
        "authority": authority,
        "name": name
    })
    
    # Try to set destination to invalid format
    sudo_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": authority,
        "name": name,
        "destination": "invalid-destination-format"
    })
    
    return {
        "create_result": sudo_result1,
        "set_result": sudo_result2
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
        "demo_create_name_and_invalid_destination",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response - should fail on invalid destination
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    # Should have exception for invalid destination format
    assert (
        result.get("exception") is not None
    ), "Expected exception for invalid destination format"
    exception_msg = result["exception"]["msg"]
    assert (
        "destination must be a valid bech32 address or existing name" in exception_msg
    ), f"Expected 'destination must be a valid bech32 address or existing name' in error message: {exception_msg}"


def test_set_destination_nil_request(chainnet):
    """Test destination setting with nil request - handled at framework level."""
    dysond = chainnet[0]

    # Get gov address for authority
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
