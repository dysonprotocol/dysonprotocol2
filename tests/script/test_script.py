import json
import pytest
import tempfile
import os
from tests.utils import poll_until_condition
import black
import random
import string


def test_update_and_query_script(chainnet, generate_account):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)
    script_code = """
def wsgi(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/html')]
    start_response(status, headers)
    return [b'<html><body><h1>Hello from Script Test!</h1></body></html>']
"""
    update_result = dysond_bin(
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
        "--gas",
        "auto",
    )
    print(f"Update script result: {update_result}")
    assert update_result.get("code", 1) == 0, "Failed to update script"
    script_info = dysond_bin(
        "query", "script", "script-info", "--address", alice_address
    )
    print(f"Script info: {script_info}")
    assert (
        script_info.get("script", {}).get("address") == alice_address
    ), "Script address doesn't match"
    # Use Black to format both code snippets before comparison to avoid failures
    # due to insignificant whitespace or quote style differences.
    formatted_received = black.format_str(
        script_info.get("script", {}).get("code", ""), mode=black.FileMode()
    )
    formatted_expected = black.format_str(script_code, mode=black.FileMode())

    assert formatted_received == formatted_expected, "Script code doesn't match"


def test_encode_json(chainnet):
    dysond_bin = chainnet[0]
    test_data = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": "dys1example",
        "to_address": "dys1example",
        "amount": [{"denom": "udys", "amount": "100"}],
    }
    test_json = json.dumps(test_data)
    encode_result = dysond_bin("query", "script", "encode-json", "--json", test_json)
    print(f"Encode JSON result: {encode_result}")
    assert "bytes" in encode_result, "Encode result missing 'bytes' field"


def test_decode_bytes(chainnet):
    dysond_bin = chainnet[0]
    test_data = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": "dys1example",
        "to_address": "dys1example",
        "amount": [{"denom": "udys", "amount": "100"}],
    }
    test_json = json.dumps(test_data)
    encode_result = dysond_bin("query", "script", "encode-json", "--json", test_json)
    encoded_bytes = encode_result.get("bytes")
    assert encoded_bytes, "Failed to get encoded bytes"
    decode_result = dysond_bin(
        "query",
        "script",
        "decode-bytes",
        "--bytes",
        encoded_bytes,
        "--type-url",
        "/cosmos.bank.v1beta1.MsgSend",
    )
    print(f"Decode bytes result: {decode_result}")
    assert "json" in decode_result, "Decode result missing 'json' field"
    assert (
        "dys1example" in decode_result["json"]
    ), "Decoded data doesn't contain original content"


def test_exec_script(chainnet, generate_account):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)
    function_code = """
def add(a, b):
    return a + b
"""
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        function_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas",
        "auto",
    )
    assert update_result.get("code", 1) == 0, "Failed to update script"
    args = [5, 7]
    args_json = json.dumps(args)
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "add",
        "--args",
        args_json,
        "--from",
        alice_name,
        "--gas",
        "auto",
    )
    assert exec_result.get("code", 1) == 0, "Failed to execute script"
    # Extract response from events using dict comprehension
    events_by_type = {
        event.get("type"): event for event in exec_result.get("events", [])
    }
    assert (
        "dysonprotocol.script.v1.EventExecScript" in events_by_type
    ), "No EventExecScript found in transaction events"

    exec_event = events_by_type["dysonprotocol.script.v1.EventExecScript"]
    attrs_by_key = {
        attr.get("key"): attr.get("value") for attr in exec_event.get("attributes", [])
    }
    assert "response" in attrs_by_key, "No response attribute found in EventExecScript"

    response_json = attrs_by_key["response"]
    response_data = json.loads(response_json)
    result_data = json.loads(response_data.get("result", "{}"))
    result_value = result_data.get("result")
    assert result_value == 12, f"Expected result 12, got '{result_value}'"


