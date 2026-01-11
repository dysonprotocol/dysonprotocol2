"""
State Channel Dispute Tests - PBI-40 Task 40-4

Tests for commitment mismatch dispute resolution:
- raise_dispute_commitment_mismatch validation
- verify_commitment_mismatch helper
- Dispute outcomes (guilty/innocent)
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


# Path to the state channel script
SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "examples" / "state_channels" / "script.py"
)


def get_script_code() -> str:
    """Load the state channel script source code."""
    return SCRIPT_PATH.read_text()


# =============================================================================
# verify_commitment_mismatch Tests
# =============================================================================


def test_verify_commitment_mismatch_detects_mismatch(chainnet):
    """Test verify_commitment_mismatch detects actual mismatch."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_verify_mismatch():
    # Create a commitment with one result
    result_hash_1 = hash_str("result_1")
    salt = "my_salt"
    commitment_hash = hash_str(result_hash_1 + ":" + salt)
    
    # Try to verify with a DIFFERENT result
    result_hash_2 = hash_str("result_2")
    
    verification = verify_commitment_mismatch(commitment_hash, result_hash_2, salt)
    return verification
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_verify_mismatch",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["is_mismatch"] is True


def test_verify_commitment_mismatch_no_mismatch(chainnet):
    """Test verify_commitment_mismatch returns False when matching."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_verify_no_mismatch():
    # Create a commitment
    result_hash = hash_str("my_result")
    salt = "my_salt"
    commitment_hash = hash_str(result_hash + ":" + salt)
    
    # Verify with the SAME result and salt
    verification = verify_commitment_mismatch(commitment_hash, result_hash, salt)
    return verification
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_verify_no_mismatch",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["is_mismatch"] is False


# =============================================================================
# raise_dispute_commitment_mismatch Tests
# =============================================================================


def test_raise_dispute_commitment_mismatch_guilty(chainnet):
    """Test raise_dispute_commitment_mismatch marks accused as guilty with fund distribution.

    Uses alice's funds via MsgSudo to fund the script (query mode doesn't persist).
    """
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_info = dysond("keys", "show", "alice")
    alice_addr = alice_info["address"]

    bob_info = dysond("keys", "show", "bob")
    bob_addr = bob_info["address"]

    charlie_info = dysond("keys", "show", "charlie")
    charlie_addr = charlie_info["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_guilty():
    executor = get_executor_address()
    script_addr = get_script_address()
    accused = "{bob_addr}"  # Bob is the accused
    third_participant = "{charlie_addr}"
    escrow_amount = 1000000
    num_participants = 3
    
    # Fund the script address with total escrow for all participants
    # - Accused's escrow gets slashed and distributed
    # - Honest participants' escrow gets returned
    total_escrow = escrow_amount * num_participants
    
    _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": "{gov_addr}",
        "messages": [{{
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": "{alice_addr}",
            "to_address": script_addr,
            "amount": [{{"denom": "udys", "amount": str(total_escrow)}}],
        }}],
    }})
    
    create_channel(
        channel_id="test_dispute_guilty",
        participants=[executor, accused, third_participant],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=escrow_amount,
        total_steps=10,
    )
    
    config = get_config("test_dispute_guilty")
    config["status"] = "active"
    config["agreed_by"] = [executor, accused, third_participant]
    set_config("test_dispute_guilty", config)
    
    # Create step with accused's commitment
    block = get_block_info()
    real_result_hash = hash_str("real_result")
    real_salt = "real_salt"
    commitment_hash = hash_str(real_result_hash + ":" + real_salt)
    
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    step_record["commitment_hashes"][accused] = commitment_hash
    set_step("test_dispute_guilty", 0, step_record)
    
    # Create participant record for accused with escrow
    participant = make_participant_record(accused, escrow_amount)
    set_participant("test_dispute_guilty", accused, participant)
    
    # Create participant records for other participants
    for addr in [executor, third_participant]:
        p = make_participant_record(addr, escrow_amount)
        set_participant("test_dispute_guilty", addr, p)
    
    # Raise dispute with WRONG result_hash (proves mismatch)
    wrong_result_hash = hash_str("wrong_result")
    
    result = raise_dispute_commitment_mismatch(
        channel_id="test_dispute_guilty",
        step=0,
        accused=accused,
        result_hash=wrong_result_hash,
        salt=real_salt,
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_guilty",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["channel_id"] == "test_dispute_guilty"
    assert data["accused"] == bob_addr
    assert data["is_mismatch"] is True
    assert data["status"] == "guilty"

    # Verify closure with reporter bonus
    assert data["closure"] is not None, "Expected channel closure on guilty verdict"
    closure = data["closure"]
    assert closure["channel_status"] == "disputed"
    assert closure["slash_amount"] == 1000000
    assert closure["slash_distribution"]["reporter"] == gov_addr
    assert closure["slash_distribution"]["reporter_bonus"] == 200000  # 20% of 1M


def test_raise_dispute_commitment_mismatch_innocent(chainnet):
    """Test raise_dispute_commitment_mismatch marks accused as innocent when no mismatch."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_innocent():
    executor = get_executor_address()
    accused = "dys1accused"
    
    create_channel(
        channel_id="test_dispute_innocent",
        participants=[executor, accused, "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_dispute_innocent")
    config["status"] = "active"
    config["agreed_by"] = [executor, accused, "dys1c"]
    set_config("test_dispute_innocent", config)
    
    # Create step with accused's commitment
    block = get_block_info()
    result_hash = hash_str("correct_result")
    salt = "correct_salt"
    commitment_hash = hash_str(result_hash + ":" + salt)
    
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    step_record["commitment_hashes"][accused] = commitment_hash
    set_step("test_dispute_innocent", 0, step_record)
    
    # Raise dispute with CORRECT result and salt (no mismatch)
    result = raise_dispute_commitment_mismatch(
        channel_id="test_dispute_innocent",
        step=0,
        accused=accused,
        result_hash=result_hash,
        salt=salt,
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_innocent",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["channel_id"] == "test_dispute_innocent"
    assert data["accused"] == "dys1accused"
    assert data["is_mismatch"] is False
    assert data["status"] == "innocent"


def test_raise_dispute_no_commitment(chainnet):
    """Test raise_dispute_commitment_mismatch rejects if accused has no commitment."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_no_commitment():
    executor = get_executor_address()
    accused = "dys1accused"
    
    create_channel(
        channel_id="test_dispute_no_commit",
        participants=[executor, accused, "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_dispute_no_commit")
    config["status"] = "active"
    config["agreed_by"] = [executor, accused, "dys1c"]
    set_config("test_dispute_no_commit", config)
    
    # Create step WITHOUT accused's commitment
    block = get_block_info()
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    # Only executor has commitment, NOT accused
    step_record["commitment_hashes"][executor] = "some_hash"
    set_step("test_dispute_no_commit", 0, step_record)
    
    # Try to dispute accused who has no commitment
    result = raise_dispute_commitment_mismatch(
        channel_id="test_dispute_no_commit",
        step=0,
        accused=accused,
        result_hash="any_hash",
        salt="any_salt",
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_no_commitment",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "No commitment from accused" in str(exception), f"Wrong error: {exception}"


def test_raise_dispute_channel_not_found(chainnet):
    """Test raise_dispute_commitment_mismatch rejects non-existent channel."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_dispute_no_channel():
    result = raise_dispute_commitment_mismatch(
        channel_id="nonexistent_channel",
        step=0,
        accused="dys1anyone",
        result_hash="any_hash",
        salt="any_salt",
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_no_channel",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "not found" in str(exception).lower(), f"Wrong error: {exception}"


def test_raise_dispute_channel_not_active(chainnet):
    """Test raise_dispute_commitment_mismatch rejects for pending channel."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_pending_channel():
    executor = get_executor_address()
    
    # Create channel but leave it pending (not active)
    create_channel(
        channel_id="test_dispute_pending",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    # Channel is still pending, not active
    result = raise_dispute_commitment_mismatch(
        channel_id="test_dispute_pending",
        step=0,
        accused="dys1b",
        result_hash="any_hash",
        salt="any_salt",
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_pending_channel",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "not active" in str(exception).lower(), f"Wrong error: {exception}"


def test_get_dispute_info(chainnet):
    """Test get_dispute_info returns dispute record."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_get_dispute_info():
    executor = get_executor_address()
    accused = "dys1accused"
    channel_id = "test_get_dispute"
    
    create_channel(
        channel_id=channel_id,
        participants=[executor, accused, "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config(channel_id)
    config["status"] = "active"
    config["agreed_by"] = [executor, accused, "dys1c"]
    set_config(channel_id, config)
    
    # Manually create a dispute record to test get_dispute_info
    # (Avoids triggering fund transfers which require funded script)
    block = get_block_info()
    dispute_id = _generate_dispute_id(channel_id, 0, DisputeType.COMMITMENT_MISMATCH, accused)
    
    dispute_record = make_dispute_record(
        dispute_id=dispute_id,
        channel_id=channel_id,
        step=0,
        dispute_type=DisputeType.COMMITMENT_MISMATCH,
        raised_by=executor,
        accused=accused,
        evidence_hash=hash_str("test_evidence"),
    )
    dispute_record["status"] = DisputeStatus.GUILTY
    dispute_record["resolved_at"] = int(block["height"])
    
    set_dispute(channel_id, dispute_id, dispute_record)
    
    # Get dispute info
    dispute_info = get_dispute_info(channel_id, dispute_id)
    
    return {{
        "dispute_id": dispute_id,
        "dispute_info": dispute_info,
    }}
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_get_dispute_info",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["dispute_id"] is not None
    assert data["dispute_info"]["dispute_type"] == "commitment_mismatch"
    assert data["dispute_info"]["status"] == "guilty"
    assert data["dispute_info"]["accused"] == "dys1accused"


# =============================================================================
# Invalid Computation Dispute Tests (40-5)
# =============================================================================


def test_execute_computation(chainnet):
    """Test execute_computation runs computation_script."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_execute_computation():
    computation_script = "state['x'] + 1"
    prev_state = {"x": 5}
    step = 0
    
    result = execute_computation(computation_script, prev_state, step)
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_execute_computation",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["result"] == 6  # 5 + 1
    assert len(data["result_hash"]) == 64  # SHA256 hex


def test_verify_invalid_computation_detects_invalid(chainnet):
    """Test verify_invalid_computation detects wrong result."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_verify_invalid():
    computation_script = "state['x'] + 1"
    prev_state = {"x": 5}
    step = 0
    
    # Correct result is 6, but we claim 999
    wrong_result_hash = hash_json({"result": 999})
    
    verification = verify_invalid_computation(
        computation_script=computation_script,
        prev_state=prev_state,
        step=step,
        claimed_result_hash=wrong_result_hash,
    )
    return verification
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_verify_invalid",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["is_invalid"] is True
    assert data["actual_result"] == 6


def test_verify_invalid_computation_valid(chainnet):
    """Test verify_invalid_computation returns False for correct result."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_verify_valid():
    computation_script = "state['x'] + 1"
    prev_state = {"x": 5}
    step = 0
    
    # Correct result is 6
    correct_result_hash = hash_json({"result": 6})
    
    verification = verify_invalid_computation(
        computation_script=computation_script,
        prev_state=prev_state,
        step=step,
        claimed_result_hash=correct_result_hash,
    )
    return verification
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_verify_valid",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["is_invalid"] is False


def test_raise_dispute_invalid_computation_guilty(chainnet):
    """Test verify_invalid_computation detects incorrect computation.

    Note: Full raise_dispute_invalid_computation test requires funded script.
    This test validates the verification logic only.
    """
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_invalid_guilty():
    # Test verification logic without fund transfers
    computation_script = "state['x'] + 1"  # Adds 1 to x
    prev_state = {{"x": 5}}
    
    # Accused claims result is 999, but correct is 6 (5+1)
    wrong_result_hash = hash_json({{"result": 999}})
    
    # Verify invalid computation
    verification = verify_invalid_computation(
        computation_script=computation_script,
        prev_state=prev_state,
        step=0,
        claimed_result_hash=wrong_result_hash,
    )
    
    return {{
        "is_invalid": verification["is_invalid"],
        "actual_result_hash": verification["actual_result_hash"],
        "claimed_result_hash": wrong_result_hash,
        "would_be_guilty": verification["is_invalid"],
    }}
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_invalid_guilty",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["is_invalid"] is True, "Should detect invalid computation"
    assert data["would_be_guilty"] is True
    assert data["actual_result_hash"] != data["claimed_result_hash"]


def test_raise_dispute_invalid_computation_innocent(chainnet):
    """Test raise_dispute_invalid_computation marks accused as innocent."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_invalid_innocent():
    executor = get_executor_address()
    accused = "dys1accused"
    
    create_channel(
        channel_id="test_invalid_innocent",
        participants=[executor, accused, "dys1c"],
        computation_script="state['x'] + 1",  # Adds 1 to x
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_invalid_innocent")
    config["status"] = "active"
    config["agreed_by"] = [executor, accused, "dys1c"]
    set_config("test_invalid_innocent", config)
    
    # Create step with accused's CORRECT reveal
    block = get_block_info()
    
    # Accused correctly claims result is 6 (5+1)
    correct_result_hash = hash_json({{"result": 6}})
    
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    step_record["reveal_hashes"][accused] = correct_result_hash
    set_step("test_invalid_innocent", 0, step_record)
    
    # Raise false accusation
    result = raise_dispute_invalid_computation(
        channel_id="test_invalid_innocent",
        step=0,
        accused=accused,
        prev_state={{"x": 5}},  # With x=5, result should be 6
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_invalid_innocent",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["channel_id"] == "test_invalid_innocent"
    assert data["accused"] == "dys1accused"
    assert data["is_invalid"] is False
    assert data["status"] == "innocent"


def test_raise_dispute_invalid_computation_no_reveal(chainnet):
    """Test raise_dispute_invalid_computation rejects if no reveal."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_invalid_no_reveal():
    executor = get_executor_address()
    accused = "dys1accused"
    
    create_channel(
        channel_id="test_invalid_no_reveal",
        participants=[executor, accused, "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_invalid_no_reveal")
    config["status"] = "active"
    config["agreed_by"] = [executor, accused, "dys1c"]
    set_config("test_invalid_no_reveal", config)
    
    # Create step WITHOUT accused's reveal
    block = get_block_info()
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    # Only executor has reveal, NOT accused
    step_record["reveal_hashes"][executor] = hash_json({{"result": 6}})
    set_step("test_invalid_no_reveal", 0, step_record)
    
    # Try to dispute accused who has no reveal
    result = raise_dispute_invalid_computation(
        channel_id="test_invalid_no_reveal",
        step=0,
        accused=accused,
        prev_state={{"x": 5}},
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_invalid_no_reveal",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "No reveal from accused" in str(exception), f"Wrong error: {exception}"


# =============================================================================
# Equivocation Dispute Tests (40-6)
# =============================================================================


def test_verify_equivocation_detects_double_sign(chainnet):
    """Test verify_equivocation detects different messages."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_verify_equivocation():
    message_1_hash = hash_json({"result": "value_A"})
    message_2_hash = hash_json({"result": "value_B"})
    
    verification = verify_equivocation(message_1_hash, message_2_hash)
    return verification
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_verify_equivocation",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["is_equivocation"] is True


def test_verify_equivocation_same_message(chainnet):
    """Test verify_equivocation returns False for same message."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_verify_no_equivocation():
    message_hash = hash_json({"result": "same_value"})
    
    verification = verify_equivocation(message_hash, message_hash)
    return verification
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_verify_no_equivocation",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["is_equivocation"] is False


def test_raise_dispute_equivocation_guilty(chainnet):
    """Test verify_equivocation detects double-signing.

    Note: Full raise_dispute_equivocation test requires funded script.
    This test validates the verification logic only.
    """
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_equivocation_guilty():
    # Test verification logic without fund transfers
    # Two DIFFERENT message content hashes from same step
    message_1_hash = hash_json({{"result": "value_A", "nonce": 1}})
    message_2_hash = hash_json({{"result": "value_B", "nonce": 2}})
    
    verification = verify_equivocation(message_1_hash, message_2_hash)
    
    return {{
        "is_equivocation": verification["is_equivocation"],
        "message_1_hash": message_1_hash,
        "message_2_hash": message_2_hash,
        "would_be_guilty": verification["is_equivocation"],
    }}
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_equivocation_guilty",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["is_equivocation"] is True, "Should detect equivocation"
    assert data["would_be_guilty"] is True
    assert data["message_1_hash"] != data["message_2_hash"]


def test_raise_dispute_equivocation_innocent(chainnet):
    """Test raise_dispute_equivocation marks accused as innocent when same message."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_equivocation_innocent():
    executor = get_executor_address()
    accused = "dys1accused"
    
    create_channel(
        channel_id="test_equivoc_innocent",
        participants=[executor, accused, "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_equivoc_innocent")
    config["status"] = "active"
    config["agreed_by"] = [executor, accused, "dys1c"]
    set_config("test_equivoc_innocent", config)
    
    # Two IDENTICAL messages (same content)
    same_content = {{"result": "same_value"}}
    message_1 = {{
        "content": same_content,
        "signer": accused,
        "step": 0,
    }}
    message_2 = {{
        "content": same_content,
        "signer": accused,
        "step": 0,
    }}
    
    result = raise_dispute_equivocation(
        channel_id="test_equivoc_innocent",
        step=0,
        accused=accused,
        message_1=message_1,
        message_2=message_2,
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_equivocation_innocent",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["channel_id"] == "test_equivoc_innocent"
    assert data["accused"] == "dys1accused"
    assert data["is_equivocation"] is False
    assert data["status"] == "innocent"


def test_raise_dispute_equivocation_signer_mismatch(chainnet):
    """Test raise_dispute_equivocation rejects if signer doesn't match accused."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_dispute_equivocation_signer_mismatch():
    executor = get_executor_address()
    accused = "dys1accused"
    
    create_channel(
        channel_id="test_equivoc_signer",
        participants=[executor, accused, "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_equivoc_signer")
    config["status"] = "active"
    config["agreed_by"] = [executor, accused, "dys1c"]
    set_config("test_equivoc_signer", config)
    
    # Message 1 has WRONG signer
    message_1 = {{
        "content": {{"result": "value_A"}},
        "signer": "dys1wrong_signer",  # Not accused!
        "step": 0,
    }}
    message_2 = {{
        "content": {{"result": "value_B"}},
        "signer": accused,
        "step": 0,
    }}
    
    result = raise_dispute_equivocation(
        channel_id="test_equivoc_signer",
        step=0,
        accused=accused,
        message_1=message_1,
        message_2=message_2,
    )
    return result
"""
    )

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_dispute_equivocation_signer_mismatch",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "signer mismatch" in str(exception), f"Wrong error: {exception}"
