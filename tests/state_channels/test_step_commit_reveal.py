"""
State Channel Commit-Reveal Tests - PBI-40 Task 40-3

Tests for step commitment, reveal, and completion:
- submit_commitment validation and recording
- submit_reveal verification
- complete_step with full participation (MVP: all must agree)
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
# submit_commitment Tests
# =============================================================================


def test_submit_commitment_success(chainnet):
    """Test submit_commitment records commitment hash."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_submit_commitment():
    # Create and activate a channel
    executor = get_executor_address()
    create_channel(
        channel_id="test_commit_1",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    # Manually set to ACTIVE for testing (simulating all agreed)
    config = get_config("test_commit_1")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_commit_1", config)
    
    # Create initial state and step
    block = get_block_info()
    state = {{
        "channel_id": "test_commit_1",
        "step": 0,
        "state_data": {{"x": 0}},
        "state_hash": hash_json({{"x": 0}}),
        "prev_state_hash": "",
        "last_updated": int(block["height"]),
    }}
    set_state("test_commit_1", state)
    
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash=state["state_hash"],
    )
    set_step("test_commit_1", 0, step_record)
    
    # Create participant record
    participant = make_participant_record(executor, 1000000)
    set_participant("test_commit_1", executor, participant)
    
    # Submit commitment
    result_hash = hash_str("my_result")
    salt = "my_secret_salt"
    commitment_hash = hash_str(result_hash + ":" + salt)
    
    result = submit_commitment("test_commit_1", 0, commitment_hash)
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
        "demo_submit_commitment",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["channel_id"] == "test_commit_1"
    assert data["step"] == 0
    assert data["participant"] == gov_addr
    assert len(data["commitment_hash"]) == 64  # SHA256 hex
    assert data["all_committed"] is False  # Only 1 of 3 committed


def test_submit_commitment_not_participant(chainnet):
    """Test submit_commitment rejects non-participant."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_commit_not_participant():
    # Create channel where executor is NOT a participant
    create_channel(
        channel_id="test_commit_np",
        participants=["dys1a", "dys1b", "dys1c"],  # gov_addr not in list
        computation_script="state['x'] + 1",
        initial_state={"x": 0},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    # Set to ACTIVE
    config = get_config("test_commit_np")
    config["status"] = "active"
    config["agreed_by"] = ["dys1a", "dys1b", "dys1c"]
    set_config("test_commit_np", config)
    
    # Create step
    block = get_block_info()
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    set_step("test_commit_np", 0, step_record)
    
    # Try to commit (should fail)
    result = submit_commitment("test_commit_np", 0, "fake_commitment")
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
        "demo_commit_not_participant",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "Not a participant" in str(exception), f"Wrong error: {exception}"


def test_submit_commitment_wrong_phase(chainnet):
    """Test submit_commitment rejects if not in commitment phase."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_commit_wrong_phase():
    executor = get_executor_address()
    create_channel(
        channel_id="test_commit_phase",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_commit_phase")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_commit_phase", config)
    
    # Create step in REVEAL phase
    block = get_block_info()
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"  # Already in reveal phase
    set_step("test_commit_phase", 0, step_record)
    
    result = submit_commitment("test_commit_phase", 0, "some_commitment")
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
        "demo_commit_wrong_phase",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "not in commitment phase" in str(exception), f"Wrong error: {exception}"


# =============================================================================
# submit_reveal Tests
# =============================================================================


def test_submit_reveal_success(chainnet):
    """Test submit_reveal verifies and records reveal."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_submit_reveal():
    executor = get_executor_address()
    create_channel(
        channel_id="test_reveal_1",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_reveal_1")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_reveal_1", config)
    
    # Create step in REVEAL phase with commitment
    block = get_block_info()
    result_hash = hash_str("my_result")
    salt = "my_secret_salt"
    commitment_hash = hash_str(result_hash + ":" + salt)
    
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    step_record["commitment_hashes"][executor] = commitment_hash
    set_step("test_reveal_1", 0, step_record)
    
    # Create participant record
    participant = make_participant_record(executor, 1000000)
    set_participant("test_reveal_1", executor, participant)
    
    # Submit reveal
    result = submit_reveal("test_reveal_1", 0, result_hash, salt)
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
        "demo_submit_reveal",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["channel_id"] == "test_reveal_1"
    assert data["step"] == 0
    assert data["participant"] == gov_addr
    assert data["reveals_count"] == 1


def test_submit_reveal_mismatch(chainnet):
    """Test submit_reveal rejects if hash doesn't match commitment."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_reveal_mismatch():
    executor = get_executor_address()
    create_channel(
        channel_id="test_reveal_mis",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_reveal_mis")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_reveal_mis", config)
    
    # Create step with a commitment
    block = get_block_info()
    result_hash = hash_str("my_result")
    salt = "my_secret_salt"
    commitment_hash = hash_str(result_hash + ":" + salt)
    
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    step_record["commitment_hashes"][executor] = commitment_hash
    set_step("test_reveal_mis", 0, step_record)
    
    # Submit reveal with WRONG salt
    result = submit_reveal("test_reveal_mis", 0, result_hash, "wrong_salt")
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
        "demo_reveal_mismatch",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "mismatch" in str(exception).lower(), f"Wrong error: {exception}"


# =============================================================================
# complete_step_with_quorum Tests
# =============================================================================


