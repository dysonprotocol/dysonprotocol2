"""
State Channel Test Utilities - PBI-40

Provides helpers for creating properly signed attestations using ADR-36 signatures.
"""

import json
import tempfile
from pathlib import Path
from deep_parse import deep_parse


# Path to the state channel script
SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "examples" / "state_channels" / "script.py"
)


def get_script_code() -> str:
    """Load the state channel script source code."""
    return SCRIPT_PATH.read_text()


def _assert_script_result(query_result: dict, context: str) -> dict:
    """
    Validate and extract result from script query response.
    Raises AssertionError with helpful context on any failure.

    Args:
        query_result: Raw result from dysond query script run
        context: Description of what operation was being performed

    Returns:
        The actual result value from the script execution
    """
    assert isinstance(query_result, dict), (
        f"{context}: Expected dict, got {type(query_result).__name__}. "
        f"Value: {query_result!r}"
    )

    assert (
        query_result.get("exception") is None
    ), f"{context}: Script raised exception: {query_result.get('exception')}"

    parsed = deep_parse(query_result)

    assert isinstance(parsed, dict), (
        f"{context}: deep_parse returned {type(parsed).__name__}, expected dict. "
        f"Raw: {query_result!r}"
    )

    assert "result" in parsed, (
        f"{context}: Missing 'result' key in parsed response. "
        f"Keys: {list(parsed.keys())}. Full: {json.dumps(parsed, indent=2)}"
    )

    outer_result = parsed["result"]
    assert isinstance(outer_result, dict), (
        f"{context}: parsed['result'] is {type(outer_result).__name__}, expected dict. "
        f"Value: {outer_result!r}"
    )

    assert "result" in outer_result, (
        f"{context}: Missing 'result' key in parsed['result']. "
        f"Keys: {list(outer_result.keys())}. Full: {json.dumps(outer_result, indent=2)}"
    )

    return outer_result["result"]


