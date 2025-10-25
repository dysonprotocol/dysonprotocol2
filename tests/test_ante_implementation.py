#!/usr/bin/env python3
import pytest
import json


def test_new_account_with_zero_account_number(chainnet, generate_account):
    """Test that newly generated accounts can make transactions using account number 0.

    This tests the ante handler implementation that allows new accounts to:
    1. Be created automatically when they don't exist
    2. Use account number 0 for signature verification
    3. Have transactions processed successfully
    """
    dysond_bin = chainnet[0]

    # First, create a script owner account to deploy the hello world script
    # faucet amount must be 0 to test properly, if faucet amount is not 0, the account will be funded and
    # the account number will not be 0
    [script_owner_name, script_owner_address] = generate_account(
        "script_owner", faucet_amount=0
    )

    # Create a simple hello world script
    hello_world_code = """
def hello():
    return {"message": "Hello World!", "success": True}

def wsgi(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/html')]
    start_response(status, headers)
    return [b'<html><body><h1>Hello World from Ante Test!</h1></body></html>']
"""

    # Deploy the script
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        hello_world_code,
        "--from",
        script_owner_name,
        "--fees",
        "0udys",
        "--gas",
        "1500000",
        "--offline",
        "--account-number",
        "0",
        "--sequence",
        "0",
        "--chain-id",
        "chain-a",
        "-y",
    )
    assert update_result.get("code", 1) == 0, "Failed to update script"

    # wait-tx
    wait_result = dysond_bin("query", "wait-tx", update_result.get("txhash"))
    assert (
        wait_result.get("code", 1) == 0
    ), f"Transaction execution failed. Wait result: {wait_result.get('raw_log', 'No raw log available')}"

    # Verify script was created
    script_info = dysond_bin(
        "query", "script", "script-info", "--address", script_owner_address
    )
    assert (
        script_info.get("script", {}).get("address") == script_owner_address
    ), "Script address doesn't match"

    # Now test the ante handler with a new unfunded account using the manual approach
    [test_account_name, test_account_address] = generate_account(
        "test_ante", faucet_amount=0
    )

    # Verify the test account doesn't exist on-chain yet
    account_query = dysond_bin(
        "query", "auth", "account", test_account_address, raw=True
    )
    assert "account" in account_query and "not found" in account_query

    # Execute transaction using offline mode with account-number 0 and sequence 0
    # This should trigger the ante handler to create the account automatically
    tx_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        script_owner_address,
        "--function-name",
        "hello",
        "--from",
        test_account_name,
        "--gas",
        "1500000",
        "--offline",
        "--account-number",
        "0",
        "--sequence",
        "0",
        "--chain-id",
        "chain-a",
        "-y",
    )

    # Verify transaction succeeded
    assert (
        tx_result.get("code", 1) == 0
    ), f"Transaction failed with code {tx_result.get('code')}: {tx_result.get('raw_log', 'No raw log available')}"

    txhash = tx_result.get("txhash")
    assert txhash is not None, f"No txhash found in transaction result: {tx_result}"

    # Wait for transaction to be processed
    wait_result = dysond_bin("query", "wait-tx", txhash)
    assert (
        wait_result.get("code", 1) == 0
    ), f"Transaction execution failed. Wait result: {wait_result.get('raw_log', 'No raw log available')}"

    # Verify the account was created on-chain
    account_data = dysond_bin("query", "auth", "account", test_account_address)

    # Account should now exist and have the expected properties
    assert account_data["account"]["value"]["address"] == test_account_address
    assert (
        int(account_data["account"]["value"]["sequence"]) == 1
    )  # Should be 1 after the transaction

    # Account number should be assigned by the chain (not 0)
    account_number = int(account_data["account"]["value"]["account_number"])
    assert account_number > 0

    # Verify script execution was successful by checking the wait result
    exec_events = [
        e
        for e in wait_result.get("events", [])
        if e.get("type") == "dysonprotocol.script.v1.EventExecScript"
    ]
    assert exec_events, "Script execution event not found"

    print(
        f"✅ SUCCESS: New account {test_account_address} created and transaction executed!"
    )


