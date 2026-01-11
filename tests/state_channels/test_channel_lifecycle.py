"""
State Channel Lifecycle Tests - PBI-40 Task 40-2

Tests channel creation and participant agreement:
- create_channel validation and storage
- agree_to_channel escrow and status transitions
- channel_address proof verification
"""

import json
import pytest
from deep_parse import deep_parse


# =============================================================================
# create_channel Tests
# =============================================================================


def test_create_channel_success(sc_script):
    """Test create_channel stores valid ChannelConfig."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    kwargs = json.dumps(
        {
            "channel_id": "test_chan_1",
            "participants": ["dys1a", "dys1b", "dys1c"],
            "computation_script": "state['x'] + 1",
            "initial_state": {"x": 0},
            "escrow_per_participant": 1000000,
            "total_steps": 100,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "create_channel",
        "--kwargs",
        kwargs,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    data = result["result"]["result"]
    assert data["channel_id"] == "test_chan_1"

    config = data["config"]
    assert config["channel_id"] == "test_chan_1"
    assert config["participants"] == ["dys1a", "dys1b", "dys1c"]
    assert config["quorum"] == 3
    assert config["status"] == "pending"
    assert config["agreed_by"] == []
    assert config["escrow_per_participant"] == 1000000
    assert config["total_steps"] == 100


def test_create_channel_insufficient_participants(sc_script):
    """Test create_channel rejects less than 3 participants."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    kwargs = json.dumps(
        {
            "channel_id": "test_chan_few",
            "participants": ["dys1a", "dys1b"],  # Only 2!
            "computation_script": "state['x'] + 1",
            "initial_state": {"x": 0},
            "escrow_per_participant": 1000000,
            "total_steps": 100,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "create_channel",
        "--kwargs",
        kwargs,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception for < 3 participants"
    assert "Minimum 3 participants" in str(exception), f"Wrong error: {exception}"


def test_create_channel_empty_script(sc_script):
    """Test create_channel rejects empty computation script."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    kwargs = json.dumps(
        {
            "channel_id": "test_chan_empty",
            "participants": ["dys1a", "dys1b", "dys1c"],
            "computation_script": "",  # Empty!
            "initial_state": {"x": 0},
            "escrow_per_participant": 1000000,
            "total_steps": 100,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "create_channel",
        "--kwargs",
        kwargs,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception for empty script"
    assert "cannot be empty" in str(exception), f"Wrong error: {exception}"


def test_create_channel_duplicate_participants(sc_script):
    """Test create_channel rejects duplicate participants."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    kwargs = json.dumps(
        {
            "channel_id": "test_chan_dup",
            "participants": ["dys1a", "dys1b", "dys1a"],  # Duplicate!
            "computation_script": "state['x'] + 1",
            "initial_state": {"x": 0},
            "escrow_per_participant": 1000000,
            "total_steps": 100,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "create_channel",
        "--kwargs",
        kwargs,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception for duplicates"
    assert "Duplicate" in str(exception), f"Wrong error: {exception}"


def test_create_channel_invalid_escrow(sc_script):
    """Test create_channel rejects zero or negative escrow."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    kwargs = json.dumps(
        {
            "channel_id": "test_chan_zero",
            "participants": ["dys1a", "dys1b", "dys1c"],
            "computation_script": "state['x'] + 1",
            "initial_state": {"x": 0},
            "escrow_per_participant": 0,  # Zero!
            "total_steps": 100,
        }
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "create_channel",
        "--kwargs",
        kwargs,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception for zero escrow"
    assert "must be positive" in str(exception), f"Wrong error: {exception}"


# =============================================================================
# agree_to_channel Tests
# =============================================================================


def test_agree_to_channel_not_found(sc_script):
    """Test agree_to_channel rejects non-existent channel."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    kwargs = json.dumps({"channel_id": "nonexistent_channel"})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "agree_to_channel",
        "--kwargs",
        kwargs,
    )

    exception = query_result.get("exception")
    assert (
        exception is not None
    ), "Should have raised exception for non-existent channel"
    assert "not found" in str(exception).lower(), f"Wrong error: {exception}"


def test_agree_to_channel_not_participant(sc_script):
    """Test agree_to_channel rejects caller not in participants list."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    # Multi-step: create channel then try to agree (extra_code calls deployed functions)
    extra_code = """
def demo_agree_not_participant():
    create_channel(
        channel_id="test_chan_not_part",
        participants=["dys1a", "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={"x": 0},
        escrow_per_participant=1000000,
        total_steps=100,
    )
    result = agree_to_channel("test_chan_not_part")
    return result
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,  # Not in participants list
        "--function-name",
        "demo_agree_not_participant",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception for non-participant"
    assert "Not a participant" in str(exception), f"Wrong error: {exception}"


def test_agree_to_channel_no_escrow(sc_script):
    """Test agree_to_channel rejects when no escrow attached."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    extra_code = """
def demo_agree_no_escrow():
    executor = get_executor_address()
    create_channel(
        channel_id="test_chan_no_escrow",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={"x": 0},
        escrow_per_participant=1000000,
        total_steps=100,
    )
    result = agree_to_channel("test_chan_no_escrow")
    return result
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "demo_agree_no_escrow",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception for no escrow"
    assert "Insufficient escrow" in str(exception), f"Wrong error: {exception}"


def test_get_channel_info(sc_script):
    """Test get_channel_info returns complete channel data."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    extra_code = """
def demo_get_channel_info():
    create_channel(
        channel_id="test_chan_info",
        participants=["dys1a", "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={"x": 0},
        escrow_per_participant=1000000,
        total_steps=100,
    )
    info = get_channel_info("test_chan_info")
    return info
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "demo_get_channel_info",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    info = result["result"]["result"]
    assert "config" in info
    assert info["config"]["channel_id"] == "test_chan_info"
    assert info["config"]["status"] == "pending"
    assert info["participants"] == {}  # No one agreed yet


def test_create_and_query_channel(sc_script):
    """Test channel can be created and queried."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    extra_code = """
def demo_create_and_query():
    create_result = create_channel(
        channel_id="test_chan_query",
        participants=["dys1a", "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={"x": 0},
        escrow_per_participant=1000000,
        total_steps=100,
    )
    config = query_config("test_chan_query")
    return {
        "create_result": create_result,
        "queried_config": config,
        "matches": create_result["config"]["channel_id"] == config["channel_id"],
    }
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "demo_create_and_query",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    data = result["result"]["result"]
    assert data["matches"] is True
    assert data["queried_config"]["status"] == "pending"


# =============================================================================
# Channel Address Proof Tests
# =============================================================================


def test_agree_to_channel_without_required_proof(sc_script):
    """Test agree_to_channel rejects different channel_address without proof."""
    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    # Use real accounts from keyring
    bob_key_info = dysond("keys", "show", "bob")
    bob_addr = bob_key_info["address"]
    charlie_key_info = dysond("keys", "show", "charlie")
    charlie_addr = charlie_key_info["address"]

    # Run as owner (script_addr) using extra-code
    # Owner is also a participant, and tries to agree with a different channel_address
    extra_code = f"""
def demo_agree_without_proof():
    create_channel(
        channel_id="proof_test_1",
        participants=["{bob_addr}", "{charlie_addr}", "{script_addr}"],
        computation_script="pass",
        initial_state={{}},
        escrow_per_participant=100,
        total_steps=10,
    )
    # script_addr (owner/executor) is a participant
    # Trying to set channel_address to bob_addr without proof should fail
    agree_to_channel(
        channel_id="proof_test_1",
        channel_address="{bob_addr}",
        channel_address_proof="",
    )
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,  # owner can use extra-code
        "--function-name",
        "demo_agree_without_proof",
        "--extra-code",
        extra_code,
    )

    # Should have raised an exception
    assert (
        query_result.get("exception") is not None
    ), f"Expected exception but got: {query_result}"
    exc = str(query_result.get("exception", ""))
    assert (
        "channel_address_proof required" in exc
    ), f"Expected 'channel_address_proof required' error, got: {exc}"


def test_verify_channel_address_proof_success(sc_script):
    """Test verify_channel_address_proof with valid signature."""
    import tempfile

    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    # Use existing alice/bob accounts from keyring
    alice_key_info = dysond("keys", "show", "alice")
    alice_addr = alice_key_info["address"]
    bob_key_info = dysond("keys", "show", "bob")
    bob_addr = bob_key_info["address"]

    # Create proof: bob's key signs for alice on channel "test_chan"
    proof_data = {"participant": alice_addr, "channel_id": "test_chan"}
    tx_for_signing = {
        "body": {
            "messages": [
                {
                    "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                    "signer": bob_addr,
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

        dysond(
            "tx",
            "sign",
            tx_file.name,
            "--from",
            "bob",
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

        with open(signed_tx_file.name, "r") as f:
            proof_json = f.read().strip()

    proof_escaped = proof_json.replace("\\", "\\\\").replace("'", "\\'")

    extra_code = f"""
def demo_verify_proof():
    result = verify_channel_address_proof(
        channel_address="{bob_addr}",
        participant="{alice_addr}",
        channel_id="test_chan",
        signed_tx_json='''{proof_escaped}''',
    )
    return {{"verified": result}}
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "demo_verify_proof",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    assert result["result"]["result"]["verified"] is True


def test_verify_channel_address_proof_wrong_signer(sc_script):
    """Test verify_channel_address_proof rejects proof from wrong signer."""
    import tempfile

    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    # Use existing accounts from keyring
    alice_key_info = dysond("keys", "show", "alice")
    alice_addr = alice_key_info["address"]
    bob_key_info = dysond("keys", "show", "bob")
    bob_addr = bob_key_info["address"]
    charlie_key_info = dysond("keys", "show", "charlie")
    charlie_addr = charlie_key_info["address"]

    # Create proof signed by charlie, but we'll claim it's from bob
    proof_data = {"participant": alice_addr, "channel_id": "test_chan"}
    tx_for_signing = {
        "body": {
            "messages": [
                {
                    "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                    "signer": charlie_addr,  # Charlie signs
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

        dysond(
            "tx",
            "sign",
            tx_file.name,
            "--from",
            "charlie",
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

        with open(signed_tx_file.name, "r") as f:
            proof_json = f.read().strip()

    proof_escaped = proof_json.replace("\\", "\\\\").replace("'", "\\'")

    extra_code = f"""
def demo_verify_wrong_signer():
    verify_channel_address_proof(
        channel_address="{bob_addr}",
        participant="{alice_addr}",
        channel_id="test_chan",
        signed_tx_json='''{proof_escaped}''',
    )
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "demo_verify_wrong_signer",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception but got: {query_result}"
    exc = query_result.get("exception", {})
    exc_msg = exc.get("msg", "") if isinstance(exc, dict) else str(exc)
    assert (
        "Proof signed by wrong address" in exc_msg
    ), f"Expected 'Proof signed by wrong address' error, got: {exc_msg}"


def test_verify_channel_address_proof_wrong_channel_id(sc_script):
    """Test verify_channel_address_proof rejects proof for wrong channel."""
    import tempfile

    dysond = sc_script["dysond"]
    script_addr = sc_script["script_address"]

    # Use existing accounts from keyring
    alice_key_info = dysond("keys", "show", "alice")
    alice_addr = alice_key_info["address"]
    bob_key_info = dysond("keys", "show", "bob")
    bob_addr = bob_key_info["address"]

    # Create proof for channel "test_chan_A"
    proof_data = {"participant": alice_addr, "channel_id": "test_chan_A"}
    tx_for_signing = {
        "body": {
            "messages": [
                {
                    "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                    "signer": bob_addr,
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

        dysond(
            "tx",
            "sign",
            tx_file.name,
            "--from",
            "bob",
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

        with open(signed_tx_file.name, "r") as f:
            proof_json = f.read().strip()

    proof_escaped = proof_json.replace("\\", "\\\\").replace("'", "\\'")

    extra_code = f"""
def demo_verify_wrong_channel():
    verify_channel_address_proof(
        channel_address="{bob_addr}",
        participant="{alice_addr}",
        channel_id="test_chan_B",
        signed_tx_json='''{proof_escaped}''',
    )
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        script_addr,
        "--executor-address",
        script_addr,
        "--function-name",
        "demo_verify_wrong_channel",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception but got: {query_result}"
    exc = query_result.get("exception", {})
    exc_msg = exc.get("msg", "") if isinstance(exc, dict) else str(exc)
    assert (
        "channel_id mismatch" in exc_msg
    ), f"Expected channel_id mismatch error, got: {exc_msg}"