def create_signed_attestation(
    dysond_bin,
    attester_name: str,
    attester_addr: str,
    accused: str,
    channel_id: str,
    step_number: int,
) -> dict:
    """
    Create a properly ADR-36 signed non-participation attestation.

    Args:
        dysond_bin: The dysond binary function
        attester_name: Keyring name of the attester
        attester_addr: Address of the attester
        accused: Address of the accused (non-participating) participant
        channel_id: Channel ID
        step_number: Step number where non-participation occurred

    Returns:
        dict: {
            "attester": str,
            "accused": str,
            "channel_id": str,
            "step_number": int,
            "attestation_hash": str,  # Computed by script
            "timestamp": int,
            "signed_tx": dict,  # Full signed ADR-36 tx for verification
        }
    """
    # Create attestation data
    attestation_data = {
        "type": "non_participation_attestation",
        "attester": attester_addr,
        "accused": accused,
        "channel_id": channel_id,
        "step_number": step_number,
    }

    # Create ADR-36 compliant MsgArbitraryData
    tx_for_signing = {
        "body": {
            "messages": [
                {
                    "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                    "signer": attester_addr,
                    "data": json.dumps(attestation_data),
                    "app_domain": "state_channel/attestation/v1",
                    "metadata": "{}",
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

        # Sign offline with ADR-36 parameters
        dysond_bin(
            "tx",
            "sign",
            tx_file.name,
            "--from",
            attester_name,
            "--chain-id",
            "",
            "--account-number",
            "0",
            "--sequence",
            "0",
            "--offline",
            "--output-document",
            signed_tx_file.name,
            "--keyring-backend",
            "test",
        )

        # Read signed transaction
        with open(signed_tx_file.name, "r") as f:
            content = f.read().strip()
            assert content, (
                f"Signed tx file is empty for attester={attester_name}, "
                f"accused={accused}, channel={channel_id}, step={step_number}"
            )
            signed_tx = json.loads(content)

    # Compute attestation hash on-chain for consistency
    gov_result = dysond_bin("query", "auth", "module-account", "gov")
    assert isinstance(
        gov_result, dict
    ), f"gov query returned {type(gov_result)}: {gov_result}"
    assert "account" in gov_result, f"gov query missing 'account': {gov_result}"
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def compute_att_hash():
    return make_attestation_hash("{attester_addr}", "{accused}", "{channel_id}", {step_number})
"""
    )

    query_result = dysond_bin(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "compute_att_hash",
        "--extra-code",
        extra_code,
    )

    attestation_hash = _assert_script_result(
        query_result,
        f"compute_att_hash(attester={attester_addr}, accused={accused}, channel={channel_id}, step={step_number})",
    )

    assert isinstance(
        attestation_hash, str
    ), f"attestation_hash should be str, got {type(attestation_hash)}: {attestation_hash}"
    assert (
        len(attestation_hash) == 64
    ), f"attestation_hash should be 64-char hex, got {len(attestation_hash)}: {attestation_hash}"

    return {
        "attester": attester_addr,
        "accused": accused,
        "channel_id": channel_id,
        "step_number": step_number,
        "attestation_hash": attestation_hash,
        "timestamp": 0,  # Will be set by block info
        "signed_tx": signed_tx,
    }


def create_channel_address_proof(
    dysond_bin,
    channel_address_name: str,
    channel_address: str,
    participant_address: str,
    channel_id: str,
) -> str:
    """
    Create a signed MsgArbitraryData proof from channel_address authorizing
    it to sign on behalf of participant_address for the given channel.

    The proof data is JSON: {"participant": participant_address, "channel_id": channel_id}
    This proves:
    1. Control - The caller has the channel_address private key
    2. Intent - channel_address specifically authorizes this binding

    Args:
        dysond_bin: The dysond binary function
        channel_address_name: Keyring name for the channel_address (hot wallet)
        channel_address: Address of the hot wallet
        participant_address: Address of the main participant (Keplr wallet)
        channel_id: Channel ID being joined

    Returns:
        JSON string of the signed transaction (for passing to agree_to_channel)
    """
    # Create the proof data
    proof_data = {
        "participant": participant_address,
        "channel_id": channel_id,
    }

    # Create ADR-36 compliant MsgArbitraryData
    tx_for_signing = {
        "body": {
            "messages": [
                {
                    "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                    "signer": channel_address,
                    "data": json.dumps(proof_data),
                    "app_domain": "state_channel/channel_address_proof/v1",
                    "metadata": "{}",
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

        # Sign offline with ADR-36 parameters
        dysond_bin(
            "tx",
            "sign",
            tx_file.name,
            "--from",
            channel_address_name,
            "--chain-id",
            "",
            "--account-number",
            "0",
            "--sequence",
            "0",
            "--offline",
            "--output-document",
            signed_tx_file.name,
            "--keyring-backend",
            "test",
        )

        # Read signed transaction
        with open(signed_tx_file.name, "r") as f:
            content = f.read().strip()
            assert content, (
                f"Signed tx file is empty for channel_address={channel_address_name}, "
                f"participant={participant_address}, channel={channel_id}"
            )

    return content


def create_channel_with_real_participants(
    dysond_bin,
    participant_accounts: list,
    channel_id: str,
    computation_script: str = "pass",
    initial_state: dict = None,
    escrow_per_participant: int = 100,
    total_steps: int = 10,
) -> dict:
    """
    Create a channel configuration with real participant addresses.

    Args:
        dysond_bin: The dysond binary function
        participant_accounts: List of (name, address) tuples for participants
        channel_id: Unique channel ID
        computation_script: Python code to execute each step
        initial_state: Initial state dict
        escrow_per_participant: Escrow amount per participant
        total_steps: Total number of steps

    Returns:
        dict with channel configuration details
    """
    gov_result = dysond_bin("query", "auth", "module-account", "gov")
    assert isinstance(
        gov_result, dict
    ), f"gov query returned {type(gov_result)}: {gov_result}"
    assert "account" in gov_result, f"gov query missing 'account': {gov_result}"
    gov_addr = gov_result["account"]["value"]["address"]

    participants = [acc[1] for acc in participant_accounts]
    created_by = participants[0]

    script_code = get_script_code()
    participants_json = json.dumps(participants)
    initial_state_json = json.dumps(initial_state or {})

    extra_code = (
        script_code
        + f"""

def create_test_channel():
    config = make_channel_config(
        channel_id="{channel_id}",
        participants={participants_json},
        computation_script='''{computation_script}''',
        initial_state={initial_state_json},
        escrow_per_participant={escrow_per_participant},
        total_steps={total_steps},
        created_by="{created_by}",
    )
    set_config("{channel_id}", config)
    
    # Initialize participant records
    for addr in {participants_json}:
        participant = make_participant_record(
            address=addr,
            escrow_balance={escrow_per_participant},
        )
        set_participant("{channel_id}", addr, participant)
    
    return {{
        "channel_id": "{channel_id}",
        "participants": {participants_json},
        "quorum": config["quorum"],
    }}
"""
    )

    query_result = dysond_bin(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "create_test_channel",
        "--extra-code",
        extra_code,
    )

    result = _assert_script_result(
        query_result,
        f"create_test_channel(channel_id={channel_id}, participants={participants})",
    )

    assert isinstance(
        result, dict
    ), f"create_test_channel should return dict, got {type(result)}: {result}"
    assert (
        "channel_id" in result
    ), f"create_test_channel result missing 'channel_id'. Keys: {list(result.keys())}"
    assert (
        "participants" in result
    ), f"create_test_channel result missing 'participants'. Keys: {list(result.keys())}"
    assert (
        "quorum" in result
    ), f"create_test_channel result missing 'quorum'. Keys: {list(result.keys())}"

    return result


def cleanup_channel(dysond_bin, channel_id: str, participants: list) -> None:
    """
    Clean up channel storage after test.
    """
    gov_result = dysond_bin("query", "auth", "module-account", "gov")
    assert isinstance(
        gov_result, dict
    ), f"gov query returned {type(gov_result)}: {gov_result}"
    assert "account" in gov_result, f"gov query missing 'account': {gov_result}"
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    participants_json = json.dumps(participants)

    extra_code = (
        script_code
        + f"""

def cleanup_test_channel():
    _storage_delete(config_key("{channel_id}"))
    _storage_delete(state_key("{channel_id}"))
    for addr in {participants_json}:
        _storage_delete(participant_key("{channel_id}", addr))
    return "cleaned"
"""
    )

    query_result = dysond_bin(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "cleanup_test_channel",
        "--extra-code",
        extra_code,
    )

    result = _assert_script_result(
        query_result, f"cleanup_test_channel(channel_id={channel_id})"
    )
    assert result == "cleaned", f"cleanup returned {result!r}, expected 'cleaned'"
