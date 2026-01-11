"""
State Channel Non-Participation Proof Tests - PBI-40 Task 40-8

Tests for non-participation proof with real accounts and signed attestations.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse

from tests.state_channels.utils import (
    get_script_code,
    create_signed_attestation,
)


# =============================================================================
# Fixtures
# =============================================================================


def _strip_signed_tx(attestations: list) -> list:
    """Strip signed_tx from attestations to avoid JSON/Python boolean issues."""
    return [{k: v for k, v in att.items() if k != "signed_tx"} for att in attestations]


# =============================================================================
# make_attestation_hash Tests
# =============================================================================


def test_make_attestation_hash_deterministic(chainnet):
    """Test that make_attestation_hash produces consistent output."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_attestation_hash():
    hash1 = make_attestation_hash("dys1a", "dys1b", "test_channel", 5)
    hash2 = make_attestation_hash("dys1a", "dys1b", "test_channel", 5)
    hash3 = make_attestation_hash("dys1c", "dys1b", "test_channel", 5)  # different attester
    
    return {
        "hash1": hash1,
        "hash2": hash2,
        "hash3": hash3,
        "same_inputs_match": hash1 == hash2,
        "different_inputs_differ": hash1 != hash3,
    }
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
        "demo_attestation_hash",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    assert "result" in result, f"Missing 'result' in {result}"
    assert (
        "result" in result["result"]
    ), f"Missing nested 'result' in {result['result']}"
    data = result["result"]["result"]

    assert (
        data["same_inputs_match"] is True
    ), f"same_inputs_match was {data['same_inputs_match']}"
    assert (
        data["different_inputs_differ"] is True
    ), f"different_inputs_differ was {data['different_inputs_differ']}"
    assert (
        len(data["hash1"]) == 64
    ), f"hash1 length was {len(data['hash1'])}, expected 64"


# =============================================================================
# verify_attestations Tests with Real Accounts
# =============================================================================


def test_verify_attestations_quorum_met(chainnet, sc_participants):
    """Test verify_attestations with quorum met using real accounts."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    p1_name, p1_addr = sc_participants[0]
    p2_name, p2_addr = sc_participants[1]
    p3_name, p3_addr = sc_participants[2]
    p4_name, p4_addr = sc_participants[3]

    channel_id = "test_verify_quorum"
    participants = [p1_addr, p2_addr, p3_addr, p4_addr]
    accused = p4_addr
    step_number = 5

    # Create attestations from p1, p2, p3 against p4 (quorum = 3 for 4 participants)
    attestations = []
    for name, addr in [(p1_name, p1_addr), (p2_name, p2_addr), (p3_name, p3_addr)]:
        att = create_signed_attestation(
            dysond, name, addr, accused, channel_id, step_number
        )
        attestations.append(att)

    script_code = get_script_code()
    participants_json = json.dumps(participants)
    attestations_json = json.dumps(_strip_signed_tx(attestations))

    extra_code = (
        script_code
        + f"""

def demo_verify_attestations_quorum():
    import json as _json
    channel_id = "{channel_id}"
    participants = _json.loads('''{participants_json}''')
    
    config = make_channel_config(
        channel_id=channel_id,
        participants=participants,
        computation_script="pass",
        initial_state={{}},
        escrow_per_participant=100,
        total_steps=10,
        created_by=participants[0],
    )
    set_config(channel_id, config)
    
    attestations = _json.loads('''{attestations_json}''')
    result = verify_attestations(channel_id, {step_number}, "{accused}", attestations)
    
    _storage_delete(config_key(channel_id))
    
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
        "demo_verify_attestations_quorum",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    assert "result" in result, f"Missing 'result' in {result}"
    assert (
        "result" in result["result"]
    ), f"Missing nested 'result' in {result['result']}"
    data = result["result"]["result"]

    assert data["valid"] is True, f"valid was {data['valid']}"
    assert data["quorum_met"] is True, f"quorum_met was {data['quorum_met']}"
    assert (
        data["attestation_count"] == 3
    ), f"attestation_count was {data['attestation_count']}"
    assert (
        data["required_quorum"] == 3
    ), f"required_quorum was {data['required_quorum']}"
    assert set(data["valid_attesters"]) == {
        p1_addr,
        p2_addr,
        p3_addr,
    }, f"valid_attesters was {data['valid_attesters']}"