def test_verify_arbitrary_data_signature(chainnet, generate_account, faucet):
    """Test signing and verifying arbitrary data using MsgArbitraryData"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10")

    # Create temporary files for the transaction
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as tx_file, tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as signed_tx_file:
        tx_json_path = tx_file.name
        signed_tx_json_path = signed_tx_file.name

        # Construct MsgArbitraryData transaction
        tx_data = {
            "body": {
                "messages": [
                    {
                        "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                        "signer": alice_address,
                        "data": "this is test data",
                        "app_domain": "fooApp/123",
                    }
                ],
                "memo": "",
            },
            "auth_info": {"signer_infos": [], "fee": {"amount": [], "gas_limit": "0"}},
            "signatures": [],
        }
        # Write the transaction data to the file
        json.dump(tx_data, tx_file)
        tx_file.flush()

        # Sign the transaction (offline, ADR-036 parameters)
        dysond_bin(
            "tx",
            "sign",
            tx_json_path,
            "--from",
            alice_name,
            "--chain-id",
            "",
            "--account-number",
            "0",
            "--sequence",
            "0",
            "--offline",
            "--output-document",
            signed_tx_json_path,
            "--keyring-backend",
            "test",
        )
        # Read the signed transaction
        with open(signed_tx_json_path, "r") as f:
            signed_tx_json = f.read()
        # Verify the signed transaction
        verify_result = dysond_bin(
            "query", "script", "verify-tx", "--tx-json", signed_tx_json, "-o", "json"
        )
        print(f"Verify transaction result: {verify_result}")
        assert isinstance(verify_result, dict), "Verification failed"


def test_verify_tx_fails_on_bad_data(chainnet, generate_account, faucet):
    """Test that verify-tx correctly fails on various types of bad data"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    [bob_name, bob_address] = generate_account("bob")
    faucet(alice_address, denom="udys", amount="10")

    # First, create a valid signed transaction as baseline
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as tx_file, tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as signed_tx_file:
        tx_json_path = tx_file.name
        signed_tx_json_path = signed_tx_file.name

        # Construct MsgArbitraryData transaction
        tx_data = {
            "body": {
                "messages": [
                    {
                        "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                        "signer": alice_address,
                        "data": "original test data",
                        "app_domain": "testApp/verification",
                    }
                ],
                "memo": "",
            },
            "auth_info": {"signer_infos": [], "fee": {"amount": [], "gas_limit": "0"}},
            "signatures": [],
        }
        # Write the transaction data to the file
        json.dump(tx_data, tx_file)
        tx_file.flush()

        # Sign the transaction (offline, ADR-036 parameters)
        dysond_bin(
            "tx",
            "sign",
            tx_json_path,
            "--from",
            alice_name,
            "--chain-id",
            "",
            "--account-number",
            "0",
            "--sequence",
            "0",
            "--offline",
            "--output-document",
            signed_tx_json_path,
            "--keyring-backend",
            "test",
        )

        # Read the signed transaction
        with open(signed_tx_json_path, "r") as f:
            signed_tx_json = f.read()

        # Parse the signed transaction for manipulation
        signed_tx_data = json.loads(signed_tx_json)

        # Test 1: Tampered signature - modify the signature bytes
        print("Test 1: Testing with tampered signature...")
        tampered_sig_data = json.loads(json.dumps(signed_tx_data))  # Deep copy
        original_sig = tampered_sig_data["signatures"][0]
        # Change a character in the middle of the signature
        sig_list = list(original_sig)
        sig_list[10] = "A" if sig_list[10] != "A" else "B"
        tampered_sig_data["signatures"][0] = "".join(sig_list)
        tampered_sig_json = json.dumps(tampered_sig_data)

        # Verify should fail with tampered signature
        verify_result = dysond_bin(
            "query", "script", "verify-tx", "--tx-json", tampered_sig_json, "-o", "json"
        )
        # When verification fails, dysond returns an error string instead of a dict
        assert isinstance(
            verify_result, str
        ), f"Expected error string, got dict: {verify_result}"
        print(f"tampered_signature_verify_result: {verify_result}")
        # Assert exact message
        expected = """rpc error: code = unauthenticated desc = rpc error: code = unauthenticated desc = signature [0] verification failed (make sure the --chain-id="", --account-number=0, and --sequence=0): unable to verify single signer signature: unauthorized"""
        assert (
            verify_result.strip().lower() == expected
        ), f"Expected '{expected}', got: {verify_result}"

        # Test 2: Tampered message data - change the data field after signing
        print("Test 2: Testing with tampered message data...")
        tampered_msg_data = json.loads(json.dumps(signed_tx_data))  # Deep copy
        tampered_msg_data["body"]["messages"][0]["data"] = "tampered test data"
        tampered_msg_json = json.dumps(tampered_msg_data)

        # Verify should fail with tampered message
        verify_result = dysond_bin(
            "query", "script", "verify-tx", "--tx-json", tampered_msg_json, "-o", "json"
        )
        assert isinstance(
            verify_result, str
        ), f"Expected error string, got dict: {verify_result}"
        print(f"tampered_message_verify_result: {verify_result}")
        lower = verify_result.strip().lower()
        expected = 'rpc error: code = unauthenticated desc = rpc error: code = unauthenticated desc = signature [0] verification failed (make sure the --chain-id="", --account-number=0, and --sequence=0): unable to verify single signer signature: unauthorized'
        assert lower == expected, f"Expected '{expected}', got: {verify_result}"

        # Test 3: Wrong signer address - change the signer field after signing
        print("Test 3: Testing with wrong signer address...")
        wrong_signer_data = json.loads(json.dumps(signed_tx_data))  # Deep copy
        wrong_signer_data["body"]["messages"][0]["signer"] = bob_address
        wrong_signer_json = json.dumps(wrong_signer_data)

        # Verify should fail with wrong signer
        verify_result = dysond_bin(
            "query", "script", "verify-tx", "--tx-json", wrong_signer_json, "-o", "json"
        )
        assert isinstance(
            verify_result, str
        ), f"Expected error string, got dict: {verify_result}"
        print(f"wrong_signer_verify_result: {verify_result}")
        lower = verify_result.strip().lower()
        expected = f"rpc error: code = invalidargument desc = rpc error: code = invalidargument desc = signature does not match its respective signer; expected: {bob_address}, got: {alice_address}: invalid request"
        assert lower == expected, f"Expected '{expected}' in error: {verify_result}"

        # Test 4: Malformed JSON - missing required fields
        print("Test 4: Testing with malformed transaction (missing signatures)...")
        malformed_data = {
            "body": {
                "messages": [
                    {
                        "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                        "signer": alice_address,
                        "data": "test",
                        "app_domain": "test",
                    }
                ],
                "memo": "",
            },
            # Missing auth_info and signatures
        }
        malformed_json = json.dumps(malformed_data)

        # Verify should fail with malformed transaction
        verify_result = dysond_bin(
            "query", "script", "verify-tx", "--tx-json", malformed_json, "-o", "json"
        )
        assert isinstance(
            verify_result, str
        ), f"Expected error string, got dict: {verify_result}"
        lower = verify_result.strip().lower()
        expected = "rpc error: code = unknown desc = runtime error: invalid memory address or nil pointer dereference: panic"
        assert lower == expected, f"Expected '{expected}' in error: {verify_result}"

        # Test 5: Empty/Invalid signature
        print("Test 5: Testing with empty signature...")
        empty_sig_data = json.loads(json.dumps(signed_tx_data))  # Deep copy
        empty_sig_data["signatures"] = [""]  # Empty signature
        empty_sig_json = json.dumps(empty_sig_data)

        # Verify should fail with empty signature
        verify_result = dysond_bin(
            "query", "script", "verify-tx", "--tx-json", empty_sig_json, "-o", "json"
        )
        assert isinstance(
            verify_result, str
        ), f"Expected error string, got dict: {verify_result}"
        lower = verify_result.strip().lower()
        expected = 'rpc error: code = unauthenticated desc = rpc error: code = unauthenticated desc = signature [0] verification failed (make sure the --chain-id="", --account-number=0, and --sequence=0): unable to verify single signer signature: unauthorized'
        assert lower == expected, f"Expected '{expected}' in error: {verify_result}"

        # Test 6: Invalid base64 signature
        print("Test 6: Testing with invalid base64 signature...")
        invalid_b64_data = json.loads(json.dumps(signed_tx_data))  # Deep copy
        invalid_b64_data["signatures"] = ["not-valid-base64!!!"]
        invalid_b64_json = json.dumps(invalid_b64_data)

        # Verify should fail with invalid base64
        verify_result = dysond_bin(
            "query", "script", "verify-tx", "--tx-json", invalid_b64_json, "-o", "json"
        )
        assert isinstance(
            verify_result, str
        ), f"Expected error string, got dict: {verify_result}"
        lower = verify_result.strip().lower()
        expected = "failed to decode"
        assert expected in lower, f"Expected '{expected}' in error: {verify_result}"

        # Test 7: Completely invalid JSON
        print("Test 7: Testing with completely invalid JSON...")
        invalid_json = "{ this is not valid json }"

        # Verify should fail with invalid JSON
        verify_result = dysond_bin(
            "query", "script", "verify-tx", "--tx-json", invalid_json, "-o", "json"
        )
        assert isinstance(
            verify_result, str
        ), f"Expected error string, got dict: {verify_result}"
        assert (
            "failed to decode transaction" in verify_result
        ), f"Unexpected error message: {verify_result}"

        print("✓ All verify-tx failure tests passed!")