def test_multiple_new_accounts_sequential_offline(chainnet, generate_account):
    """Test that multiple new accounts can be created sequentially using the offline approach."""
    dysond_bin = chainnet[0]

    # Create script owner and deploy script first
    [script_owner_name, script_owner_address] = generate_account(
        "script_owner_multi", faucet_amount=1000
    )

    simple_code = """
def ping():
    return {"status": "pong"}
"""

    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        simple_code,
        "--from",
        script_owner_name,
    )
    assert update_result.get("code", 1) == 0, "Failed to update script"

    accounts = []
    for i in range(2):  # Test with 2 accounts to avoid too much overhead
        # Generate new accounts without funding
        [account_name, account_address] = generate_account(
            f"multi_test_{i}", faucet_amount=0
        )
        accounts.append((account_name, account_address))

        # Use the offline approach with account-number 0 and sequence 0
        tx_result = dysond_bin(
            "tx",
            "script",
            "exec",
            "--script-address",
            script_owner_address,
            "--function-name",
            "ping",
            "--from",
            account_name,
            "--gas",
            "1500000",
            "--fees",
            "0udys",
            "--offline",
            "--account-number",
            "0",
            "--sequence",
            "0",
            "--chain-id",
            "chain-a",
            "-y",
        )

        # Verify transaction succeeded
        assert (
            tx_result.get("code", 1) == 0
        ), f"Transaction failed for account {i}. Result: {tx_result.get('raw_log', 'No raw log available')}"

        # Get the transaction hash and wait for it to be confirmed
        txhash = tx_result.get("txhash")
        assert txhash, f"No txhash in transaction result: {tx_result}"

        # Wait for transaction confirmation
        wait_result = dysond_bin("query", "wait-tx", txhash)
        assert (
            wait_result.get("code", 1) == 0
        ), f"Transaction execution failed. Wait result: {wait_result.get('raw_log', 'No raw log available')}"

        # Verify account exists
        account_data = dysond_bin("query", "auth", "account", account_address)

        # Handle the case where account_data might be a string (error) instead of dict
        assert isinstance(
            account_data, dict
        ), f"Expected account data to be a dict, got: {account_data}"
        assert (
            "account" in account_data
        ), f"No 'account' field in response: {json.dumps(account_data, indent=2)}"
        assert account_data["account"]["value"]["address"] == account_address
        assert int(account_data["account"]["value"]["sequence"]) == 1

    # Verify all accounts have different account numbers
    account_numbers = []
    for _, address in accounts:
        account_data = dysond_bin("query", "auth", "account", address)
        # Handle the case where account_data might be a string (error) instead of dict
        assert isinstance(
            account_data, dict
        ), f"Expected account data to be a dict for {address}, got: {account_data}"
        assert (
            "account" in account_data
        ), f"No 'account' field in response for {address}: {json.dumps(account_data, indent=2)}"
        account_number = int(account_data["account"]["value"]["account_number"])
        assert account_number not in account_numbers
        account_numbers.append(account_number)

    print(
        f"✅ SUCCESS: Created {len(accounts)} accounts with different account numbers: {account_numbers}"
    )


def test_existing_account_still_works(chainnet, generate_account, faucet):
    """Test that existing funded accounts still work normally."""
    dysond_bin = chainnet[0]

    # Create script owner and deploy script first
    [script_owner_name, script_owner_address] = generate_account(
        "script_owner_existing", faucet_amount=1000
    )

    test_code = """
def check_func():
    return {"test": "passed"}
"""

    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        test_code,
        "--from",
        script_owner_name,
        "--gas",
        "auto",
    )
    assert update_result.get("code", 1) == 0, (
        f"Failed to update script. Code: {update_result.get('code')}, "
        f"raw_log: {update_result.get('raw_log', '')}.\nFull: {json.dumps(update_result, indent=2)}"
    )

    # Generate account with funding (creates the account on-chain)
    [account_name, account_address] = generate_account(
        "existing_test", faucet_amount=1000
    )

    # Verify account exists and has funds
    account_data = dysond_bin("query", "auth", "account", account_address)
    assert account_data["account"]["value"]["address"] == account_address

    balance_data = dysond_bin("query", "bank", "balances", account_address)
    assert len(balance_data["balances"]) > 0
    assert int(balance_data["balances"][0]["amount"]) >= 1000

    # Execute transaction with existing funded account (should work normally with test fixtures)
    tx_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        script_owner_address,
        "--function-name",
        "check_func",
        "--from",
        account_name,
        "--fees",
        "0udys",
    )

    assert (
        tx_result["code"] == 0
    ), f"Transaction failed with code {tx_result['code']}, raw_log: {tx_result.get('raw_log', 'No raw log available')}"
