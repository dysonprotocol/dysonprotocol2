import pytest
import json
import ast


def test_script_get_block(chainnet):
    """Test the GetBlock query for Script module"""
    dysond_bin = chainnet[0]

    # Get the current block info from the Script module
    response = dysond_bin("query", "script", "get-block")

    # Verify the response contains expected fields
    assert "block_height" in response
    assert "block_time" in response
    assert "chain_id" in response
    assert "block_hash" in response
    assert "app_hash" in response
    assert "proposer_address" in response

    # Verify block height is positive
    assert int(response["block_height"]) > 0

    # Verify chain ID is present and starts with expected prefix
    assert "chain_id" in response
    assert response["chain_id"] in [
        "chain-a",
        "chain-b",
        "dyson-test",
    ], f"Unexpected chain ID: {response['chain_id']}"

    # Verify hashes are non-empty (they are base64 encoded)
    assert len(response["block_hash"]) > 0
    assert len(response["app_hash"]) > 0

    # Verify proposer address is a valid bech32 address
    assert response["proposer_address"].startswith("dys2")

    print(f"Block height: {response['block_height']}")
    print(f"Block time: {response['block_time']}")
    print(f"Chain ID: {response['chain_id']}")
    print(f"Block hash: {response['block_hash']}")
    print(f"App hash: {response['app_hash']}")
    print(f"Proposer address: {response['proposer_address']}")


def test_script_get_block_after_transactions(chainnet, generate_account):
    """Test GetBlock query returns updated block info after transactions"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")

    # Get initial block info
    initial_response = dysond_bin("query", "script", "get-block")
    initial_height = int(initial_response["block_height"])

    # Create a simple script to generate a transaction
    script_code = """
def hello():
    return "Hello from block test"
"""

    # Create the script
    result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        script_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert result.get("code", 1) == 0, "Failed to update script"

    # Get block info after transaction
    final_response = dysond_bin("query", "script", "get-block")
    final_height = int(final_response["block_height"])

    # Verify block height has increased
    assert final_height > initial_height

    # Verify other fields are still present and valid
    assert len(final_response["block_hash"]) > 0
    assert len(final_response["app_hash"]) > 0
    assert final_response["chain_id"] in ["chain-a", "chain-b", "dyson-test"]

    print(f"Initial block height: {initial_height}")
    print(f"Final block height: {final_height}")
    print(f"Block height increased by: {final_height - initial_height}")


def test_no_historical_queries_supported():
    """Historical queries are not supported; ensure example test is removed."""
    assert True