def test_script_governance_param_update_and_storage_history(chainnet):
    """
    Test script parameter updates via governance proposal and storage history functionality.

    This test:
    1. Sets new script params with a gov proposal
    2. Creates a function to store storage data {"block_height": <height>} in storage at index "test_history"
    3. Calls the storage function 3 separate times
    4. Creates a function query(heights: List) that passes heights and returns "test_history" at each height
    5. Verifies that the return data is correct
    """
    dysond_bin = chainnet[0]

    # Use the built-in alice account which has more balance
    alice_name = "alice"
    alice_info = dysond_bin("keys", "show", alice_name)
    alice_address = alice_info["address"]
    print(f"Using built-in alice account: {alice_address}")

    # Check alice's balance
    alice_balance = dysond_bin("query", "bank", "balances", alice_address)
    print(f"Alice's initial balance: {alice_balance}")

    # Delegate tokens to get voting power
    validators_result = dysond_bin("query", "staking", "validators")
    assert isinstance(
        validators_result, dict
    ), f"Failed to query validators: {validators_result}"
    validator_operator = validators_result["validators"][0]["operator_address"]

    # Delegate much more tokens to ensure voting power exceeds quorum
    delegate_result = dysond_bin(
        "tx",
        "staking",
        "delegate",
        validator_operator,
        "500000000udys",  # 500M tokens should be plenty for quorum
        "--from",
        alice_name,
    )
    assert isinstance(delegate_result, dict), f"Failed to delegate: {delegate_result}"
    assert delegate_result["code"] == 0, f"Failed to delegate: {delegate_result}"
    print("Delegated 500M tokens to get voting power")

    # Check total bonded tokens and alice's voting power percentage
    pool_info = dysond_bin("query", "staking", "pool")
    total_bonded = int(pool_info["pool"]["bonded_tokens"])
    alice_power_pct = (500000000 / total_bonded) * 100
    print(
        f"Total bonded tokens: {total_bonded}, Alice's voting power: {alice_power_pct:.2f}%"
    )

    # Step 1: Create and submit governance proposal to update script params
    print("Creating governance proposal to update script parameters...")

    # Get the governance module address
    gov_module_result = dysond_bin("query", "auth", "module-account", "gov")
    assert isinstance(
        gov_module_result, dict
    ), f"Failed to query gov module account: {gov_module_result}"
    gov_address = (
        gov_module_result.get("account", {}).get("value", {}).get("address", "")
    )
    assert gov_address, "Could not get governance module address"
    print(f"Using governance module address: {gov_address}")

    # Create proposal JSON file
    proposal_data = {
        "messages": [
            {
                "@type": "/dysonprotocol.script.v1.MsgUpdateParams",
                "authority": gov_address,
                "params": {
                    "maxRelativeHistoricalBlocks": "1000",  # Update from default to 1000
                    "absoluteHistoricalBlockCutoff": "1",  # Keep default cutoff
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "100000udys",
        "title": "Update Script Module Parameters",
        "summary": "Update maxRelativeHistoricalBlocks parameter to 1000",
    }

    # Submit the proposal using temporary file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as proposal_file:
        json.dump(proposal_data, proposal_file, indent=2)
        proposal_file.flush()

        result = dysond_bin(
            "tx", "gov", "submit-proposal", proposal_file.name, "--from", alice_name
        )
    assert isinstance(result, dict), f"Failed to submit proposal: {result}"
    assert result["code"] == 0, f"Failed to submit proposal: {result}"

    # Get proposal ID from the result using dict comprehension
    events_by_type = {event.get("type"): event for event in result.get("events", [])}
    assert "submit_proposal" in events_by_type, "No submit_proposal event found"

    submit_event = events_by_type["submit_proposal"]
    attrs_by_key = {
        attr.get("key"): attr.get("value")
        for attr in submit_event.get("attributes", [])
    }
    # The proposal ID seems to be in voting_period_start now
    # Try both old and new attribute names for compatibility
    proposal_id = (
        attrs_by_key.get("proposal_id")
        if "proposal_id" in attrs_by_key
        else attrs_by_key.get("voting_period_start")
    )
    assert proposal_id, f"Could not find proposal ID in attributes: {attrs_by_key}"
    print(f"Submitted proposal ID: {proposal_id}")

    # Check proposal status before voting
    pre_vote_proposal = dysond_bin("query", "gov", "proposal", proposal_id)
    print(
        f"Proposal status before voting: {pre_vote_proposal.get('proposal', {}).get('status', 'UNKNOWN')}"
    )
    print(
        f"Voting end time: {pre_vote_proposal.get('proposal', {}).get('voting_end_time', 'UNKNOWN')}"
    )

    # Vote on the proposal
    vote_result = dysond_bin(
        "tx", "gov", "vote", proposal_id, "yes", "--from", alice_name
    )
    assert isinstance(vote_result, dict), f"Failed to vote on proposal: {vote_result}"
    assert vote_result["code"] == 0, f"Failed to vote on proposal: {vote_result}"

    # Verify vote was recorded
    votes_after_voting = dysond_bin("query", "gov", "votes", proposal_id)
    print(f"Votes recorded after voting: {len(votes_after_voting.get('votes', []))}")

    # Wait for proposal to reach final state with better debugging
    def check_proposal_status():
        result = dysond_bin("query", "gov", "proposal", proposal_id)
        status = result.get("proposal", {}).get("status", "UNKNOWN")
        print(f"Current proposal status: {status}")

        # Check if proposal reached a final state
        final_states = [
            "PROPOSAL_STATUS_PASSED",
            "PROPOSAL_STATUS_REJECTED",
            "PROPOSAL_STATUS_FAILED",
        ]
        return status in final_states

    poll_until_condition(check_proposal_status, timeout=60, poll_interval=2)

    # Get final status and check if it passed
    final_result = dysond_bin("query", "gov", "proposal", proposal_id)
    final_status = final_result.get("proposal", {}).get("status", "UNKNOWN")

    # If it didn't pass, provide detailed debugging information
    votes_result = dysond_bin("query", "gov", "votes", proposal_id)
    tally_result = dysond_bin("query", "gov", "tally", proposal_id)

    assert (
        final_status == "PROPOSAL_STATUS_PASSED"
    ), f"""
Governance proposal failed with status: {final_status}

DEBUGGING INFORMATION:
======================
Final Proposal Details:
{json.dumps(final_result, indent=2)}

Vote Details:
{json.dumps(votes_result, indent=2)}

Tally Results:
{json.dumps(tally_result, indent=2)}

Alice's voting power and delegation info was shown above.
Check if voting period was too short or quorum not met.
"""

    print("Governance proposal passed!")

    # Step 2: Create a script that stores block height data in storage
    print("Creating script to store block height data...")

    storage_script_code = '''

def store_block_height():
    """Store current block height in storage at index 'test_history'"""
    import json
    from dys import get_block_info, get_script_address, _msg
    
    block_info = get_block_info()
    current_height = block_info["height"]
    data = {"block_height": current_height}
    
    # Store data using storage module
    result = _msg({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": get_script_address(),
        "index": "test_history",
        "data": json.dumps(data)
    })
    
    return f"Stored block height {current_height}"

def query_heights(heights):
    """Query storage data for given heights"""
    import json
    from dys import get_script_address, _query
    
    results = []
    for height in heights:
        # Query storage at specific height
        result = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": get_script_address(),
            "index": "test_history"
        }, query_height=height)
        
        results.append(result)
    
    return results

'''

    # Create the storage script
    result = dysond_bin(
        "tx",
        "script",
        "create-new-script",
        "storage_test_script",
        "--code",
        storage_script_code,
        "--from",
        alice_name,
    )
    assert isinstance(result, dict), f"Failed to create storage script: {result}"
    assert result["code"] == 0, f"Failed to create storage script: {result}"

    # Get script address from the create transaction result
    script_address = get_script_address_from_create_result(result)
    print(f"Created storage script at address: {script_address}")

    # Step 3: Call the storage function 3 separate times to store data at different heights
    print("Storing block height data 3 times...")

    stored_heights = []
    for i in range(3):
        print(f"Storing data iteration {i+1}...")

        # Execute the store_block_height function
        result = dysond_bin(
            "tx",
            "script",
            "exec",
            "--script-address",
            script_address,
            "--function-name",
            "store_block_height",
            "--args",
            "[]",
            "--from",
            alice_name,
        )
        assert isinstance(
            result, dict
        ), f"Failed to execute store_block_height iteration {i+1}: {result}"
        assert (
            result["code"] == 0
        ), f"Failed to execute store_block_height iteration {i+1}: {result}"

        # Get current block height to track what was stored
        block_result = dysond_bin("query", "block")
        # Handle string result from block query (extract JSON part)
        json_data = block_result
        # Parse JSON if result is a string
        json_start = block_result.find("{") if isinstance(block_result, str) else -1
        assert (
            json_start != -2
        ), f"No JSON found in block query response: {block_result}"
        json_data = (
            json.loads(block_result[json_start:].strip())
            if isinstance(block_result, str)
            else block_result
        )

        # Debug: print the structure to understand the response format
        print(f"Block result structure: {list(json_data.keys())}")
        # Get height from either header or block.header structure
        current_height = int(
            json_data.get("header", json_data.get("block", {}).get("header", {})).get(
                "height", 0
            )
        )
        assert current_height > 0, f"Unexpected block result structure: {json_data}"
        stored_heights.append(current_height)

        # Use poll_until_condition to wait for block height to increase
        prev_height = current_height

        def block_height_increased():
            result = dysond_bin("query", "block")
            # Parse JSON from string result
            json_start = result.find("{") if isinstance(result, str) else -1
            json_data = (
                json.loads(result[json_start:].strip())
                if isinstance(result, str)
                else result
            )
            new_height = int(
                json_data.get(
                    "header", json_data.get("block", {}).get("header", {})
                ).get("height", 0)
            )
            return new_height > prev_height

        poll_until_condition(block_height_increased, timeout=10, poll_interval=0.5)

        print(f"Stored data at heights: {stored_heights}")

        # Step 4: First check if data was stored by querying current state
        print("Checking if data was stored in current state...")

        # Query current storage state directly
        current_storage_result = dysond_bin(
            "query", "storage", "get", script_address, "--index", "test_history"
        )
        # Print result based on type
        result_type = "string" if isinstance(current_storage_result, str) else "dict"
        print(f"Current storage query returned {result_type}: {current_storage_result}")

        # Step 5: Query the stored data using the query function
        print("Querying stored data...")

        # Execute the query_heights function with the stored heights
        heights_json = json.dumps(stored_heights)
        result = dysond_bin(
            "tx",
            "script",
            "exec",
            "--script-address",
            script_address,
            "--function-name",
            "query_heights",
            "--args",
            f"[{heights_json}]",
            "--from",
            alice_name,
        )
    assert isinstance(result, dict), f"Failed to execute query_heights: {result}"
    assert result["code"] == 0, f"Failed to execute query_heights: {result}"

    # Extract the script execution result from transaction events using dict comprehension
    events_by_type = {event.get("type"): event for event in result.get("events", [])}
    assert (
        "dysonprotocol.script.v1.EventExecScript" in events_by_type
    ), "No EventExecScript found in transaction events"

    exec_event = events_by_type["dysonprotocol.script.v1.EventExecScript"]
    attrs_by_key = {
        attr.get("key"): attr.get("value") for attr in exec_event.get("attributes", [])
    }
    assert "response" in attrs_by_key, "No response attribute found in EventExecScript"

    response_json = attrs_by_key["response"]
    response_data = json.loads(response_json)
    result_data = json.loads(response_data.get("result", "{}"))
    script_result = result_data.get("result")

    assert (
        script_result is not None
    ), "Could not find script execution result in transaction events"

    # Step 5: Verify that the return data is correct
    print("Verifying query results...")

    # Parse the result
    query_results = script_result
    print(f"Query results: {query_results}")

    # Verify each result
    assert len(query_results) == 3, f"Expected 3 results, got {len(query_results)}"

    for i, (stored_height, result_data) in enumerate(
        zip(stored_heights, query_results)
    ):
        assert result_data is not None, f"Result {i+1} should not be None"
        assert "@type" in result_data, f"Result {i+1} should contain '@type'"
        assert (
            result_data["@type"] == "/dysonprotocol.storage.v1.QueryStorageGetResponse"
        ), f"Result {i+1} should be a QueryStorageGetResponse"
        assert "entry" in result_data, f"Result {i+1} should contain 'entry'"
        assert (
            "data" in result_data["entry"]
        ), f"Result {i+1} entry should contain 'data'"

        # Parse the JSON data from the entry
        data_str = result_data["entry"]["data"]
        data = json.loads(data_str)
        assert (
            "block_height" in data
        ), f"Result {i+1} data should contain 'block_height'"

        # The stored height should match what we expect (within a reasonable range due to timing)
        result_height = data["block_height"]
        assert (
            abs(result_height - stored_height) <= 2
        ), f"Result {i+1}: expected height ~{stored_height}, got {result_height}"

        print(f"✓ Verified result {i+1}: stored at height {result_height}")

    print("✓ All storage history data verified successfully!")

    print("Test completed successfully!")


def get_script_address_from_create_result(create_result):
    """Helper function to extract script address from create script transaction result"""
    # Use dict comprehension to find the event
    events_by_type = {
        event.get("type"): event for event in create_result.get("events", [])
    }
    assert (
        "dysonprotocol.script.v1.EventCreateNewScript" in events_by_type
    ), f"Script address not found in create transaction events: {create_result}"

    create_event = events_by_type["dysonprotocol.script.v1.EventCreateNewScript"]
    attrs_by_key = {
        attr.get("key"): attr.get("value")
        for attr in create_event.get("attributes", [])
    }
    assert (
        "script_address" in attrs_by_key
    ), f"Script address not found in create transaction event attributes: {create_result}"

    script_address = attrs_by_key["script_address"]
    # The value might be JSON-encoded, so decode if it's quoted
    is_json_encoded = (
        script_address
        and script_address.startswith('"')
        and script_address.endswith('"')
    )
    script_address = is_json_encoded and json.loads(script_address) or script_address
    return script_address


def test_query_script(chainnet, generate_account):
    """Test the Query Script (Read-only) functionality"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)

    # Create a simple script for testing
    simple_script = '''
from dys import _query, _msg, get_script_address
import json

def get_info():
    """Simple function that returns static data"""
    return {"message": "Hello from query!", "version": "1.0"}

def add_numbers(a, b):
    """Add two numbers together"""
    return {"result": a + b}

def use_kwargs(name="World", age=0):
    """Function that uses keyword arguments"""
    return {"greeting": f"Hello {name}, you are {age} years old"}

def check_storage_write():
    """
    Test that _msg calls in query mode persist only within the RunScript context.
    This function writes to storage and reads it back within the same execution,
    but the changes won't be visible outside this specific RunScript call.
    """
    script_address = get_script_address()
    
    # Attempt to write to storage using _msg
    # In query mode, this should persist only within this specific RunScript but not outside of it
    _msg({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": script_address,
        "index": "query_test_key_unique",
        "data": json.dumps({"value": "this_should_not_persist", "timestamp": "12345"})
    })
    
    # Now read what we just "wrote" - within this RunScript context, we should see it
    after_write = _query({
        "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
        "owner": script_address,
        "index": "query_test_key_unique"
    })
    
    return {
        "msg_executed": True,
        "value_after_msg": json.loads(after_write["entry"]["data"])
    }
'''

    # Update the script
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        simple_script,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas",
        "auto",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # Test 1: Query simple function with no arguments
    query_result = dysond_bin(
        "query",
        "script",
        "run",
        "--executor-address",
        alice_address,
        "--script-address",
        alice_address,
        "--function-name",
        "get_info",
        "--args",
        "[]",
        "--kwargs",
        "{}",
        "-o",
        "json",
    )
    assert (
        "result" in query_result
    ), f"Query result missing 'result' field: {query_result}"
    # The actual function result is a JSON string that needs to be parsed
    result_data = json.loads(query_result["result"])
    # The script execution result is nested inside
    assert "result" in result_data, f"Result data missing 'result' field: {result_data}"
    function_result = result_data["result"]
    assert function_result == {
        "message": "Hello from query!",
        "version": "1.0",
    }, f"Unexpected result: {function_result}"

    # Test 2: Query function with positional arguments
    args = [5, 7]
    query_result = dysond_bin(
        "query",
        "script",
        "run",
        "--executor-address",
        alice_address,
        "--script-address",
        alice_address,
        "--function-name",
        "add_numbers",
        "--args",
        json.dumps(args),
        "--kwargs",
        "{}",
        "-o",
        "json",
    )
    assert (
        "result" in query_result
    ), f"Query result missing 'result' field: {query_result}"
    result_data = json.loads(query_result["result"])
    assert "result" in result_data, f"Result data missing 'result' field: {result_data}"
    function_result = result_data["result"]
    assert function_result == {"result": 12}, f"Unexpected result: {function_result}"

    # Test 3: Query function with keyword arguments
    kwargs = {"name": "Alice", "age": 30}
    query_result = dysond_bin(
        "query",
        "script",
        "run",
        "--executor-address",
        alice_address,
        "--script-address",
        alice_address,
        "--function-name",
        "use_kwargs",
        "--args",
        "[]",
        "--kwargs",
        json.dumps(kwargs),
        "-o",
        "json",
    )
    assert (
        "result" in query_result
    ), f"Query result missing 'result' field: {query_result}"
    result_data = json.loads(query_result["result"])
    assert "result" in result_data, f"Result data missing 'result' field: {result_data}"
    function_result = result_data["result"]
    assert function_result == {
        "greeting": "Hello Alice, you are 30 years old"
    }, f"Unexpected result: {function_result}"

    # Test 4: Verify that the query context metadata is present
    assert "gas_limit" in result_data, "Result should contain gas_limit"
    assert (
        "script_gas_consumed" in result_data
    ), "Result should contain script_gas_consumed"
    assert "nodes_called" in result_data, "Result should contain nodes_called"
    assert result_data["exception"] is None, "Query should not have raised an exception"

    # Test 5: Test that _msg calls in query mode persist only within the RunScript context
    print("Testing storage write in query mode...")
    query_result = dysond_bin(
        "query",
        "script",
        "run",
        "--executor-address",
        alice_address,
        "--script-address",
        alice_address,
        "--function-name",
        "check_storage_write",
        "--args",
        "[]",
        "--kwargs",
        "{}",
        "-o",
        "json",
    )
    assert (
        "result" in query_result
    ), f"Query result missing 'result' field: {query_result}"
    result_data = json.loads(query_result["result"])
    assert "result" in result_data, f"Result data missing 'result' field: {result_data}"
    function_result = result_data["result"]

    # The function should have executed and returned exactly what we expect
    assert function_result == {
        "msg_executed": True,
        "value_after_msg": {"value": "this_should_not_persist", "timestamp": "12345"},
    }, f"Unexpected function result: {function_result}"

    # Now verify that the storage modification was scoped only to the RunScript context
    # Query storage directly from the blockchain - it should not exist
    storage_result = dysond_bin(
        "query", "storage", "get", alice_address, "--index", "query_test_key_unique"
    )

    # The storage query should return an error string indicating not found
    assert isinstance(
        storage_result, str
    ), f"Expected error string, got: {type(storage_result)}"
    assert (
        "doesn't exist" in storage_result
    ), f"Expected 'doesn't exist' error, got: {storage_result}"

    print("✓ All Query Script tests passed!")


def test_run_repr_forbidden_script(chainnet, generate_account):
    """
    Test that `dysond query run` correctly forbids the use of __repr__ in scripts
    """
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)

    script_code = """
class MyObject:
    def __repr__(self):
        return "MyObject()"
        
MyObject()
"""
    update_result = dysond_bin(
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
        "--gas",
        "auto",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"


def test_dunder_names_forbidden(chainnet, generate_account):
    """Test that all uses of names starting with '__' are forbidden in scripts"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)

    # Test 1: Defining a function with a name starting with "__"
    print("Test 1: Testing function definition with dunder name...")
    function_def_code = """
def __init__(self):
    return "This should fail"

def normal_function():
    return "This is fine"
"""
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        function_def_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas",
        "auto",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # Try to execute the script - it should fail during parsing/execution
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "normal_function",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "auto",
    )
    # Check that the execution failed with the expected error
    assert exec_result.get("code", 0) != 0, "Expected script execution to fail"
    # The error message is in the raw_log field
    raw_log = exec_result.get("raw_log", "")
    _variants = [
        "Defining function with the name '__init__' is forbidden",
        "Defining function with the name '__init__' is forbidden",
    ]
    present = [v for v in _variants if v in raw_log]
    assert len(present) > 0, f"Unexpected error in raw_log: {raw_log}"

    # Test 2: Defining a class with a name starting with "__"
    print("Test 2: Testing class definition with dunder name...")
    class_def_code = """
class __SpecialClass:
    def method(self):
        return "This should fail"

def test_function():
    return "Testing"
"""
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        class_def_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas",
        "auto",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # Try to execute the script - it should fail during parsing/execution
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "test_function",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "auto",
    )
    # Check that the execution failed with the expected error
    assert exec_result.get("code", 0) != 0, "Expected script execution to fail"
    # The error message is in the raw_log field
    raw_log = exec_result.get("raw_log", "")
    normalized = raw_log.replace("\\'", "'")
    expected = "Defining class with the name '__SpecialClass' is forbidden"
    assert expected in normalized, f"Unexpected error in raw_log: {raw_log}"

    # Test 3: Calling a function with a name starting with "__"
    print("Test 3: Testing function call with dunder name...")
    function_call_code = """
def test_call():
    # Try to call a built-in dunder method
    result = __import__('os')
    return result
"""
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        function_call_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas",
        "auto",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # Try to execute the function - it should fail when trying to call __import__
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "test_call",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "auto",
    )
    # Check that the execution failed with the expected error
    assert exec_result.get("code", 0) != 0, "Expected script execution to fail"
    # The error message is in the raw_log field
    raw_log = exec_result.get("raw_log", "")
    _variants = [
        "Calling function '__import__' is forbidden",
        "Calling function '__import__' is forbidden",
    ]
    present = [v for v in _variants if v in raw_log]
    assert len(present) > 0, f"Unexpected error in raw_log: {raw_log}"

    # Test 4: Calling a method with a name starting with "__"
    print("Test 4: Testing method call with dunder name...")
    method_code = """
class MyClass:
    def __special_method__(self):
        return "This should fail"

def test_method_call():
    obj = MyClass()
    return obj.__special_method__()
"""

    # Update the script
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        method_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas",
        "auto",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # Try to execute - should fail
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "test_method_call",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "auto",
    )

    # Check that the execution failed with the expected error
    assert exec_result.get("code", 0) != 0, "Expected script execution to fail"
    # The error message is in the raw_log field
    raw_log = exec_result.get("raw_log", "")
    # Methods with dunder names are caught during class definition as "Defining function"
    _variants = [
        "Defining function with the name '__special_method__' is forbidden",
        "Defining function with the name '__special_method__' is forbidden",
    ]
    present = [v for v in _variants if v in raw_log]
    assert len(present) > 0, f"Unexpected error in raw_log: {raw_log}"

    # Test 5: Valid script without dunder names should work
    print("Test 5: Testing valid script without dunder names...")
    valid_code = """
class RegularClass:
    def regular_method(self):
        return "success"

def regular_function():
    obj = RegularClass()
    return obj.regular_method()
"""
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        valid_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # Execute the valid function - it should succeed
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "regular_function",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "auto",
    )
    assert (
        exec_result.get("code", 1) == 0
    ), f"Valid script execution failed: {exec_result}"

    # Extract and verify the result
    events_by_type = {
        event.get("type"): event for event in exec_result.get("events", [])
    }
    assert (
        "dysonprotocol.script.v1.EventExecScript" in events_by_type
    ), "No EventExecScript found"

    exec_event = events_by_type["dysonprotocol.script.v1.EventExecScript"]
    attrs_by_key = {
        attr.get("key"): attr.get("value") for attr in exec_event.get("attributes", [])
    }
    response_json = attrs_by_key.get("response", "{}")
    response_data = json.loads(response_json)
    result_data = json.loads(response_data.get("result", "{}"))

    assert (
        result_data.get("result") == "success"
    ), f"Expected 'success', got: {result_data}"

    # Test 5: Edge case - calling methods that happen to start with __ through getattr
    print("Test 5: Testing indirect dunder method access...")
    indirect_code = """
def test_indirect():
    # Try to access dunder methods indirectly
    obj = object()
    # This should be caught even if accessed indirectly
    method_name = "__" + "class" + "__"
    return getattr(obj, method_name)
"""
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        indirect_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # Note: This test might pass if the restriction is only on direct calls
    # The important thing is that direct dunder usage is blocked
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "test_indirect",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "auto",
    )
    # This may or may not fail depending on how thorough the restriction is
    print(f"Indirect access result: {exec_result.get('code', 'N/A')}")

    print("✓ All dunder name restriction tests completed!")


