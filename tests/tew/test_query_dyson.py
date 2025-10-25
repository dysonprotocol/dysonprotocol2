"""
Test query_dyson functionality for TEW transactions.

This test demonstrates how L2 transactions can query DysonProtocol storage
through the L1/L2 message queue system.
"""

import json
from pathlib import Path
import pytest

from tests.tew import utils


def test_l2_query_dyson_functionality(chainnet, generate_account, faucet):
    """Test that L2 transactions can query Dyson storage through L1."""
    dysond_bin = chainnet[0]

    # Create and fund account for TewProtocol operator
    tew_name, tew_addr = generate_account("tew", faucet_amount=1000000)
    print(f"Created TEW operator account: {tew_name} -> {tew_addr}")

    # Create and fund a regular user account
    user_name, user_addr = generate_account("alice", faucet_amount=1000000)
    print(f"Created user account: {user_name} -> {user_addr}")

    # Delegate stake for TEW operator and user to satisfy storage stake validation
    validators = dysond_bin("query", "staking", "validators")
    validator_operator = validators["validators"][0]["operator_address"]
    tew_delegate = dysond_bin(
        "tx",
        "staking",
        "delegate",
        validator_operator,
        "200000udys",
        "--from",
        tew_name,
        "--yes",
    )
    assert tew_delegate.get("code", 1) == 0, f"TEW delegation failed: {tew_delegate}"
    user_delegate = dysond_bin(
        "tx",
        "staking",
        "delegate",
        validator_operator,
        "100000udys",
        "--from",
        user_name,
        "--yes",
    )
    assert user_delegate.get("code", 1) == 0, f"User delegation failed: {user_delegate}"
    print("✓ Delegated stake for TEW operator and user")

    # Read and upload queue_chain.py
    project_root = Path(__file__).parent.parent.parent
    queue_chain_path = project_root / "demo-tew" / "queue_chain.py"

    print("\n=== Step 1: Upload queue_chain.py ===")
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code-path",
        str(queue_chain_path),
        "--from",
        tew_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas-adjustment",
        "1.5",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"
    print("✓ Script uploaded successfully")

    # Initialize L1 and L2
    instance_id = "query-test"
    chain_id = f"tew-{instance_id}"

    print(f"\n=== Step 2: Initialize L1 for instance '{instance_id}' ===")
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        tew_addr,
        "--function-name",
        "initialize_l1",
        "--args",
        json.dumps([instance_id]),
        "--from",
        tew_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas-adjustment",
        "1.5",
    )
    assert exec_result.get("code", 1) == 0, f"L1 initialization failed: {exec_result}"
    print("✓ L1 initialized")

    print(f"\n=== Step 3: Initialize L2 genesis ===")
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        tew_addr,
        "--function-name",
        "initialize_l2_genesis",
        "--args",
        json.dumps([instance_id, chain_id, tew_addr]),
        "--from",
        tew_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas-adjustment",
        "1.5",
    )
    assert exec_result.get("code", 1) == 0, f"L2 genesis failed: {exec_result}"
    print("✓ L2 genesis initialized")

    # Store some test data in Dyson storage that we'll query
    test_key = f"test/{instance_id}/sample_data"
    test_data = {"message": "Hello from Dyson storage!", "value": 42}

    print(f"\n=== Step 4: Store test data in Dyson storage ===")
    # Use raw transaction to store data
    exec_result = dysond_bin(
        "tx",
        "storage",
        "set",
        "--index",
        test_key,
        "--data",
        json.dumps(test_data),
        "--from",
        user_name,
        "--yes",
        "--gas-adjustment",
        "1.5",
    )
    # Wait for transaction to be included
    wait_result = dysond_bin(
        "query",
        "wait-tx",
        exec_result["txhash"],
    )
    assert wait_result.get("code", 1) == 0, f"Storage set failed: {wait_result}"
    print(f"✓ Stored data at key: {test_key}")

    # Create a TEW transaction that queries the storage
    query_tx_code = f"""
# Query Dyson storage from L2
query_params = {{
    "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
    "owner": "{user_addr}",
    "index": "{test_key}"
}}

# Send query to L1
msg_id = query_dyson(query_params)
print("Sent query request with message ID: " + str(msg_id))

# Return the message ID
msg_id
"""

    print("\n=== Step 5: Create TEW transaction that queries storage ===")
    signed_tx = utils.create_signed_tx(
        dysond_bin=dysond_bin,
        signer_name=user_name,
        signer_addr=user_addr,
        chain_id=chain_id,
        sequence=0,
        tx_data_str=query_tx_code,
    )

    # Create L2 genesis state with both the TEW operator and user accounts
    genesis_state = {
        "accounts_by_number": {
            "0": {"address": tew_addr, "account_number": 0, "sequence": 0},
            "1": {"address": user_addr, "account_number": 1, "sequence": 0},
        },
        "account_numbers_by_address": {tew_addr: 0, user_addr: 1},
        "next_account_number": 2,
        "l1_queue_state": None,
        "l2_queue_state": None,
        "captured_stdout": "",
    }

    # Create L2 block metadata - first block must be height 0
    block0_metadata = {
        "chain_id": chain_id,
        "height": 0,
        "time": "2024-01-01T00:00:00Z",
        "current_authority": tew_addr,
        "next_authority": tew_addr,
        "total_tx_count": 0,
        "instance_id": instance_id,
    }

    # Build L2 block with the query transaction
    signed_block0 = utils.create_signed_block(
        dysond_bin=dysond_bin,
        signer_name=tew_name,
        sequence=0,
        block_data={
            "prev_signed_tew_block_hash": "genesis",
            "metadata": block0_metadata,
            "pre_state": genesis_state,
            "signed_txs": [signed_tx],
            "tx_results": [],
            "post_state": genesis_state,  # Will be updated by build_next_block
        },
    )

    print("\n=== Step 6: Build L2 block 0 with query transaction ===")
    # Build the block
    block0_result = utils.run_build_next_block(
        dysond_bin=dysond_bin,
        script_addr=tew_addr,
        signed_block=signed_block0,
        prev_meta=None,
        prev_hash="genesis_hash",
    )

    # The result is already parsed
    print(f"✓ L2 block 0 built successfully")

    # Check that the query message was sent
    l2_state = block0_result["post_state"]["l2_queue_state"]
    assert "0" in l2_state["outgoing_queue"], "Query message not in L2 outgoing queue"
    query_msg = l2_state["outgoing_queue"]["0"]
    print(f"L2 sent query message: {query_msg}")

    # Check transaction result
    tx_result = block0_result["tx_results"][0]
    assert tx_result["error"] is None, f"Transaction failed: {tx_result['error']}"
    print(f"Transaction returned message ID: {tx_result['result']}")

    # Now submit the L2 block to L1 to process the query
    print("\n=== Step 7: Submit L2 block to L1 to process query ===")

    # Create a new signed block with the actual post_state
    signed_block0_updated = utils.create_signed_block(
        dysond_bin=dysond_bin,
        signer_name=tew_name,
        sequence=1,
        block_data=block0_result,
    )

    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        tew_addr,
        "--function-name",
        "submit_l2_block",
        "--args",
        json.dumps([json.dumps(signed_block0_updated), instance_id]),
        "--from",
        tew_name,
        "--keyring-backend",
        "test",
        "--yes",
        "--gas-adjustment",
        "1.5",
    )

    assert exec_result.get("code", 1) == 0, f"L2 block submission failed: {exec_result}"

    # Extract the result
    events_by_type = {
        event.get("type"): event for event in exec_result.get("events", [])
    }
    exec_event = events_by_type.get("dysonprotocol.script.v1.EventExecScript")
    assert (
        exec_event
    ), f"No EventExecScript found. Events: {list(events_by_type.keys())}"

    response_data = next(
        (
            attr["value"]
            for attr in exec_event["attributes"]
            if attr["key"] == "response"
        ),
        None,
    )
    assert response_data, f"No response found in EventExecScript: {exec_event}"

    submit_result = json.loads(json.loads(response_data).get("result", "{}")).get(
        "result"
    )
    print(f"Submit result: {submit_result}")

    # Verify that L1 processed the query and generated a response
    print("\n=== Step 8: Check L1 response queue ===")

    # Get L1 state to check the response
    l1_state = dysond_bin(
        "query",
        "storage",
        "get",
        tew_addr,
        "--index",
        f"tew/{instance_id}/l1",
        "-o",
        "json",
    )

    l1_data = json.loads(l1_state["entry"]["data"])
    assert "0" in l1_data["response_queue"], "Query response not in L1 response queue"

    query_response = l1_data["response_queue"]["0"]
    print(f"L1 query response: {query_response}")

    # Verify the response contains the data we stored
    response_data = query_response["response_data"]
    assert (
        response_data["type"] == "query_response"
    ), f"Unexpected response type: {response_data}"
    assert response_data["error"] is None, f"Query error: {response_data['error']}"

    # The result should contain our stored data
    query_result = response_data["result"]
    assert "entry" in query_result, f"No entry in query result: {query_result}"
    stored_data = json.loads(query_result["entry"]["data"])
    assert (
        stored_data == test_data
    ), f"Retrieved data doesn't match. Expected: {test_data}, Got: {stored_data}"

    print("\n🎉 Query Dyson Test Complete!")
    print(f"  - L2 transaction queried storage key: {test_key}")
    print(f"  - L1 executed the query and returned: {stored_data}")
    print(f"  - Query functionality working correctly!")
