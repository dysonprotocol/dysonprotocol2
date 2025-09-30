import pytest
import json
import time
import requests
from datetime import datetime, timedelta
import subprocess
from utils import poll_until_condition
from pathlib import Path


# REQUIRMENTS:
# - never use hardcoded times. Always use the blockchain time with "datetime.now()"
# - never use time.sleep() use polling to check the condition
# - use a short timedelta for crontasks: 3 seconds is plenty


def test_simple_wsgi_example(chainnet, generate_account, faucet, api_address):
    """Test the simple WSGI example that responds with 'hi world' or 'hi {name}'."""
    dysond = chainnet[0]

    # Create and fund Alice account
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Step 1: Read the simple WSGI example script
    script_path = Path(__file__).parent.parent / "examples" / "simple_wsgi_example.py"
    with open(script_path, "r") as f:
        script_content = f.read()

    # Step 2: Update the script using the dysond command directly
    update_result = dysond(
        "tx", "script", "update", "--from", alice_name, "--code", script_content
    )

    print(
        f"Simple WSGI example script update transaction hash: {update_result['txhash']}"
    )

    # Step 3: Set up the test URL
    # Hard-code the URL for simplicity and reliability

    script_url = f"{alice_address}.localhost"
    api_url = f"http://{api_address['host']}:{api_address['port']}"
    print(f"Using script URL: {script_url}")

    # Wait for the WSGI endpoint to become ready
    print(f"Polling {script_url} until ready...")

    # Define polling check function
    attempts = 0

    def check_url_ready():
        nonlocal attempts
        attempts += 1

        response = requests.get(api_url, timeout=1, headers={"Host": script_url})
        ready = response.status_code == 200

        (
            print(f"Endpoint ready after {attempts} attempts")
            if ready
            else print(
                f"Response status: {response.status_code}, text: {response.text[:100]}"
            )
        )
        return ready

    # Poll until the endpoint is ready
    poll_until_condition(
        check_url_ready,
        timeout=10,
        error_message=f"Endpoint {script_url} not ready after 10 seconds",
    )

    # Test default response (hi world)
    response = requests.get(api_url, timeout=10, headers={"Host": script_url})
    print(f"Response status: {response.status_code}")
    assert (
        response.status_code == 200
    ), f"WSGI request failed with status code {response.status_code}"
    assert "hi world" in response.text, "Default greeting not found in WSGI response"
    print(f"Default response: {response.text[:100]}...")

    # Test with name parameter
    test_names = ["Alice", "Bob", "Charlie"]
    for name in test_names:
        response = requests.get(
            api_url, timeout=1, headers={"Host": script_url}, params={"name": name}
        )
        assert (
            response.status_code == 200
        ), f"WSGI request with name={name} failed with status code {response.status_code}"
        assert (
            f"hi {name}" in response.text
        ), f"Greeting with name '{name}' not found in WSGI response"
        print(f"Response with name={name}: {response.text[:100]}...")

    # Test with POST request
    post_data = {"name": "PostUser"}
    post_response = requests.post(
        api_url, timeout=1, headers={"Host": script_url}, data=post_data
    )
    assert post_response.status_code == 200, "WSGI POST request failed"
    print(f"POST response: {post_response.text[:100]}...")