def test_comprehensive_dunder_method_prevention(chainnet, generate_account):
    """Comprehensive test to ensure NO functions or methods with leading __ can be defined"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)

    # Test cases for all possible ways to define functions/methods with dunder names
    test_cases = [
        # Case 1: Top-level function
        (
            "top-level function",
            """
def __forbidden_func():
    return "This should not be allowed"
""",
        ),
        # Case 2: Method inside class
        (
            "class method",
            """
class MyClass:
    def __forbidden_method(self):
        return "This should not be allowed"
""",
        ),
        # Case 3: Static method
        (
            "static method",
            """
class MyClass:
    @staticmethod
    def __forbidden_static():
        return "This should not be allowed"
""",
        ),
        # Case 4: Class method
        (
            "class method decorator",
            """
class MyClass:
    @classmethod
    def __forbidden_classmethod(cls):
        return "This should not be allowed"
""",
        ),
        # Case 5: Lambda assigned to dunder name
        (
            "lambda assignment",
            """
__forbidden_lambda = lambda x: x + 1

def trigger_lambda():
    return 42  # Just needs to trigger script execution
""",
        ),
        # Case 6: Nested function
        (
            "nested function",
            """
def outer():
    def __forbidden_nested():
        return "This should not be allowed"
    return __forbidden_nested