def test_verify_attestations_quorum_not_met(chainnet, sc_participants):
    """Test verify_attestations with insufficient attestations."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    p1_name, p1_addr = sc_participants[0]
    p2_name, p2_addr = sc_participants[1]
    p3_name, p3_addr = sc_participants[2]
    p4_name, p4_addr = sc_participants[3]

    channel_id = "test_verify_insuff"
    participants = [p1_addr, p2_addr, p3_addr, p4_addr]
    accused = p4_addr
    step_number = 5

    # Only 1 attestation (quorum = 3)
    att = create_signed_attestation(
        dysond, p1_name, p1_addr, accused, channel_id, step_number
    )
    attestations = [att]

    script_code = get_script_code()
    participants_json = json.dumps(participants)
    attestations_json = json.dumps(_strip_signed_tx(attestations))

    extra_code = (
        script_code
        + f"""

def demo_verify_attestations_insufficient():
    import json as _json
    channel_id = "{channel_id}"
    participants = _json.loads('''{participants_json}''')
    
    config = make_channel_config(
        channel_id=channel_id,
        participants=participants,
        computation_script="pass",
        initial_state={{}},
        escrow_per_participant=100,
        total_steps=10,
        created_by=participants[0],
    )
    set_config(channel_id, config)
    
    attestations = _json.loads('''{attestations_json}''')
    result = verify_attestations(channel_id, {step_number}, "{accused}", attestations)
    
    _storage_delete(config_key(channel_id))
    
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
        "demo_verify_attestations_insufficient",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    assert "result" in result, f"Missing 'result' in {result}"
    data = result["result"]["result"]

    assert data["valid"] is True, f"valid was {data['valid']}"
    assert data["quorum_met"] is False, f"quorum_met was {data['quorum_met']}"
    assert (
        data["attestation_count"] == 1
    ), f"attestation_count was {data['attestation_count']}"
    assert (
        data["required_quorum"] == 3
    ), f"required_quorum was {data['required_quorum']}"


def test_verify_attestations_duplicate_attesters(chainnet, sc_participants):
    """Test verify_attestations filters out duplicate attesters."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    p1_name, p1_addr = sc_participants[0]
    p2_name, p2_addr = sc_participants[1]
    p3_name, p3_addr = sc_participants[2]

    channel_id = "test_verify_dups"
    participants = [p1_addr, p2_addr, p3_addr]
    accused = p3_addr
    step_number = 3

    # Same attester submits twice
    att1 = create_signed_attestation(
        dysond, p1_name, p1_addr, accused, channel_id, step_number
    )
    att2 = create_signed_attestation(
        dysond, p1_name, p1_addr, accused, channel_id, step_number
    )
    attestations = [att1, att2]

    script_code = get_script_code()
    participants_json = json.dumps(participants)
    attestations_json = json.dumps(_strip_signed_tx(attestations))

    extra_code = (
        script_code
        + f"""

def demo_verify_attestations_duplicates():
    import json as _json
    channel_id = "{channel_id}"
    participants = _json.loads('''{participants_json}''')
    
    config = make_channel_config(
        channel_id=channel_id,
        participants=participants,
        computation_script="pass",
        initial_state={{}},
        escrow_per_participant=100,
        total_steps=10,
        created_by=participants[0],
    )
    set_config(channel_id, config)
    
    attestations = _json.loads('''{attestations_json}''')
    result = verify_attestations(channel_id, {step_number}, "{accused}", attestations)
    
    _storage_delete(config_key(channel_id))
    
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
        "demo_verify_attestations_duplicates",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    # Only counts unique attesters
    assert (
        data["attestation_count"] == 1
    ), f"attestation_count was {data['attestation_count']}"
    assert data["valid_attesters"] == [
        p1_addr
    ], f"valid_attesters was {data['valid_attesters']}"


def test_verify_attestations_self_attestation(chainnet, sc_participants):
    """Test verify_attestations filters out self-attestation."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    p1_name, p1_addr = sc_participants[0]
    p2_name, p2_addr = sc_participants[1]
    p3_name, p3_addr = sc_participants[2]

    channel_id = "test_verify_self"
    participants = [p1_addr, p2_addr, p3_addr]
    accused = p3_addr  # p3 attests against themselves
    step_number = 3

    # Self-attestation
    att = create_signed_attestation(
        dysond, p3_name, p3_addr, accused, channel_id, step_number
    )
    attestations = [att]

    script_code = get_script_code()
    participants_json = json.dumps(participants)
    attestations_json = json.dumps(_strip_signed_tx(attestations))

    extra_code = (
        script_code
        + f"""

