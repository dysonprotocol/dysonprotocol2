import json
import tempfile


def create_signed_tx(
    dysond_bin, signer_name, signer_addr, chain_id, sequence, tx_data_str
):
    """
    Creates and signs a Tew transaction offline.
    """
    tx_data = {
        "chain_id": chain_id,
        "sequence": sequence,
        "data": tx_data_str,
    }

    tx_body_msg = {"signer": signer_addr, "data": tx_data}

    tx_for_signing = {
        "body": {
            "messages": [
                {
                    "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                    "signer": signer_addr,
                    "data": json.dumps(tx_body_msg),
                    "app_domain": "tew/tx",
                }
            ],
            "memo": "",
        },
        "auth_info": {"signer_infos": [], "fee": {"amount": [], "gas_limit": "0"}},
        "signatures": [],
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tx_file, tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as signed_tx_file:

        json.dump(tx_for_signing, tx_file)
        tx_file.flush()

        # Capture the result of the signing command
        sign_result = dysond_bin(
            "tx",
            "sign",
            tx_file.name,
            "--from",
            signer_name,
            "--chain-id",
            "",
            "--account-number",
            "0",
            "--sequence",
            str(sequence),
            "--offline",
            "--output-document",
            signed_tx_file.name,
            "--keyring-backend",
            "test",
        )

        # Check if the signing command failed (if it's a dict with code field)
        if isinstance(sign_result, dict) and sign_result.get("code", 0) != 0:
            raise Exception(f"Failed to sign transaction: {sign_result}")

        # Check if the output file has content
        with open(signed_tx_file.name, "r") as f:
            content = f.read().strip()
            if not content:
                raise Exception("Signing produced empty output file")

            # Parse the JSON content
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                raise Exception(
                    f"Failed to parse signed tx JSON: {e}. Content: {content[:200]}"
                )


def create_signed_block(dysond_bin, signer_name, sequence, block_data):
    """
    Creates and signs a Tew block offline.
    """
    block_body_msg = {
        "signer": block_data["metadata"]["current_authority"],
        "data": block_data,
    }

    block_for_signing = {
        "body": {
            "messages": [
                {
                    "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                    "signer": block_data["metadata"]["current_authority"],
                    "data": json.dumps(block_body_msg),
                    "app_domain": "tew/block",
                }
            ],
            "memo": "",
        },
        "auth_info": {"signer_infos": [], "fee": {"amount": [], "gas_limit": "0"}},
        "signatures": [],
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as block_file, tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as signed_block_file:
        json.dump(block_for_signing, block_file)
        block_file.flush()

        # Capture the result of the signing command
        sign_result = dysond_bin(
            "tx",
            "sign",
            block_file.name,
            "--from",
            signer_name,
            "--chain-id",
            "",
            "--account-number",
            "0",
            "--sequence",
            str(sequence),
            "--offline",
            "--output-document",
            signed_block_file.name,
            "--keyring-backend",
            "test",
        )

        # Check if the signing command failed (if it's a dict with code field)
        if isinstance(sign_result, dict) and sign_result.get("code", 0) != 0:
            raise Exception(f"Failed to sign block: {sign_result}")

        # Check if the output file has content
        with open(signed_block_file.name, "r") as f:
            content = f.read().strip()
            if not content:
                raise Exception("Signing produced empty output file")

            # Parse the JSON content
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                raise Exception(
                    f"Failed to parse signed block JSON: {e}. Content: {content[:200]}"
                )


def run_build_next_block(dysond_bin, script_addr, signed_block, prev_meta, prev_hash):
    """
    Runs the build_next_block function on the script and returns the result.
    """
    args = [signed_block, prev_meta, prev_hash]
    result = dysond_bin(
        "query",
        "script",
        "run",
        "--executor-address",
        script_addr,
        "--script-address",
        script_addr,
        "--function-name",
        "build_next_block",
        "--args",
        json.dumps(args),
        "--kwargs",
        "{}",
        "-o",
        "json",
    )

    assert (
        result.get("exception") is None
    ), f"Script execution failed: {result.get('exception')}\nStdout: {result.get('stdout')}\nFull result: {json.dumps(result, indent=2)}"
    assert "result" in result, f"Query result missing 'result' field: {result}"
    assert isinstance(
        result["result"], str
    ), f"Expected 'result' to be a JSON string, but got {type(result['result'])}: {result['result']}"

    result_data = json.loads(result["result"])
    assert "result" in result_data, f"Result data missing 'result' field: {result_data}"

    return result_data["result"]


def initialize_test_l1_l2(
    dysond_bin, l1_operator_name, l1_operator_addr, instance_id="test", chain_id=None
):
    """
    Initialize L1 and optionally L2 genesis for tests.

    Args:
        dysond_bin: The dysond binary function
        l1_operator_name: Name of the L1 operator account
        l1_operator_addr: Address of the L1 operator account
        instance_id: Instance ID for the L1/L2 pair (default: "test")
        chain_id: Chain ID for L2 (default: "tew-{instance_id}")

    Returns:
        dict: L1 state data that was initialized
    """
    # Initialize L1
    init_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        l1_operator_addr,
        "--function-name",
        "initialize_l1",
        "--args",
        json.dumps([instance_id]),
        "--from",
        l1_operator_name,
        "--gas",
        "auto",
        "--gas-adjustment",
        "1.5",
    )
    assert init_result.get("code", 1) == 0, f"Failed to initialize L1: {init_result}"

    # Query the L1 state to return it
    storage_result = dysond_bin(
        "query", "storage", "get", l1_operator_addr, "--index", f"tew/{instance_id}/l1"
    )

    assert isinstance(
        storage_result, dict
    ), f"L1 storage query failed: {storage_result}"
    assert "entry" in storage_result, f"L1 storage missing entry: {storage_result}"

    l1_data = json.loads(storage_result["entry"]["data"])

    # Optionally initialize L2 genesis if chain_id is provided
    if chain_id:
        init_l2_result = dysond_bin(
            "tx",
            "script",
            "exec",
            "--script-address",
            l1_operator_addr,
            "--function-name",
            "initialize_l2_genesis",
            "--args",
            json.dumps([instance_id, chain_id, l1_operator_addr]),
            "--from",
            l1_operator_name,
            "--gas",
            "auto",
            "--gas-adjustment",
            "1.5",
        )
        assert (
            init_l2_result.get("code", 1) == 0
        ), f"Failed to initialize L2 genesis: {init_l2_result}"

    return l1_data


def create_l2_genesis_block_with_l1(
    l1_operator_addr, l1_data, instance_id="test", l2_state_override=None
):
    """
    Create an L2 genesis block that properly references L1 state.

    Args:
        l1_operator_addr: Address of the L1 operator/authority
        l1_data: The L1 state data (from storage or initialization)
        instance_id: Instance ID for the L1/L2 pair
        l2_state_override: Optional L2 state to use instead of default

    Returns:
        dict: Genesis block data
    """
    # Default L2 state if not provided
    if l2_state_override is None:
        l2_state = {
            "queue_metadata": {"next_message_id": 0},
            "outgoing_queue": {},
            "response_queue": {},
            "current_height": 0,
            "processed_messages": {},
        }
    else:
        l2_state = l2_state_override

    genesis_block_data = {
        "prev_signed_tew_block_hash": "genesis",
        "metadata": {
            "chain_id": f"tew-{instance_id}",
            "height": 0,
            "time": "2024-01-01T00:00:00Z",
            "current_authority": l1_operator_addr,
            "next_authority": l1_operator_addr,
            "total_tx_count": 0,
            "instance_id": instance_id,
        },
        "pre_state": {
            "accounts_by_number": {
                "0": {"address": l1_operator_addr, "account_number": 0, "sequence": 0}
            },
            "account_numbers_by_address": {l1_operator_addr: 0},
            "next_account_number": 1,
            "l1_queue_state": l1_data,  # Use the actual L1 state
            "l2_queue_state": l2_state,
        },
        "signed_txs": [],
        "tx_results": [],
        "post_state": {
            "accounts_by_number": {
                "0": {"address": l1_operator_addr, "account_number": 0, "sequence": 0}
            },
            "account_numbers_by_address": {l1_operator_addr: 0},
            "next_account_number": 1,
            "l1_queue_state": l1_data,  # Use the actual L1 state
            "l2_queue_state": l2_state,
        },
    }

    return genesis_block_data