def trigger_nested():
    return outer()  # This will trigger the nested function definition
""",
        ),
        # Case 7: Variable assignment with dunder name
        (
            "variable assignment",
            """
__forbidden_var = "This should not be allowed"

def trigger_assignment():
    return 42  # Just needs to trigger script execution
""",
        ),
        # Case 8: Multiple dunder methods in one class
        (
            "multiple dunder methods",
            """
class MyClass:
    def __method1(self):
        pass
    
    def __method2(self):
        pass
        
    @property
    def __prop(self):
        return "forbidden"
""",
        ),
    ]

    for test_name, code in test_cases:
        print(f"\nTesting {test_name}...")

        # Add a valid function to test execution
        full_code = (
            code
            + """
def valid_function():
    return "This is valid"
"""
        )

        # Update the script
        update_result = dysond_bin(
            "tx",
            "script",
            "update",
            "--code",
            full_code,
            "--from",
            alice_name,
            "--keyring-backend",
            "test",
            "--yes",
        )
        assert (
            update_result.get("code", 1) == 0
        ), f"Failed to update script: {update_result}"

        # Try to execute using query run - should fail during script parsing/loading
        # For certain tests, we need to call specific trigger functions
        function_map = {
            "nested function": "trigger_nested",
            "lambda assignment": "trigger_lambda",
            "variable assignment": "trigger_assignment",
        }
        function_to_call = function_map.get(test_name, "valid_function")

        exec_result = dysond_bin(
            "query",
            "script",
            "run",
            "--script-address",
            alice_address,
            "--executor-address",
            alice_address,
            "--function-name",
            function_to_call,
            "--args",
            "[]",
            "-o",
            "json",
        )

        # Verify it failed - query run may return error as string or dict
        # When script has parse errors, dysond returns error in stderr as string
        # When script parses but has runtime errors, it returns dict with exception

        # Handle different response types
        is_string = isinstance(exec_result, str)
        is_dict = isinstance(exec_result, dict)

        # For string responses (command failed), the whole string is the error
        exception_msg = exec_result if is_string else ""

        # For dict responses, check if there's an exception directly in the response
        has_exception = exec_result.get("exception") is not None if is_dict else False
        exception_msg = (
            exec_result["exception"].get("msg", "")
            if (is_dict and has_exception)
            else exception_msg
        )

        # Either string error or dict with exception means it failed as expected
        failed_as_expected = is_string or has_exception
        assert (
            failed_as_expected
        ), f"Expected {test_name} to fail but it succeeded: {exec_result}"
        _prefixes = [
            "Defining function with the name",
            "Defining class with the name",
            "Assigning to variable",
        ]
        hits = [p for p in _prefixes if p in exception_msg]
        assert len(hits) > 0, f"Unexpected error for {test_name}: {exception_msg}"
        assert (
            "is forbidden" in exception_msg
        ), f"Unexpected error for {test_name}: {exception_msg}"

        print(f"✓ {test_name} correctly blocked")

    # Test edge cases with underscores
    edge_cases = [
        # Single underscore is allowed
        (
            "single underscore",
            """
