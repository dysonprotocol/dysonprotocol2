"""
State Channel Data Structures Tests - PBI-40 Task 40-1

Tests the state channel script's data structures, hash utilities, quorum calculation,
and storage key patterns using stateless script query execution.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


# Path to the state channel script
SCRIPT_PATH = Path(__file__).parent.parent.parent / "examples" / "state_channels" / "script.py"


def get_script_code() -> str:
    """Load the state channel script source code."""
    return SCRIPT_PATH.read_text()


# =============================================================================
# Status Enum Tests
# =============================================================================

def test_channel_status_values(chainnet):
    """Test ChannelStatus enum values."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_channel_status():
    return {
        "PENDING": ChannelStatus.PENDING,
        "ACTIVE": ChannelStatus.ACTIVE,
        "COMPLETED": ChannelStatus.COMPLETED,
        "DISPUTED": ChannelStatus.DISPUTED,
        "ABORTED": ChannelStatus.ABORTED,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_channel_status",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["PENDING"] == "pending"
    assert values["ACTIVE"] == "active"
    assert values["COMPLETED"] == "completed"
    assert values["DISPUTED"] == "disputed"
    assert values["ABORTED"] == "aborted"


def test_step_status_values(chainnet):
    """Test StepStatus enum values."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_step_status():
    return {
        "COMMITMENT": StepStatus.COMMITMENT,
        "REVEAL": StepStatus.REVEAL,
        "COMPLETED": StepStatus.COMPLETED,
        "TIMEOUT": StepStatus.TIMEOUT,
        "DISPUTED": StepStatus.DISPUTED,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_step_status",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["COMMITMENT"] == "commitment"
    assert values["REVEAL"] == "reveal"
    assert values["COMPLETED"] == "completed"
    assert values["TIMEOUT"] == "timeout"
    assert values["DISPUTED"] == "disputed"


def test_participant_state_values(chainnet):
    """Test ParticipantState enum values."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_participant_state():
    return {
        "ACTIVE": ParticipantState.ACTIVE,
        "WARNED": ParticipantState.WARNED,
        "SUSPENDED": ParticipantState.SUSPENDED,
        "SLASHED": ParticipantState.SLASHED,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_participant_state",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["ACTIVE"] == "active"
    assert values["WARNED"] == "warned"
    assert values["SUSPENDED"] == "suspended"
    assert values["SLASHED"] == "slashed"


def test_dispute_status_values(chainnet):
    """Test DisputeStatus enum values."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_dispute_status():
    return {
        "PENDING": DisputeStatus.PENDING,
        "GUILTY": DisputeStatus.GUILTY,
        "INNOCENT": DisputeStatus.INNOCENT,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_dispute_status",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["PENDING"] == "pending"
    assert values["GUILTY"] == "guilty"
    assert values["INNOCENT"] == "innocent"


def test_dispute_type_values(chainnet):
    """Test DisputeType enum values."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_dispute_type():
    return {
        "COMMITMENT_MISMATCH": DisputeType.COMMITMENT_MISMATCH,
        "INVALID_COMPUTATION": DisputeType.INVALID_COMPUTATION,
        "EQUIVOCATION": DisputeType.EQUIVOCATION,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_dispute_type",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["COMMITMENT_MISMATCH"] == "commitment_mismatch"
    assert values["INVALID_COMPUTATION"] == "invalid_computation"
    assert values["EQUIVOCATION"] == "equivocation"


def test_challenge_status_values(chainnet):
    """Test ChallengeStatus enum values."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_challenge_status():
    return {
        "PENDING": ChallengeStatus.PENDING,
        "RESPONDED": ChallengeStatus.RESPONDED,
        "TIMEOUT": ChallengeStatus.TIMEOUT,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_challenge_status",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["PENDING"] == "pending"
    assert values["RESPONDED"] == "responded"
    assert values["TIMEOUT"] == "timeout"


# =============================================================================
# Quorum Calculation Tests
# =============================================================================

def test_quorum_calculation(chainnet):
    """Test BFT quorum calculation for various participant counts."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_quorum_calculation():
    return {
        "n3": required_quorum(3),  # f=0, all must agree
        "n4": required_quorum(4),  # f=1, quorum=3
        "n5": required_quorum(5),  # f=1, quorum=4
        "n6": required_quorum(6),  # f=1, quorum=5
        "n7": required_quorum(7),  # f=2, quorum=5
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_quorum_calculation",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["n3"] == 3, f"n=3: expected 3, got {values['n3']}"
    assert values["n4"] == 3, f"n=4: expected 3, got {values['n4']}"
    assert values["n5"] == 4, f"n=5: expected 4, got {values['n5']}"
    assert values["n6"] == 5, f"n=6: expected 5, got {values['n6']}"
    assert values["n7"] == 5, f"n=7: expected 5, got {values['n7']}"


# =============================================================================
# Hash Function Tests
# =============================================================================

def test_hash_determinism(chainnet):
    """Test hash functions produce deterministic output."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_hash_determinism():
    # Same input should produce same hash
    h1 = hash_str("test data")
    h2 = hash_str("test data")
    
    # Different key order should produce same hash
    obj1 = {"b": 2, "a": 1}
    obj2 = {"a": 1, "b": 2}
    j1 = hash_json(obj1)
    j2 = hash_json(obj2)
    
    return {
        "str_hash_1": h1,
        "str_hash_2": h2,
        "str_match": h1 == h2,
        "json_hash_1": j1,
        "json_hash_2": j2,
        "json_match": j1 == j2,
        "hash_length": len(h1),
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_hash_determinism",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["str_match"] is True, "String hashes should match"
    assert values["json_match"] is True, "JSON hashes should match (key order independent)"
    assert values["hash_length"] == 64, f"SHA256 hex should be 64 chars, got {values['hash_length']}"


def test_chain_hash_links(chainnet):
    """Test chain hash creates linked hashes."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_chain_hash():
    genesis = "0" * 64
    data1 = {"step": 0, "result": "a"}
    data2 = {"step": 1, "result": "b"}
    
    h1 = chain_hash(genesis, data1)
    h2 = chain_hash(h1, data2)
    h2_alt = chain_hash(genesis, data2)  # Same data, different prev
    
    return {
        "genesis": genesis,
        "h1": h1,
        "h2": h2,
        "h2_alt": h2_alt,
        "h1_differs_genesis": h1 != genesis,
        "h2_differs_h1": h2 != h1,
        "h2_differs_h2_alt": h2 != h2_alt,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_chain_hash",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["h1_differs_genesis"] is True, "h1 should differ from genesis"
    assert values["h2_differs_h1"] is True, "h2 should differ from h1"
    assert values["h2_differs_h2_alt"] is True, "Changing prev_hash should change output"


# =============================================================================
# Storage Key Tests
# =============================================================================

def test_storage_key_patterns(chainnet):
    """Test storage key generation patterns."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_storage_keys():
    cid = "chan123"
    return {
        "prefix": PREFIX,
        "config": config_key(cid),
        "state": state_key(cid),
        "step_0": step_key(cid, 0),
        "step_1": step_key(cid, 1),
        "step_999999": step_key(cid, 999999),
        "participant": participant_key(cid, "dys1abc"),
        "challenge": challenge_key(cid, 5, "dys1abc"),
        "dispute": dispute_key(cid, "disp456"),
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_storage_keys",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    keys = result["result"]["result"]
    assert keys["prefix"] == "sc"
    assert keys["config"] == "sc/chan123/config"
    assert keys["state"] == "sc/chan123/state"
    assert keys["step_0"] == "sc/chan123/steps/000000"
    assert keys["step_1"] == "sc/chan123/steps/000001"
    assert keys["step_999999"] == "sc/chan123/steps/999999"
    assert keys["participant"] == "sc/chan123/participants/dys1abc"
    assert keys["challenge"] == "sc/chan123/challenges/000005/dys1abc"
    assert keys["dispute"] == "sc/chan123/disputes/disp456"


def test_step_key_lexicographic_order(chainnet):
    """Test step keys are lexicographically ordered."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_step_key_order():
    cid = "chan"
    keys = [step_key(cid, i) for i in [5, 100, 2, 50]]
    sorted_keys = sorted(keys)
    return {
        "original": keys,
        "sorted": sorted_keys,
        "is_sorted_correctly": sorted_keys == [
            "sc/chan/steps/000002",
            "sc/chan/steps/000005",
            "sc/chan/steps/000050",
            "sc/chan/steps/000100",
        ]
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_step_key_order",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["is_sorted_correctly"] is True, f"Keys not sorted correctly: {values['sorted']}"


# =============================================================================
# Factory Function Tests
# =============================================================================

def test_make_channel_config(chainnet):
    """Test make_channel_config factory function."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_make_channel_config():
    config = make_channel_config(
        channel_id="test_chan",
        participants=["dys1a", "dys1b", "dys1c"],
        computation_script="state['x'] + 1",
        initial_state={"x": 0},
        escrow_per_participant=1000000,
        total_steps=100,
        created_by="dys1a",
    )
    return config
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_make_channel_config",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    config = result["result"]["result"]
    assert config["channel_id"] == "test_chan"
    assert config["participants"] == ["dys1a", "dys1b", "dys1c"]
    assert config["quorum"] == 3, f"Quorum for n=3 should be 3, got {config['quorum']}"
    assert config["computation_script"] == "state['x'] + 1"
    assert config["initial_state"] == {"x": 0}
    assert config["status"] == "pending"
    assert config["agreed_by"] == []
    assert config["created_at"] > 0


def test_make_participant_record(chainnet):
    """Test make_participant_record factory function."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_make_participant_record():
    record = make_participant_record("dys1abc", 1000000)
    return record
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_make_participant_record",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    record = result["result"]["result"]
    assert record["address"] == "dys1abc"
    assert record["escrow_balance"] == 1000000
    assert record["steps_participated"] == 0
    assert record["consecutive_misses"] == 0
    assert record["status"] == "active"


def test_make_step_record(chainnet):
    """Test make_step_record factory function."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_make_step_record():
    record = make_step_record(
        step=0,
        started_at=100,
        commitment_timeout=60,
        reveal_timeout=60,
        prev_step_hash="genesis",
    )
    return record
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_make_step_record",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    record = result["result"]["result"]
    assert record["step"] == 0
    assert record["started_at"] == 100
    assert record["commitment_deadline"] == 160
    assert record["reveal_deadline"] == 220
    assert record["commitment_hashes"] == {}
    assert record["reveal_hashes"] == {}
    assert record["status"] == "commitment"
    assert record["prev_step_hash"] == "genesis"


# =============================================================================
# JSON Serialization Tests
# =============================================================================

def test_channel_config_json_roundtrip(chainnet):
    """Test ChannelConfig JSON serialization roundtrip."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_config_roundtrip():
    config = make_channel_config(
        channel_id="test",
        participants=["a", "b", "c"],
        computation_script="x+1",
        initial_state={"x": 0},
        escrow_per_participant=100,
        total_steps=10,
        created_by="a",
    )
    
    # Serialize and deserialize
    json_str = json.dumps(config, sort_keys=True)
    restored = json.loads(json_str)
    
    return {
        "original": config,
        "restored": restored,
        "match": config == restored,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_config_roundtrip",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["match"] is True, "JSON roundtrip should preserve data"


def test_step_record_json_roundtrip(chainnet):
    """Test StepRecord JSON serialization roundtrip."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = get_script_code()
    extra_code = script_code + """

def demo_step_roundtrip():
    record = make_step_record(0, 100, 60, 60, "prev")
    
    # Serialize and deserialize
    json_str = json.dumps(record, sort_keys=True)
    restored = json.loads(json_str)
    
    return {
        "original": record,
        "restored": restored,
        "match": record == restored,
    }
"""

    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_step_roundtrip",
        "--extra-code", extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result.get('exception')}"

    values = result["result"]["result"]
    assert values["match"] is True, "JSON roundtrip should preserve data"
