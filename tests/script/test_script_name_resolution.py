import pytest
import requests
import time


@pytest.fixture
def script_code():
    """Simple Python script that returns a hello message"""
    return """
def wsgi(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/html')]
    start_response(status, headers)
    return [b'<html><body><h1>Hello from Dyson Protocol!</h1></body></html>']
"""


def test_name_resolution(chainnet, generate_account, faucet, script_code, api_address):
    """Test name resolution in the RunWeb function"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # First, update Alice's script with a simple WSGI app
    update_result = dysond_bin(
        "tx", "script", "update", "--code", script_code, "--from", alice_name
    )
    assert update_result["code"] == 0, "Failed to update script"

    # Register a name using commit-reveal process with unique timestamp
    timestamp = int(time.time() * 1000)  # Use milliseconds for uniqueness
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
    # Log error details if the transaction failed
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

    api_url = f"http://{api_address['host']}:{api_address['port']}"

    # Test script access by address (direct)
    response = requests.get(
        api_url, timeout=10, headers={"Host": f"{alice_address}.localhost"}
    )
    direct_result = response.text
    assert (
        "Hello from Dyson Protocol" in direct_result
    ), "Failed to access script by address"

    # Test script access by name (resolved)
    response = requests.get(api_url, timeout=10, headers={"Host": f"{name}.localhost"})
    name_result = response.text
    assert "Hello from Dyson Protocol" in name_result, "Failed to access script by name"

    # Verify both responses are identical
    assert (
        direct_result == name_result
    ), "Response differs between address and name access"