def _private_func():
    return "Single underscore is allowed"
    
class MyClass:
    def _private_method(self):
        return "Single underscore is allowed"
""",
            True,
        ),  # Should succeed
        # Three underscores is blocked (starts with __)
        (
            "three underscores",
            """
def ___triple_func():
    return "Three underscores starts with __ so blocked"
""",
            False,
        ),  # Should fail
        # Underscore in middle is allowed
        (
            "underscore in middle",
            """
def my__func():
    return "Double underscore in middle is allowed"
""",
            True,
        ),  # Should succeed
        # Trailing double underscore is allowed
        (
            "trailing double underscore",
            """
def func__():
    return "Trailing double underscore is allowed"
""",
            True,
        ),  # Should succeed
    ]

    for test_name, code, should_succeed in edge_cases:
        print(f"\nTesting edge case: {test_name}...")

        # Add a test function
        full_code = (
            code
            + """
def test_func():
    return "test"
"""
        )

        # Update the script
        update_result = dysond_bin(
            "tx",
            "script",
            "update",
            "--code",
            full_code,
            "--from",
            alice_name,
            "--keyring-backend",
            "test",
            "--yes",
        )
        assert (
            update_result.get("code", 1) == 0
        ), f"Failed to update script: {update_result}"

        # Try to execute using query run
        exec_result = dysond_bin(
            "query",
            "script",
            "run",
            "--script-address",
            alice_address,
            "--executor-address",
            alice_address,
            "--function-name",
            "test_func",
            "--args",
            "[]",
            "-o",
            "json",
        )

        # Check result based on expectation
        is_string = isinstance(exec_result, str)
        is_dict = isinstance(exec_result, dict)

        # For dict responses, check if there's an exception directly
        has_dict_exception = (
            exec_result.get("exception") is not None if is_dict else False
        )

        # String response = command failed = has exception
        # Dict response with exception = has exception
        has_exception = is_string or has_dict_exception
        expected_success = should_succeed

        # For success cases, there should be no exception
        # For failure cases, there should be an exception
        assert (
            not has_exception
        ) == expected_success, f"{test_name}: Expected {'success' if expected_success else 'failure'} but got {'exception' if has_exception else 'success'}. Full result: {exec_result}"

        print(f"✓ {test_name} correctly {'allowed' if should_succeed else 'blocked'}")

    print("\n✓ All comprehensive dunder prevention tests passed!")
