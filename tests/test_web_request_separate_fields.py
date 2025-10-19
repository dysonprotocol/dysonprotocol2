import pytest
import time


@pytest.fixture
def script_code():
    """Simple Python script that returns a hello message"""
    return """
def wsgi(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/html')]
    start_response(status, headers)
    return [b'<html><body><h1>Hello from separate fields test!</h1></body></html>']
"""


def test_web_request_with_script_address_only(
    chainnet, generate_account, faucet, script_code
):
    """Test WebRequest with only script_address field"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Update Alice's script
    update_result = dysond_bin(
        "tx", "script", "update", "--code", script_code, "--from", alice_name
    )
    assert update_result["code"] == 0, "Failed to update script"

    # Test Web query with only script_address
    web_request = {
        "script_address": alice_address,
        "httprequest": "GET / HTTP/1.1\r\nHost: test.example.com\r\n\r\n",
    }

    web_result = dysond_bin(
        "query",
        "script",
        "web",
        "--script-address",
        alice_address,
        "--httprequest",
        web_request["httprequest"],
    )
    assert "httpresponse" in web_result, "Web query should return httpresponse"
    assert web_result["httpresponse"], "httpresponse should not be empty"


def test_web_request_with_script_name_only(
    chainnet, generate_account, faucet, script_code
):
    """Test WebRequest with only script_name field"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Update Alice's script
    update_result = dysond_bin(
        "tx", "script", "update", "--code", script_code, "--from", alice_name
    )
    assert update_result["code"] == 0, "Failed to update script"

    # Register a name using commit-reveal process
    timestamp = int(time.time() * 1000)
    name = f"alice-test-{timestamp}.dys"
    salt = "test123salt"

    # Compute the hash for commitment
    hash_result = dysond_bin(
        "query",
        "nameservice",
        "compute-hash",
        "--name",
        name,
        "--salt",
        salt,
        "--committer",
        alice_address,
    )
    hex_hash = hash_result["hex_hash"]
    assert hex_hash, "Failed to compute hash"

    # Commit to the name registration
    commit_result = dysond_bin(
        "tx",
        "nameservice",
        "commit",
        "--commitment",
        hex_hash,
        "--valuation",
        "100udys",
        "--from",
        alice_name,
    )
    assert commit_result["code"] == 0, "Failed to commit name registration"

    # Reveal the name to complete registration
    reveal_result = dysond_bin(
        "tx",
        "nameservice",
        "reveal",
        "--name",
        name,
        "--salt",
        salt,
        "--from",
        alice_name,
    )
    assert (
        reveal_result["code"] == 0
    ), f"Failed to reveal name registration: {reveal_result.get('raw_log', 'No raw log available')}"

    # Set the destination to Alice's address
    set_dest_result = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert set_dest_result["code"] == 0, "Failed to set destination"

    # Test Web query with only script_name
    web_request = {
        "script_name": name,
        "httprequest": "GET / HTTP/1.1\r\nHost: test.example.com\r\n\r\n",
    }

    web_result = dysond_bin(
        "query",
        "script",
        "web",
        "--script-name",
        name,
        "--httprequest",
        web_request["httprequest"],
    )
    assert "httpresponse" in web_result, "Web query should return httpresponse"
    assert web_result["httpresponse"], "httpresponse should not be empty"


def test_web_request_with_both_fields_matching(
    chainnet, generate_account, faucet, script_code
):
    """Test WebRequest with both script_address and script_name that match"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Update Alice's script
    update_result = dysond_bin(
        "tx", "script", "update", "--code", script_code, "--from", alice_name
    )
    assert update_result["code"] == 0, "Failed to update script"

    # Register a name using commit-reveal process
    timestamp = int(time.time() * 1000)
    name = f"alice-test-{timestamp}.dys"
    salt = "test123salt"

    # Compute the hash for commitment
    hash_result = dysond_bin(
        "query",
        "nameservice",
        "compute-hash",
        "--name",
        name,
        "--salt",
        salt,
        "--committer",
        alice_address,
    )
    hex_hash = hash_result["hex_hash"]
    assert hex_hash, "Failed to compute hash"

    # Commit to the name registration
    commit_result = dysond_bin(
        "tx",
        "nameservice",
        "commit",
        "--commitment",
        hex_hash,
        "--valuation",
        "100udys",
        "--from",
        alice_name,
    )
    assert commit_result["code"] == 0, "Failed to commit name registration"

    # Reveal the name to complete registration
    reveal_result = dysond_bin(
        "tx",
        "nameservice",
        "reveal",
        "--name",
        name,
        "--salt",
        salt,
        "--from",
        alice_name,
    )
    assert (
        reveal_result["code"] == 0
    ), f"Failed to reveal name registration: {reveal_result.get('raw_log', 'No raw log available')}"

    # Set the destination to Alice's address
    set_dest_result = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert set_dest_result["code"] == 0, "Failed to set destination"

    # Test Web query with both fields (should succeed since they match)
    web_result = dysond_bin(
        "query",
        "script",
        "web",
        "--script-address",
        alice_address,
        "--script-name",
        name,
        "--httprequest",
        "GET / HTTP/1.1\r\nHost: test.example.com\r\n\r\n",
    )
    assert "httpresponse" in web_result, "Web query should return httpresponse"
    assert web_result["httpresponse"], "httpresponse should not be empty"


def test_web_request_with_neither_field_fails(chainnet):
    """Test WebRequest with neither field should fail"""
    dysond_bin = chainnet[0]

    # Test Web query with neither field (should fail)
    web_result = dysond_bin(
        "query",
        "script",
        "web",
        "--httprequest",
        "GET / HTTP/1.1\r\nHost: test.example.com\r\n\r\n",
    )
    # When command fails, result is a string containing the error message
    assert isinstance(
        web_result, str
    ), "Web query should fail when neither field is provided"
    assert (
        "either script_address or script_name must be provided" in web_result
    ), "Should indicate missing fields"
