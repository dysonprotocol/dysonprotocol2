"""
Test L2 block submission to L1 - New architecture.

This test validates that L2 blocks can be submitted to L1 by anyone,
and L1 properly processes them in message sequence order.
"""

import json
from pathlib import Path
import pytest

from tests.tew import utils


def test_submit_l2_block_basic(chainnet, generate_account, faucet):
    """Test basic L2 block submission to L1."""
    dysond_bin = chainnet[0]

    # Create accounts
    l1_operator_name, l1_operator_addr = generate_account(
        "l1_op", faucet_amount=1000000
    )
    submitter_name, submitter_addr = generate_account(
        "submitter", faucet_amount=1000000
    )

    # Read and upload queue_chain.py
    project_root = Path(__file__).parent.parent.parent
    queue_chain_path = project_root / "demo-tew" / "queue_chain.py"

    print(f"\n=== Step 1: Upload queue_chain.py ({queue_chain_path}) ===")
    # Upload as L1 operator using --code-path to avoid shell escaping issues
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code-path",
        str(queue_chain_path),
        "--from",
        l1_operator_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # === Step 1: Initialize L1 and send message to L2 ===
    print("\n### Step 1: Initialize L1 and send message to L2 ###")

    # Initialize L1 state first
    init_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "initialize_l1",
        "--args",
        json.dumps(["test_instance"]),
        "--from",
        l1_operator_name,
    )
    assert init_result.get("code", 1) == 0, f"Failed to initialize L1: {init_result}"
    print("✓ L1 initialized")

    # Now send the greeting
    greeting_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "say_hi",
        "--args",
        json.dumps(["Hello from L1!", "test_instance"]),
        "--from",
        l1_operator_name,
    )
    assert (
        greeting_result.get("code", 1) == 0
    ), f"Failed to send message to L2: {greeting_result}"
    print("✓ L1 sent message to L2")

    # Verify L1 state has the message
    l1_state_result = dysond_bin(
        "query",
        "script",
        "run",
        "--executor-address",
        l1_operator_addr,
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "get_stored_responses",
        "--args",
        json.dumps(["test_instance"]),
    )

    # Extract L1 state - query result is a direct dictionary with "result" field
    result_str = l1_state_result["result"]
    parsed_result = json.loads(result_str)
    l1_state = parsed_result["result"]

    print(f"L1 state after sending: {json.dumps(l1_state, indent=2)}")
    # get_stored_responses returns stored_responses and total_responses
    assert "stored_responses" in l1_state
    assert "total_responses" in l1_state
    assert l1_state["total_responses"] == 0, "Should have no responses yet"

    # We need to check L1 storage directly to verify the message was sent
    # Query L1 storage to see the outgoing queue
    storage_result = dysond_bin(
        "query", "storage", "get", l1_operator_addr, "--index", "tew/test_instance/l1"
    )

    # Check if storage exists - it returns a dict with 'entry' if it exists, or a string error if not
    assert isinstance(
        storage_result, dict
    ), f"L1 storage should exist after say_hi, got: {storage_result}"
    assert (
        "entry" in storage_result
    ), f"Expected 'entry' field in storage result: {storage_result}"

    l1_data = json.loads(storage_result["entry"]["data"])
    print(f"L1 storage data: {json.dumps(l1_data, indent=2)}")
    assert len(l1_data["outgoing_queue"]) == 1
    assert (
        l1_data["queue_metadata"]["next_l2_message_id"] == 0
    ), "Should expect message 0 from L2"

    # === Step 2: Build L2 block that processes the message ===
    print("\n### Step 2: Build L2 block with response ###")

    # Create genesis block data for L2
    genesis_block_data = {
        "prev_signed_tew_block_hash": "genesis",
        "metadata": {
            "chain_id": "tew-test_instance",
            "height": 0,
            "time": "2024-01-01T00:00:00Z",
            "current_authority": l1_operator_addr,
            "next_authority": l1_operator_addr,
            "total_tx_count": 0,
            "instance_id": "test_instance",
        },
        "pre_state": {
            "accounts_by_number": {
                "0": {"address": l1_operator_addr, "account_number": 0, "sequence": 0}
            },
            "account_numbers_by_address": {l1_operator_addr: 0},
            "next_account_number": 1,
            "l1_queue_state": {
                "queue_metadata": {"next_message_id": 1, "next_l2_message_id": 0},
                "outgoing_queue": {
                    "0": {
                        "msg_id": 0,
                        "message_data": f"{l1_operator_addr} says hi: Hello from L1!",
                    }
                },
                "response_queue": {},
                "stored_responses": {},
            },
            "l2_queue_state": None,
        },
        "signed_txs": [],
        "tx_results": [],
        "post_state": {
            "accounts_by_number": {
                "0": {"address": l1_operator_addr, "account_number": 0, "sequence": 0}
            },
            "account_numbers_by_address": {l1_operator_addr: 0},
            "next_account_number": 1,
            "l1_queue_state": {
                "queue_metadata": {"next_message_id": 1, "next_l2_message_id": 0},
                "outgoing_queue": {
                    "0": {
                        "msg_id": 0,
                        "message_data": f"{l1_operator_addr} says hi: Hello from L1!",
                    }
                },
                "response_queue": {},
                "stored_responses": {},
            },
            "l2_queue_state": None,
        },
    }

    # Create a properly signed genesis block
    genesis_signed_block = utils.create_signed_block(
        dysond_bin,
        l1_operator_name,
        0,  # sequence for genesis block
        genesis_block_data,
    )

    # Build next L2 block via query (this processes the L1 message)
    block_result = utils.run_build_next_block(
        dysond_bin=dysond_bin,
        script_addr=l1_operator_addr,
        signed_block=genesis_signed_block,  # Pass as dict, not JSON string
        prev_meta=None,
        prev_hash="genesis_hash",
    )

    print(f"L2 block built at height: {block_result['metadata']['height']}")

    # Extract L2 state to verify it has a response
    l2_state = block_result["post_state"]["l2_queue_state"]
    print(
        f"L2 response queue: {json.dumps(l2_state.get('response_queue', {}), indent=2)}"
    )
    assert (
        len(l2_state["response_queue"]) == 1
    ), f"L2 should have generated a response, block_result: {json.dumps(block_result, indent=2)}"
    assert "0" in l2_state["response_queue"], "Response for message 0 should exist"

    # Create a signed L2 block from the block result
    signed_l2_block = utils.create_signed_block(
        dysond_bin=dysond_bin,
        signer_name=l1_operator_name,
        sequence=2,  # sequence incremented for signing
        block_data=block_result,
    )

    # === Step 3: Submit L2 block to L1 (by different account) ===
    print("\n### Step 3: Submit L2 block to L1 ###")

    submit_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "submit_l2_block",
        "--args",
        json.dumps([json.dumps(signed_l2_block), "test_instance"]),
        "--from",
        submitter_name,  # Different account submitting!
    )
    assert (
        submit_result.get("code", 1) == 0
    ), f"Failed to submit L2 block: {submit_result}"

    # Extract result from events
    exec_events = [
        e
        for e in submit_result.get("events", [])
        if e["type"] == "dysonprotocol.script.v1.EventExecScript"
    ]
    assert (
        len(exec_events) > 0
    ), f"No EventExecScript found in events: {submit_result.get('events', [])}"

    event_dict = {
        e.get("type"): {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in exec_events
    }
    response_attr = event_dict["dysonprotocol.script.v1.EventExecScript"]["response"]
    response_data = json.loads(response_attr)
    result_str = response_data["result"]
    result_parsed = json.loads(result_str)
    result = result_parsed["result"]

    print(f"Submit result: {result}")
    assert "successfully" in result, f"Block submission failed: {result}"

    # === Step 4: Verify L1 processed the response ===
    print("\n### Step 4: Verify L1 processed L2 response ###")

    # Query L1 storage directly to check the full state
    final_storage_result = dysond_bin(
        "query", "storage", "get", l1_operator_addr, "--index", "tew/test_instance/l1"
    )

    # Check if storage exists
    assert isinstance(
        final_storage_result, dict
    ), f"L1 storage should exist after submit_l2_block, got: {final_storage_result}"
    assert (
        "entry" in final_storage_result
    ), f"Expected 'entry' field in storage result: {final_storage_result}"

    final_l1_data = json.loads(final_storage_result["entry"]["data"])
    print(f"Final L1 storage data: {json.dumps(final_l1_data, indent=2)}")

    # Verify the response was stored
    assert "stored_responses" in final_l1_data
    assert len(final_l1_data["stored_responses"]) == 1
    assert "0" in final_l1_data["stored_responses"]
    actual_response = final_l1_data["stored_responses"]["0"]
    print(f"✓ L1 received and stored response: {actual_response}")

    # Verify message was removed from outgoing queue
    assert (
        len(final_l1_data["outgoing_queue"]) == 0
    ), "Message should be removed after response"
    assert (
        final_l1_data["queue_metadata"]["next_l2_message_id"] == 0
    ), "Should still expect message 0 from L2 (no new messages sent)"

    print("\n🎉 L2 block submission test passed!")
    print("  - L1 sent message to L2")
    print("  - L2 processed message and created response")
    print("  - Different account submitted L2 block to L1")
    print("  - L1 successfully processed the L2 block and stored response")


def test_submit_l2_block_sequence_enforcement(chainnet, generate_account, faucet):
    """Test that L1 only processes L2 messages in sequence."""
    dysond_bin = chainnet[0]

    # Create accounts
    l1_operator_name, l1_operator_addr = generate_account(
        "l1_op", faucet_amount=1000000
    )

    # Upload queue_chain.py
    project_root = Path(__file__).parent.parent.parent
    queue_chain_path = project_root / "demo-tew" / "queue_chain.py"

    # Use --code-path to avoid shell escaping issues
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code-path",
        str(queue_chain_path),
        "--from",
        l1_operator_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # === Step 1: Initialize L1 first ===
    print("\n### Step 1: Initialize L1 state ###")

    # Initialize L1 state - this is required before L2 can build blocks
    l1_data = utils.initialize_test_l1_l2(
        dysond_bin=dysond_bin,
        l1_operator_name=l1_operator_name,
        l1_operator_addr=l1_operator_addr,
        instance_id="seq_test",
    )
    print("✓ L1 initialized")

    # === Step 2: Create L2 block with message ID 1 (skipping 0) ===
    print("\n### Step 2: Create L2 block with out-of-sequence message ###")

    # Create L2 state with message 1 (skipping message 0)
    l2_state_with_gap = {
        "queue_metadata": {"next_message_id": 2},  # Already sent 0 and 1
        "outgoing_queue": {
            "1": {
                "msg_id": 1,
                "message_data": "Second L2 message",
            }  # Skipping message 0
        },
        "response_queue": {},
        "current_height": 0,
        "processed_messages": {},
    }

    # Create genesis block data with L1 reference and L2 having message 1 (not 0)
    genesis_block_data = utils.create_l2_genesis_block_with_l1(
        l1_operator_addr=l1_operator_addr,
        l1_data=l1_data,
        instance_id="seq_test",
        l2_state_override=l2_state_with_gap,
    )

    # Create a properly signed genesis block
    genesis_signed_block = utils.create_signed_block(
        dysond_bin,
        l1_operator_name,
        0,  # sequence for genesis block
        genesis_block_data,
    )

    block_result = utils.run_build_next_block(
        dysond_bin=dysond_bin,
        script_addr=l1_operator_addr,
        signed_block=genesis_signed_block,  # Pass as dict, not JSON string
        prev_meta=None,
        prev_hash="genesis_hash",
    )

    signed_l2_block = utils.create_signed_block(
        dysond_bin=dysond_bin,
        signer_name=l1_operator_name,
        sequence=1,
        block_data=block_result,
    )

    # === Step 3: Submit block with out-of-sequence message ===
    print("\n### Step 3: Submit L2 block to L1 ###")

    # Now submit the block
    submit_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "submit_l2_block",
        "--args",
        json.dumps([json.dumps(signed_l2_block), "seq_test"]),
        "--from",
        l1_operator_name,
    )
    assert submit_result.get("code", 1) == 0

    # Extract result from events
    exec_events = [
        e
        for e in submit_result.get("events", [])
        if e["type"] == "dysonprotocol.script.v1.EventExecScript"
    ]
    assert (
        len(exec_events) > 0
    ), f"No EventExecScript found in events: {submit_result.get('events', [])}"

    event_dict = {
        e.get("type"): {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in exec_events
    }
    response_attr = event_dict["dysonprotocol.script.v1.EventExecScript"]["response"]

    response_data = json.loads(response_attr)
    result_str = response_data["result"]
    result_parsed = json.loads(result_str)
    result = result_parsed["result"]

    print(f"Submit result: {result}")
    assert "not processed" in result, "Block should not be processed without message 0"

    # === Step 4: Create and submit block with message 0 ===
    print("\n### Step 4: Create L2 block with message 0 ###")

    # Build another block with message 0
    prev_metadata = block_result["metadata"]

    # Create a new block that adds message 0
    new_l2_state = block_result["post_state"]["l2_queue_state"].copy()
    new_l2_state["outgoing_queue"]["0"] = {
        "msg_id": 0,
        "message_data": "First L2 message",
    }

    # Create block data for the second block
    block2_data = {
        "metadata": {
            "chain_id": "tew-seq_test",
            "height": 1,
            "time": "2024-01-01T00:01:00Z",
            "current_authority": l1_operator_addr,
            "next_authority": l1_operator_addr,
            "total_tx_count": 0,
        },
        "pre_state": block_result["post_state"],
        "signed_txs": [],
        "tx_results": [],
        "post_state": {**block_result["post_state"], "l2_queue_state": new_l2_state},
    }

    signed_l2_block2 = utils.create_signed_block(
        dysond_bin=dysond_bin,
        signer_name=l1_operator_name,
        sequence=2,
        block_data=block2_data,
    )

    # === Step 5: Submit block with message 0 - should process both ===
    print("\n### Step 5: Submit L2 block with message 0 ###")

    submit_result2 = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "submit_l2_block",
        "--args",
        json.dumps([json.dumps(signed_l2_block2), "seq_test"]),
        "--from",
        l1_operator_name,
    )
    assert submit_result2.get("code", 1) == 0

    # Extract result from events
    exec_events = [
        e
        for e in submit_result2.get("events", [])
        if e["type"] == "dysonprotocol.script.v1.EventExecScript"
    ]
    assert (
        len(exec_events) > 0
    ), f"No EventExecScript found in events: {submit_result2.get('events', [])}"

    event_dict = {
        e.get("type"): {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in exec_events
    }
    response_attr = event_dict["dysonprotocol.script.v1.EventExecScript"]["response"]
    response_data = json.loads(response_attr)
    result_str = response_data["result"]
    result_parsed = json.loads(result_str)
    result = result_parsed["result"]

    print(f"Submit result: {result}")
    assert "successfully" in result, "Block should be processed with message 0"

    # === Step 6: Verify L1 processed both messages in order ===
    print("\n### Step 6: Verify L1 state ###")

    # Query L1 storage to check next_l2_message_id
    storage_result = dysond_bin(
        "query", "storage", "get", l1_operator_addr, "--index", "tew/seq_test/l1"
    )

    # Check if storage exists
    assert isinstance(
        storage_result, dict
    ), f"L1 storage should exist after processing blocks, got: {storage_result}"
    assert (
        "entry" in storage_result
    ), f"Expected 'entry' field in storage result: {storage_result}"

    l1_data = json.loads(storage_result["entry"]["data"])
    print(f"L1 next_l2_message_id: {l1_data['queue_metadata']['next_l2_message_id']}")
    assert (
        l1_data["queue_metadata"]["next_l2_message_id"] == 2
    ), "L1 should have processed messages 0 and 1"

    print("\n🎉 Sequence enforcement test passed!")
    print("  - L1 rejected out-of-sequence message")
    print("  - L1 processed messages 0 and 1 when both were available")


def test_multiple_submitters(chainnet, generate_account, faucet):
    """Test that multiple accounts can submit the same L2 block."""
    dysond_bin = chainnet[0]

    # Create accounts
    l1_operator_name, l1_operator_addr = generate_account(
        "l1_op", faucet_amount=1000000
    )
    submitter1_name, submitter1_addr = generate_account("sub1", faucet_amount=1000000)
    submitter2_name, submitter2_addr = generate_account("sub2", faucet_amount=1000000)

    # Upload queue_chain.py
    project_root = Path(__file__).parent.parent.parent
    queue_chain_path = project_root / "demo-tew" / "queue_chain.py"

    # Use --code-path to avoid shell escaping issues
    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code-path",
        str(queue_chain_path),
        "--from",
        l1_operator_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert update_result.get("code", 1) == 0

    # === First Initialize L1 ===
    print("\n### Initialize L1 first ###")

    # Initialize L1 state - this is required before L2 can build blocks
    l1_data = utils.initialize_test_l1_l2(
        dysond_bin=dysond_bin,
        l1_operator_name=l1_operator_name,
        l1_operator_addr=l1_operator_addr,
        instance_id="multi_test",
    )
    print("✓ L1 initialized")

    # Create L2 state with a message
    l2_state = {
        "queue_metadata": {"next_message_id": 1},
        "outgoing_queue": {"0": {"msg_id": 0, "message_data": "Message from L2"}},
        "response_queue": {},
        "current_height": 0,
        "processed_messages": {},
    }

    # Create L2 genesis block that references L1
    genesis_block_data = utils.create_l2_genesis_block_with_l1(
        l1_operator_addr=l1_operator_addr,
        l1_data=l1_data,
        instance_id="multi_test",
        l2_state_override=l2_state,
    )

    # Create a properly signed genesis block
    genesis_signed_block = utils.create_signed_block(
        dysond_bin,
        l1_operator_name,
        0,  # sequence for genesis block
        genesis_block_data,
    )

    block_result = utils.run_build_next_block(
        dysond_bin=dysond_bin,
        script_addr=l1_operator_addr,
        signed_block=genesis_signed_block,  # Pass as dict, not JSON string
        prev_meta=None,
        prev_hash="genesis_hash",
    )

    signed_l2_block = utils.create_signed_block(
        dysond_bin=dysond_bin,
        signer_name=l1_operator_name,
        sequence=1,
        block_data=block_result,
    )

    # === First submitter submits the L2 block ===
    print("\n### First submitter submits L2 block ###")

    # First submission
    submit1_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "submit_l2_block",
        "--args",
        json.dumps([json.dumps(signed_l2_block), "multi_test"]),
        "--from",
        submitter1_name,
    )
    assert submit1_result.get("code", 1) == 0
    print("✓ First submission successful")

    # === Second submitter submits the same block ===
    print("\n### Second submitter submits same L2 block ###")

    submit2_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "submit_l2_block",
        "--args",
        json.dumps([json.dumps(signed_l2_block), "multi_test"]),
        "--from",
        submitter2_name,
    )
    assert submit2_result.get("code", 1) == 0

    # Extract result from events
    exec_events = [
        e
        for e in submit2_result.get("events", [])
        if e["type"] == "dysonprotocol.script.v1.EventExecScript"
    ]
    assert (
        len(exec_events) > 0
    ), f"No EventExecScript found in events: {submit2_result.get('events', [])}"

    event_dict = {
        e.get("type"): {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in exec_events
    }
    response_attr = event_dict["dysonprotocol.script.v1.EventExecScript"]["response"]
    response_data = json.loads(response_attr)
    result_str = response_data["result"]
    result_parsed = json.loads(result_str)
    result = result_parsed["result"]

    print(f"Second submit result: {result}")
    assert (
        "not processed" in result
    ), "Second submission should not reprocess same messages"

    print("\n🎉 Multiple submitters test passed!")
    print("  - First submitter processed the block")
    print("  - Second submitter's submission was accepted but not reprocessed")
