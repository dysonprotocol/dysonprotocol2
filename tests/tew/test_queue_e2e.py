"""
End-to-end test for TewQueue message flow: L1 → L2 → L1

This test demonstrates the complete flow:
1. User sends greeting via L1
2. L2 processes and computes response
3. L1 receives and stores the response
"""

import json
from pathlib import Path
import pytest

from tests.tew import utils


def test_l1_l2_greeting_echo_flow(chainnet, generate_account, faucet):
    """Test complete L1→L2→L1 message flow with greeting echo service."""
    dysond_bin = chainnet[0]

    # Create and fund account for TewProtocol operator
    tew_name, tew_addr = generate_account("tew", faucet_amount=1000000)
    print(f"Created TEW operator account: {tew_name} -> {tew_addr}")

    # Create and fund a regular user account
    user_name, user_addr = generate_account("alice", faucet_amount=1000000)
    print(f"Created user account: {user_name} -> {user_addr}")

    # Delegate some stake for the script owner (required for storage writes)
    validators = dysond_bin("query", "staking", "validators")
    validator_operator = validators["validators"][0]["operator_address"]
    delegate_result = dysond_bin(
        "tx",
        "staking",
        "delegate",
        validator_operator,
        "100000udys",  # 100k udys >> 135 bytes requirement
        "--from",
        tew_name,
        "--yes",
    )
    assert delegate_result["code"] == 0, f"Delegation failed: {delegate_result}"
    print("✓ Delegated stake for TEW operator to satisfy storage stake validation")

    # Upload queue_chain.py script
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
        "--gas",
        "auto",
        "--gas-adjustment",
        "1.5",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"
    print("✓ Script uploaded successfully")

    # Initialize L1 and L2
    instance_id = "echo-test"
    chain_id = "tew-echo-test"  # Must be in format "tew-{instance_id}"

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
        "--gas",
        "auto",
        "--gas-adjustment",
        "1.5",
    )
    assert exec_result.get("code", 1) == 0, f"Failed to initialize L1: {exec_result}"
    print("✓ L1 initialized")

    print(
        f"\n=== Step 3: Initialize L2 genesis for chain '{chain_id}' (instance '{instance_id}') ==="
    )
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
        "--gas",
        "auto",
        "--gas-adjustment",
        "1.5",
    )
    assert (
        exec_result.get("code", 1) == 0
    ), f"Failed to initialize L2 genesis: {exec_result}"
    print("✓ L2 genesis initialized")

    # User sends greeting through L1
    greeting_text = "Hello from Alice"

    print(f"\n=== Step 4: User sends greeting '{greeting_text}' through L1 ===")
    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        tew_addr,
        "--function-name",
        "say_hi",
        "--args",
        json.dumps([greeting_text, instance_id]),
        "--from",
        user_name,  # Regular user, not TEW operator
        "--keyring-backend",
        "test",
        "--yes",
        "--gas",
        "auto",
        "--gas-adjustment",
        "1.5",
    )
    assert exec_result.get("code", 1) == 0, f"Failed to send greeting: {exec_result}"

    # Extract the message ID from the result
    events_by_type = {
        event.get("type"): event for event in exec_result.get("events", [])
    }
    exec_event = events_by_type.get("dysonprotocol.script.v1.EventExecScript")
    assert exec_event, f"No EventExecScript found"

    attrs_by_key = {
        attr.get("key"): attr.get("value") for attr in exec_event.get("attributes", [])
    }
    response_json = attrs_by_key.get("response")
    assert response_json, f"No response found in EventExecScript: {exec_event}"
    response_data = json.loads(response_json)
    result_data = json.loads(response_data.get("result", "{}"))
    result = result_data.get("result")

    print(f"✓ Greeting sent, message_id: {result['message_id']}")
    assert result["status"] == "message_sent"
    assert result["greeting"] == greeting_text
    assert result["sender"] == user_addr
    message_id = result["message_id"]

    # Now we need to build an L2 block that will process this message
    print("\n=== Step 5: Build L2 block 1 to process the L1 message ===")

    # First, load the current L1 state to get the message
    query_result = dysond_bin(
        "query",
        "storage",
        "get",
        tew_addr,
        "--index",
        f"tew/{instance_id}/l1",
    )
    l1_state = json.loads(query_result["entry"]["data"])
    print(f"L1 outgoing queue has {len(l1_state['outgoing_queue'])} messages")
    assert str(message_id) in l1_state["outgoing_queue"]

    # Create L2 genesis state
    genesis_state = {
        "chain_logic": "",  # Empty chain logic - callbacks are built-in
        "accounts_by_number": {
            "0": {"address": tew_addr, "account_number": 0, "sequence": 0}
        },
        "account_numbers_by_address": {tew_addr: 0},
        "next_account_number": 1,
        "l1_queue_state": None,  # Will be loaded from storage
        "l2_queue_state": None,  # Will be created fresh
    }

    genesis_metadata = {
        "chain_id": chain_id,
        "height": 0,
        "time": "2024-01-01T00:00:00Z",
        "current_authority": tew_addr,
        "next_authority": tew_addr,
        "total_tx_count": 0,
        "instance_id": instance_id,
    }

    # Create a simple transaction for the block
    dummy_tx_code = "'Block 1 processing L1 messages'"

    signed_tx = utils.create_signed_tx(
        dysond_bin=dysond_bin,
        signer_name=tew_name,
        signer_addr=tew_addr,
        chain_id=chain_id,
        sequence=0,
        tx_data_str=dummy_tx_code,
    )

    block1_metadata = {
        "chain_id": chain_id,
        "height": 1,
        "time": "2024-01-01T00:01:00Z",
        "current_authority": tew_addr,
        "next_authority": tew_addr,
        "total_tx_count": 0,
        "instance_id": instance_id,
    }

    block1_data = {
        "prev_signed_tew_block_hash": "genesis",
        "metadata": block1_metadata,
        "pre_state": genesis_state,
        "signed_txs": [signed_tx],
        "tx_results": [],
        "post_state": genesis_state,
    }

    signed_block1 = utils.create_signed_block(
        dysond_bin=dysond_bin,
        signer_name=tew_name,
        sequence=1,
        block_data=block1_data,
    )

    # Build the block - this will process L1's message
    block1_result = utils.run_build_next_block(
        dysond_bin=dysond_bin,
        script_addr=tew_addr,
        signed_block=signed_block1,
        prev_meta=genesis_metadata,
        prev_hash="genesis_hash",
    )

    print("✓ L2 block 1 built successfully")

    # Check that L2 processed the message and created a response
    l2_state = block1_result["post_state"]["l2_queue_state"]
    print(f"L2 response queue has {len(l2_state['response_queue'])} responses")
    assert str(message_id) in l2_state["response_queue"]

    l2_response = l2_state["response_queue"][str(message_id)]
    print(f"L2 response: {l2_response['response_data']}")

    # Expected response format based on L2.on_message logic
    expected_response = (
        f"L2 computed response: Hello {user_addr}, you said '{greeting_text}'"
    )
    assert l2_response["response_data"] == expected_response

    # Now submit the L2 block to L1
    print("\n=== Step 6: Submit L2 block to L1 ===")

    # We need to create a new signed block with the actual post_state from building
    # rather than the placeholder genesis_state we used initially
    block1_data_updated = {
        "prev_signed_tew_block_hash": "genesis",
        "metadata": block1_metadata,
        "pre_state": genesis_state,
        "signed_txs": [signed_tx],
        "tx_results": block1_result["tx_results"],  # Use actual tx results
        "post_state": block1_result[
            "post_state"
        ],  # Use actual post state with L2 queue data
    }

    # Create a new signed block with the updated data
    signed_block1_updated = utils.create_signed_block(
        dysond_bin=dysond_bin,
        signer_name=tew_name,
        sequence=1,
        block_data=block1_data_updated,
    )

    # Serialize the signed block for submission
    signed_block1_json = json.dumps(signed_block1_updated)

    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        tew_addr,
        "--function-name",
        "submit_l2_block",
        "--args",
        json.dumps([signed_block1_json, instance_id]),
        "--from",
        tew_name,  # TEW operator submits the block
        "--keyring-backend",
        "test",
        "--yes",
        "--gas",
        "auto",
        "--gas-adjustment",
        "1.5",
    )
    assert exec_result.get("code", 1) == 0, f"Failed to submit L2 block: {exec_result}"

    # Extract the result - get fresh events
    events_by_type = {
        event.get("type"): event for event in exec_result.get("events", [])
    }
    exec_event = events_by_type.get("dysonprotocol.script.v1.EventExecScript")
    attrs_by_key = {
        attr.get("key"): attr.get("value") for attr in exec_event.get("attributes", [])
    }
    response_json = attrs_by_key.get("response")
    response_data = json.loads(response_json)
    result_data = json.loads(response_data.get("result", "{}"))
    result = result_data.get("result")

    print(f"✓ L2 block submitted: {result}")
    assert "L2 block processed successfully" in result

    # Verify L1 stored the response
    print("\n=== Step 7: Verify L1 stored the response ===")

    exec_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        tew_addr,
        "--function-name",
        "get_stored_responses",
        "--args",
        json.dumps([instance_id]),
        "--from",
        user_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert (
        exec_result.get("code", 1) == 0
    ), f"Failed to get stored responses: {exec_result}"

    # Extract the stored responses - get fresh events
    events_by_type = {
        event.get("type"): event for event in exec_result.get("events", [])
    }
    exec_event = events_by_type.get("dysonprotocol.script.v1.EventExecScript")
    attrs_by_key = {
        attr.get("key"): attr.get("value") for attr in exec_event.get("attributes", [])
    }
    response_json = attrs_by_key.get("response")
    response_data = json.loads(response_json)
    result_data = json.loads(response_data.get("result", "{}"))
    result = result_data.get("result")

    print(f"Stored responses: {result}")
    assert result["total_responses"] == 1
    assert str(message_id) in result["stored_responses"]
    assert result["stored_responses"][str(message_id)] == expected_response

    # Final verification: L1 should have removed the message from outgoing_queue
    query_result = dysond_bin(
        "query",
        "storage",
        "get",
        tew_addr,
        "--index",
        f"tew/{instance_id}/l1",
    )
    final_l1_state = json.loads(query_result["entry"]["data"])
    assert (
        str(message_id) not in final_l1_state["outgoing_queue"]
    ), "Message should be removed after acknowledgment"
    print("✓ L1 removed acknowledged message from outgoing queue")

    print("\n🎉 E2E Test Complete!")
    print(f"  - User ({user_addr}) sent: '{greeting_text}'")
    print(f"  - L2 computed: '{expected_response}'")
    print(f"  - L1 stored response with ID {message_id}")
    print("  - Message properly acknowledged and cleaned up")