def demo_verify_attestations_self():
    import json as _json
    channel_id = "{channel_id}"
    participants = _json.loads('''{participants_json}''')
    
    config = make_channel_config(
        channel_id=channel_id,
        participants=participants,
        computation_script="pass",
        initial_state={{}},
        escrow_per_participant=100,
        total_steps=10,
        created_by=participants[0],
    )
    set_config(channel_id, config)
    
    attestations = _json.loads('''{attestations_json}''')
    result = verify_attestations(channel_id, {step_number}, "{accused}", attestations)
    
    _storage_delete(config_key(channel_id))
    
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
        "demo_verify_attestations_self",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    # Self-attestation filtered out
    assert (
        data["attestation_count"] == 0
    ), f"attestation_count was {data['attestation_count']}"
    assert (
        data["valid_attesters"] == []
    ), f"valid_attesters was {data['valid_attesters']}"


def test_verify_attestations_invalid_hash(chainnet, sc_participants):
    """Test verify_attestations filters out invalid hashes."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    p1_name, p1_addr = sc_participants[0]
    p2_name, p2_addr = sc_participants[1]
    p3_name, p3_addr = sc_participants[2]

    channel_id = "test_verify_badhash"
    participants = [p1_addr, p2_addr, p3_addr]
    accused = p3_addr
    step_number = 3

    # Attestation with wrong hash (no signature, manual creation)
    attestation = {
        "attester": p1_addr,
        "accused": accused,
        "channel_id": channel_id,
        "step_number": step_number,
        "attestation_hash": "wrong_hash_value",
        "timestamp": 100,
    }
    attestations = [attestation]

    script_code = get_script_code()
    participants_json = json.dumps(participants)
    attestations_json = json.dumps(attestations)

    extra_code = (
        script_code
        + f"""

def demo_verify_attestations_invalid_hash():
    import json as _json
    channel_id = "{channel_id}"
    participants = _json.loads('''{participants_json}''')
    
    config = make_channel_config(
        channel_id=channel_id,
        participants=participants,
        computation_script="pass",
        initial_state={{}},
        escrow_per_participant=100,
        total_steps=10,
        created_by=participants[0],
    )
    set_config(channel_id, config)
    
    attestations = _json.loads('''{attestations_json}''')
    result = verify_attestations(channel_id, {step_number}, "{accused}", attestations)
    
    _storage_delete(config_key(channel_id))
    
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
        "demo_verify_attestations_invalid_hash",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    # Invalid hash filtered out
    assert (
        data["attestation_count"] == 0
    ), f"attestation_count was {data['attestation_count']}"
    assert (
        data["valid_attesters"] == []
    ), f"valid_attesters was {data['valid_attesters']}"


def test_verify_attestations_accused_not_participant(
    chainnet, sc_participants, generate_account
):
    """Test verify_attestations rejects non-participant accused."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    p1_name, p1_addr = sc_participants[0]
    p2_name, p2_addr = sc_participants[1]
    p3_name, p3_addr = sc_participants[2]

    # Create outsider account
    outsider_name, outsider_addr = generate_account("outsider", faucet_amount=1)

    channel_id = "test_verify_badaccused"
    participants = [p1_addr, p2_addr, p3_addr]
    accused = outsider_addr  # Not a participant
    step_number = 3

    att = create_signed_attestation(
        dysond, p1_name, p1_addr, accused, channel_id, step_number
    )
    attestations = [att]

    script_code = get_script_code()
    participants_json = json.dumps(participants)
    attestations_json = json.dumps(_strip_signed_tx(attestations))

    extra_code = (
        script_code
        + f"""

