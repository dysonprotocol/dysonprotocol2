#!/usr/bin/env python3
import json
import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from tests import utils


def test_exec_authorization_with_function_names(chainnet, generate_account, faucet):
    """
    Test ScriptExecAuthorization with specific function names allowed.
    This tests:
    1. Creating a script with multiple functions
    2. Granting ScriptExecAuthorization for specific functions
    3. Executing allowed functions succeeds
    4. Executing disallowed functions fails
    """
    dysond_bin = chainnet[0]

    # Create accounts
    [alice_name, alice_address] = generate_account("alice")
    [bob_name, bob_address] = generate_account("bob")

    # Fund accounts
    faucet(alice_address, denom="udys", amount="10000")
    faucet(bob_address, denom="udys", amount="10000")

    # Create a script with multiple functions
    script_code = """
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

def get_info():
    return {"version": "1.0", "status": "active"}
"""

    # Alice creates the script
    create_result = dysond_bin(
        "tx", "script", "create-new-script", "--code", script_code, "--from", alice_name
    )

    # Extract script address from events using list comprehensions
    script_events = [
        e
        for e in create_result["events"]
        if e["type"] == "dysonprotocol.script.v1.EventCreateNewScript"
    ]
    address_attrs = [
        a
        for e in script_events
        for a in e["attributes"]
        if a["key"] == "script_address"
    ]

    script_address = json.loads(address_attrs[0]["value"]) if address_attrs else None

    assert script_address, "Script address not found in transaction events"
    print(f"Created script at address: {script_address}")

    # Grant authorization to Bob using the new grant-exec command
    # Set expiration to 1 hour from now
    expiration = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    grant_result = dysond_bin(
        "tx",
        "script",
        "grant-exec",
        bob_address,
        "--script-address",
        script_address,
        "--function-names",
        "add,get_info",
        "--expiration",
        expiration,
        "--from",
        alice_name,
    )

    assert grant_result["code"] == 0, f"Failed to grant authorization: {grant_result}"
    print("Granted ScriptExecAuthorization to Bob")

    # Verify the grant exists
    grants_result = dysond_bin("query", "authz", "grants", alice_address, bob_address)
    assert len(grants_result["grants"]) > 0, "No grants found"

    # Debug: print the grants structure
    print(f"Grants structure: {json.dumps(grants_result, indent=2)}")

    # Find our ScriptExecAuthorization grant using list comprehensions
    script_exec_grants = [
        grant
        for grant in grants_result["grants"]
        if grant.get("authorization", {}).get("type")
        == "/dysonprotocol.script.v1.ScriptExecAuthorization"
    ]

    exec_grant = script_exec_grants[0] if script_exec_grants else None

    assert exec_grant is not None, "ScriptExecAuthorization grant not found"

    # Extract the authorization details from the value field
    auth_value = exec_grant["authorization"]["value"]
    assert auth_value.get("script_address") == script_address
    assert auth_value.get("function_names") == ["add", "get_info"]
    print("Verified ScriptExecAuthorization grant exists with correct parameters")

    # Test 1: Bob executes allowed function 'add' - should succeed
    exec_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": alice_address,  # Alice is the actual executor (via authz)
        "script_address": script_address,
        "function_name": "add",
        "args": json.dumps([10, 20]),
        "kwargs": "{}",
    }

    tx_body = {"body": {"messages": [exec_msg]}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()

        # Bob executes via authz
        exec_result = dysond_bin(
            "tx", "authz", "exec", tx_file.name, "--from", bob_name
        )

    assert (
        exec_result["code"] == 0
    ), f"Failed to execute allowed function 'add': {exec_result}"

    # Extract result from events using list comprehensions
    exec_events = [
        e
        for e in exec_result["events"]
        if e["type"] == "dysonprotocol.script.v1.EventExecScript"
    ]
    response_attrs = [
        a for e in exec_events for a in e["attributes"] if a["key"] == "response"
    ]

    # Get the first result if available
    attr = response_attrs[0] if response_attrs else None
    response_data = json.loads(attr["value"]) if attr else {}
    result_data = json.loads(response_data.get("result", "{}")) if response_data else {}
    add_result = result_data.get("result") if result_data else None

    assert add_result == 30, f"Expected add result 30, got {add_result}"
    print("✓ Bob successfully executed allowed function 'add'")

    # Test 2: Bob executes allowed function 'get_info' - should succeed
    exec_msg["function_name"] = "get_info"
    exec_msg["args"] = "[]"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()

        exec_result = dysond_bin(
            "tx", "authz", "exec", tx_file.name, "--from", bob_name
        )

    assert (
        exec_result["code"] == 0
    ), f"Failed to execute allowed function 'get_info': {exec_result}"
    print("✓ Bob successfully executed allowed function 'get_info'")

    # Test 3: Bob tries to execute disallowed function 'multiply' - should fail
    exec_msg["function_name"] = "multiply"
    exec_msg["args"] = json.dumps([5, 6])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()

        # This should fail with an unauthorized error
        exec_result = dysond_bin(
            "tx",
            "authz",
            "exec",
            tx_file.name,
            "--from",
            bob_name,
        )

    assert (
        exec_result["code"] != 0
    ), "Expected execution to fail for disallowed function"
    assert "not authorized" in exec_result.get(
        "raw_log", ""
    ), "Expected unauthorized error"
    print("✓ Bob correctly failed to execute disallowed function 'multiply'")

    # Test 4: Bob tries to execute without function name (direct script execution) - should succeed
    exec_msg["function_name"] = ""
    exec_msg["args"] = "[]"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()

        exec_result = dysond_bin(
            "tx", "authz", "exec", tx_file.name, "--from", bob_name
        )

    assert (
        exec_result["code"] == 0
    ), f"Expected direct script execution to succeed: {exec_result}"
    print(
        "✓ Bob successfully executed script directly (direct execution is always allowed)"
    )


def test_exec_authorization_empty_function_list(chainnet, generate_account, faucet):
    """
    Test ScriptExecAuthorization with empty function list (only direct script execution allowed).
    """
    dysond_bin = chainnet[0]

    # Create accounts
    [alice_name, alice_address] = generate_account("alice")
    [bob_name, bob_address] = generate_account("bob")

    # Fund accounts
    faucet(alice_address, denom="udys", amount="10000")
    faucet(bob_address, denom="udys", amount="10000")

    # Create a simple script
    script_code = """
# Direct execution
print("Script executed directly")
result = {"executed": True, "mode": "direct"}

def some_function():
    return {"executed": True, "mode": "function"}
"""

    # Alice creates the script
    create_result = dysond_bin(
        "tx", "script", "create-new-script", "--code", script_code, "--from", alice_name
    )

    assert create_result["code"] == 0, f"Failed to create script: {create_result}"

    # Extract script address from events using list comprehensions
    script_events = [
        e
        for e in create_result["events"]
        if e["type"] == "dysonprotocol.script.v1.EventCreateNewScript"
    ]
    address_attrs = [
        a
        for e in script_events
        for a in e["attributes"]
        if a["key"] == "script_address"
    ]

    script_address = json.loads(address_attrs[0]["value"]) if address_attrs else None

    assert script_address, "Script address not found"

    # Grant authorization to Bob with empty function list
    expiration = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    grant_result = dysond_bin(
        "tx",
        "script",
        "grant-exec",
        bob_address,
        "--script-address",
        script_address,
        # No --function-names flag, so empty list
        "--expiration",
        expiration,
        "--from",
        alice_name,
    )

    assert grant_result["code"] == 0, f"Failed to grant authorization: {grant_result}"

    # Test 1: Bob executes script directly (no function) - should succeed
    exec_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": alice_address,
        "script_address": script_address,
        "function_name": "",  # Empty - direct execution
        "args": "[]",
        "kwargs": "{}",
    }

    tx_body = {"body": {"messages": [exec_msg]}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()

        exec_result = dysond_bin(
            "tx", "authz", "exec", tx_file.name, "--from", bob_name
        )

    assert exec_result["code"] == 0, f"Failed to execute script directly: {exec_result}"
    print("✓ Bob successfully executed script directly with empty function list")

    # Test 2: Bob tries to execute a function - should fail
    exec_msg["function_name"] = "some_function"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()

        exec_result = dysond_bin(
            "tx",
            "authz",
            "exec",
            tx_file.name,
            "--from",
            bob_name,
        )

    # With the simplified logic, if function_name is provided, it must be in the list
    # Empty list means no functions are allowed
    assert (
        exec_result["code"] != 0
    ), "Expected execution to fail when calling function with empty allowed list"
    print(
        "✓ Bob correctly failed to execute function when only direct execution is allowed"
    )


def test_exec_authorization_revoke(chainnet, generate_account, faucet):
    """
    Test revoking ScriptExecAuthorization.
    """
    dysond_bin = chainnet[0]

    # Create accounts
    [alice_name, alice_address] = generate_account("alice")
    [bob_name, bob_address] = generate_account("bob")

    # Fund accounts
    faucet(alice_address, denom="udys", amount="10000")
    faucet(bob_address, denom="udys", amount="10000")

    # Create a simple script
    script_code = "def test(): return 'test result'"

    create_result = dysond_bin(
        "tx", "script", "create-new-script", "--code", script_code, "--from", alice_name
    )

    # Extract script address from events using list comprehensions
    script_events = [
        e
        for e in create_result["events"]
        if e["type"] == "dysonprotocol.script.v1.EventCreateNewScript"
    ]
    address_attrs = [
        a
        for e in script_events
        for a in e["attributes"]
        if a["key"] == "script_address"
    ]

    script_address = json.loads(address_attrs[0]["value"]) if address_attrs else None

    assert script_address, "Script address not found"

    # Grant ScriptExecAuthorization
    expiration = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    grant_result = dysond_bin(
        "tx",
        "script",
        "grant-exec",
        bob_address,
        "--script-address",
        script_address,
        "--function-names",
        "test",
        "--expiration",
        expiration,
        "--from",
        alice_name,
    )

    assert grant_result["code"] == 0, "Failed to grant authorization"

    # Verify grant exists
    grants_result = dysond_bin("query", "authz", "grants", alice_address, bob_address)
    assert len(grants_result["grants"]) > 0, "No grants found"

    # Revoke the authorization
    revoke_result = dysond_bin(
        "tx",
        "authz",
        "revoke",
        bob_address,
        "/dysonprotocol.script.v1.MsgExec",
        "--from",
        alice_name,
    )

    assert (
        revoke_result["code"] == 0
    ), f"Failed to revoke authorization: {revoke_result}"
    print("✓ Successfully revoked ScriptExecAuthorization")

    # Verify grant no longer exists
    grants_result = dysond_bin("query", "authz", "grants", alice_address, bob_address)

    # Check that no ScriptExecAuthorization exists using list comprehensions
    script_exec_grants = [
        grant
        for grant in grants_result.get("grants", [])
        if grant["authorization"]["@type"]
        == "/dysonprotocol.script.v1.ScriptExecAuthorization"
    ]

    exec_grant_found = len(script_exec_grants) > 0

    assert not exec_grant_found, "ScriptExecAuthorization should have been revoked"
    print("✓ Verified ScriptExecAuthorization was revoked")

    # Try to execute - should fail
    exec_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": alice_address,
        "script_address": script_address,
        "function_name": "test",
        "args": "[]",
        "kwargs": "{}",
    }

    tx_body = {"body": {"messages": [exec_msg]}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()

        exec_result = dysond_bin(
            "tx", "authz", "exec", tx_file.name, "--from", bob_name
        )

    assert exec_result["code"] != 0, "Expected execution to fail after revoke"
    print("✓ Bob correctly failed to execute after authorization was revoked")


def test_exec_authorization_wrong_script_address(chainnet, generate_account, faucet):
    """
    Test that ScriptExecAuthorization correctly rejects execution on wrong script address.
    """
    dysond_bin = chainnet[0]

    # Create accounts
    [alice_name, alice_address] = generate_account("alice")
    [bob_name, bob_address] = generate_account("bob")

    # Fund accounts
    faucet(alice_address, denom="udys", amount="10000")
    faucet(bob_address, denom="udys", amount="10000")

    # Create two different scripts
    script1_code = "def func1(): return 'script1'"
    script2_code = "def func1(): return 'script2'"

    # Create first script
    create_result1 = dysond_bin(
        "tx",
        "script",
        "create-new-script",
        "--code",
        script1_code,
        "--from",
        alice_name,
    )

    # Extract script addresses using list comprehensions
    script1_events = [
        e
        for e in create_result1["events"]
        if e["type"] == "dysonprotocol.script.v1.EventCreateNewScript"
    ]
    script1_attrs = [
        a
        for e in script1_events
        for a in e["attributes"]
        if a["key"] == "script_address"
    ]
    script1_address = json.loads(script1_attrs[0]["value"]) if script1_attrs else None

    # Create second script
    create_result2 = dysond_bin(
        "tx",
        "script",
        "create-new-script",
        "--code",
        script2_code,
        "--from",
        alice_name,
    )

    script2_events = [
        e
        for e in create_result2["events"]
        if e["type"] == "dysonprotocol.script.v1.EventCreateNewScript"
    ]
    script2_attrs = [
        a
        for e in script2_events
        for a in e["attributes"]
        if a["key"] == "script_address"
    ]
    script2_address = json.loads(script2_attrs[0]["value"]) if script2_attrs else None

    assert script1_address and script2_address, "Failed to create scripts"
    assert script1_address != script2_address, "Scripts should have different addresses"

    # Grant ScriptExecAuthorization for script1 only
    expiration = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    grant_result = dysond_bin(
        "tx",
        "script",
        "grant-exec",
        bob_address,
        "--script-address",
        script1_address,
        "--function-names",
        "func1",
        "--expiration",
        expiration,
        "--from",
        alice_name,
    )

    assert grant_result["code"] == 0, "Failed to grant authorization"

    # Try to execute script2 using authorization for script1 - should fail
    exec_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": alice_address,
        "script_address": script2_address,  # Wrong script!
        "function_name": "func1",
        "args": "[]",
        "kwargs": "{}",
    }

    tx_body = {"body": {"messages": [exec_msg]}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()

        exec_result = dysond_bin(
            "tx", "authz", "exec", tx_file.name, "--from", bob_name
        )

    assert (
        exec_result["code"] != 0
    ), "Expected execution to fail for wrong script address"
    assert "script address mismatch" in exec_result.get(
        "raw_log", ""
    ), "Expected script address mismatch error"
    print(
        "✓ ScriptExecAuthorization correctly rejected execution on wrong script address"
    )