def test_complete_step_with_quorum(chainnet):
    """Test complete_step_with_quorum finalizes step with quorum reveals."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_complete_step():
    executor = get_executor_address()
    create_channel(
        channel_id="test_complete_1",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_complete_1")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_complete_1", config)
    
    # Create state
    block = get_block_info()
    state = {{
        "channel_id": "test_complete_1",
        "step": 0,
        "state_data": {{"x": 0}},
        "state_hash": hash_json({{"x": 0}}),
        "prev_state_hash": "",
        "last_updated": int(block["height"]),
    }}
    set_state("test_complete_1", state)
    
    # Create step in REVEAL phase with quorum reveals (3 participants, quorum=3)
    consensus_result_hash = hash_str("consensus_result")
    
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    # All 3 participants revealed the same result
    step_record["reveal_hashes"][executor] = consensus_result_hash
    step_record["reveal_hashes"]["dys1b"] = consensus_result_hash
    step_record["reveal_hashes"]["dys1c"] = consensus_result_hash
    set_step("test_complete_1", 0, step_record)
    
    # Create participant records
    for addr in [executor, "dys1b", "dys1c"]:
        participant = make_participant_record(addr, 1000000)
        set_participant("test_complete_1", addr, participant)
    
    # Complete the step
    result = complete_step_with_quorum("test_complete_1", 0)
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
        "demo_complete_step",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["channel_id"] == "test_complete_1"
    assert data["step"] == 0
    assert len(data["participants"]) == 3  # MVP: all participants
    assert data["is_final"] is False
    assert data["next_step"] == 1


def test_complete_step_incomplete_reveals(chainnet):
    """Test complete_step rejects without full participation (MVP)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_complete_incomplete():
    executor = get_executor_address()
    create_channel(
        channel_id="test_complete_insuf",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_complete_insuf")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_complete_insuf", config)
    
    block = get_block_info()
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    # Only 2 reveals (MVP requires all 3)
    step_record["reveal_hashes"][executor] = hash_str("result")
    step_record["reveal_hashes"]["dys1b"] = hash_str("result")
    set_step("test_complete_insuf", 0, step_record)
    
    result = complete_step("test_complete_insuf", 0)
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
        "demo_complete_incomplete",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "Incomplete reveals" in str(exception), f"Wrong error: {exception}"


def test_complete_step_result_mismatch(chainnet):
    """Test complete_step rejects when reveals don't all match (MVP)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_complete_mismatch():
    executor = get_executor_address()
    create_channel(
        channel_id="test_complete_nc",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_complete_nc")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_complete_nc", config)
    
    block = get_block_info()
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["status"] = "reveal"
    # All different results - MVP requires all to match
    step_record["reveal_hashes"][executor] = hash_str("result_a")
    step_record["reveal_hashes"]["dys1b"] = hash_str("result_b")
    step_record["reveal_hashes"]["dys1c"] = hash_str("result_c")
    set_step("test_complete_nc", 0, step_record)
    
    result = complete_step("test_complete_nc", 0)
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
        "demo_complete_mismatch",
        "--extra-code",
        extra_code,
    )

    exception = query_result.get("exception")
    assert exception is not None, "Should have raised exception"
    assert "Result mismatch" in str(exception), f"Wrong error: {exception}"


def test_get_step_info(chainnet):
    """Test get_step_info returns step data with metadata."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_get_step_info():
    executor = get_executor_address()
    create_channel(
        channel_id="test_step_info",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_step_info")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_step_info", config)
    
    block = get_block_info()
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    step_record["commitment_hashes"][executor] = "hash1"
    step_record["commitment_hashes"]["dys1b"] = "hash2"
    step_record["reveal_hashes"][executor] = "reveal1"
    set_step("test_step_info", 0, step_record)
    
    info = get_step_info("test_step_info", 0)
    return info
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
        "demo_get_step_info",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["commitments_count"] == 2
    assert data["reveals_count"] == 1
    assert data["total_participants"] == 3
    assert data["all_committed"] is False  # 2/3 committed
    assert data["all_revealed"] is False  # 1/3 revealed


def test_get_step_status(chainnet):
    """Test get_step_status shows participation status."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + f"""

def demo_get_step_status():
    executor = get_executor_address()
    create_channel(
        channel_id="test_step_status",
        participants=[executor, "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={{"x": 0}},
        escrow_per_participant=1000000,
        total_steps=10,
    )
    
    config = get_config("test_step_status")
    config["status"] = "active"
    config["agreed_by"] = [executor, "dys1b", "dys1c"]
    set_config("test_step_status", config)
    
    block = get_block_info()
    step_record = make_step_record(
        step=0,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    # 2 of 3 commitments, 1 reveal
    step_record["commitment_hashes"][executor] = "hash1"
    step_record["commitment_hashes"]["dys1b"] = "hash2"
    step_record["reveal_hashes"][executor] = "reveal1"
    set_step("test_step_status", 0, step_record)
    
    result = get_step_status("test_step_status", 0)
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
        "demo_get_step_status",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["channel_id"] == "test_step_status"
    assert data["step"] == 0
    assert data["status"] == "commitment"  # Still in commitment phase
    assert data["committed_count"] == 2
    assert data["revealed_count"] == 1
    assert data["all_committed"] is False
    assert data["all_revealed"] is False
    assert "dys1c" in data["missing_commitment"]
    assert "dys1b" in data["missing_reveal"]
    assert "dys1c" in data["missing_reveal"]