def demo_verify_attestations_bad_accused():
    import json as _json
    channel_id = "{channel_id}"
    participants = _json.loads('''{participants_json}''')
    
    config = make_channel_config(
        channel_id=channel_id,
        participants=participants,
        computation_script="pass",
        initial_state={{}},
        escrow_per_participant=100,
        total_steps=10,
        created_by=participants[0],
    )
    set_config(channel_id, config)
    
    attestations = _json.loads('''{attestations_json}''')
    result = verify_attestations(channel_id, {step_number}, "{accused}", attestations)
    
    _storage_delete(config_key(channel_id))
    
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
        "demo_verify_attestations_bad_accused",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["valid"] is False, f"valid was {data['valid']}"
    assert "not a participant" in data["error"], f"error was {data['error']}"


# =============================================================================
# get_final_state Tests
# =============================================================================


def test_get_final_state_no_steps(chainnet, sc_participants):
    """Test get_final_state returns initial state when no steps completed."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    p1_name, p1_addr = sc_participants[0]
    p2_name, p2_addr = sc_participants[1]

    channel_id = "test_final_nosteps"
    participants = [p1_addr, p2_addr]

    script_code = get_script_code()
    participants_json = json.dumps(participants)

    extra_code = (
        script_code
        + f"""

def demo_get_final_state_no_steps():
    import json as _json
    channel_id = "{channel_id}"
    participants = _json.loads('''{participants_json}''')
    initial_state = {{"foo": "bar", "count": 0}}
    
    config = make_channel_config(
        channel_id=channel_id,
        participants=participants,
        computation_script="pass",
        initial_state=initial_state,
        escrow_per_participant=100,
        total_steps=10,
        created_by=participants[0],
    )
    set_config(channel_id, config)
    
    result = get_final_state(channel_id)
    
    _storage_delete(config_key(channel_id))
    
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
        "demo_get_final_state_no_steps",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["final_step"] == 0, f"final_step was {data['final_step']}"
    assert data["state_data"] == {
        "foo": "bar",
        "count": 0,
    }, f"state_data was {data['state_data']}"
    assert (
        len(data["state_hash"]) == 64
    ), f"state_hash length was {len(data['state_hash'])}"


def test_get_final_state_with_completed_steps(chainnet, sc_participants):
    """Test get_final_state returns last completed step state."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    p1_name, p1_addr = sc_participants[0]
    p2_name, p2_addr = sc_participants[1]

    channel_id = "test_final_completed"
    participants = [p1_addr, p2_addr]

    script_code = get_script_code()
    participants_json = json.dumps(participants)

    extra_code = (
        script_code
        + f"""

def demo_get_final_state_completed():
    import json as _json
    channel_id = "{channel_id}"
    participants = _json.loads('''{participants_json}''')
    
    config = make_channel_config(
        channel_id=channel_id,
        participants=participants,
        computation_script="pass",
        initial_state={{"count": 0}},
        escrow_per_participant=100,
        total_steps=10,
        created_by=participants[0],
    )
    set_config(channel_id, config)
    
    # Create state at step 5
    state = make_channel_state(
        channel_id=channel_id,
        step=5,
        state_data={{"count": 5}},
        prev_state_hash="0" * 64,  # Dummy hash for test
    )
    set_state(channel_id, state)
    
    # Create completed step record
    block = get_block_info()
    step_record = make_step_record(
        step=5,
        started_at=int(block["height"]),
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="0" * 64,
    )
    step_record["status"] = StepStatus.COMPLETED
    set_step(channel_id, 5, step_record)
    
    result = get_final_state(channel_id)
    
    _storage_delete(config_key(channel_id))
    _storage_delete(state_key(channel_id))
    _storage_delete(step_key(channel_id, 5))
    
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
        "demo_get_final_state_completed",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"
    result = deep_parse(query_result)
    data = result["result"]["result"]

    assert data["final_step"] == 5, f"final_step was {data['final_step']}"
    assert data["state_data"] == {"count": 5}, f"state_data was {data['state_data']}"


def test_get_final_state_channel_not_found(chainnet):
    """Test get_final_state raises error for non-existent channel."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = (
        script_code
        + """

def demo_get_final_state_not_found():
    return get_final_state("nonexistent_channel")
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
        "demo_get_final_state_not_found",
        "--extra-code",
        extra_code,
    )

    # Expect exception
    assert (
        query_result.get("exception") is not None
    ), f"Expected exception but got: {query_result}"
    assert "Channel not found" in str(
        query_result["exception"]
    ), f"Expected 'Channel not found' in {query_result['exception']}"
