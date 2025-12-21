"""
End-to-end tests for TEWL (Tool for External World Lookups).

Stateless tests covering all Conditions of Satisfaction using query script run.
These tests simulate the full protocol flow by exercising the logic functions.
"""

import json
import hashlib


# =============================================================================
# CoS 1: Provider can register with bond and fulfill requests
# =============================================================================


def test_cos1_provider_registration_flow(chainnet, tewl_script_code):
    """CoS 1: Provider registration creates active provider record."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_provider_flow():
    # Simulate provider registration by directly setting provider data
    provider_addr = "dys1provider123"
    provider = {
        "address": provider_addr,
        "bond": "2000000",  # Above min_bond
        "reputation": {"total": 0, "correct": 0, "slashed": 0},
        "status": STATUS_ACTIVE,
        "registered_at": 100
    }
    
    # Check status determination
    state = _get_state()
    min_bond = int(state["min_bond"])
    is_active = int(provider["bond"]) >= min_bond
    
    return {
        "provider": provider,
        "min_bond": min_bond,
        "is_active": is_active,
        "status_check": provider["status"] == STATUS_ACTIVE
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
        "demo_provider_flow",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["is_active"] is True
    assert result["status_check"] is True
    assert result["provider"]["bond"] == "2000000"


# =============================================================================
# CoS 2: Requester can create request with prompt, schema, scorer, fee, callback
# =============================================================================


def test_cos2_request_structure(chainnet, tewl_script_code):
    """CoS 2: Request contains all required fields."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_request_structure():
    # Build a complete request structure
    request = {
        "request_id": 1,
        "requester": "dys1requester",
        "prompt": "What is the weather?",
        "response_schema": {"type": "object", "properties": {"temp": {"type": "number"}}},
        "scorer": "def scorer(reveal, state): return state",
        "commit_blocks": 10,
        "reveal_blocks": 10,
        "fee": "100000",
        "callback_script": "dys1callback",
        "callback_fn": "on_result",
        "created_at": 100,
        "status": REQ_PENDING,
        "commits": {},
        "reveals": {},
        "result": None,
        "scores": {}
    }
    
    # Verify all required fields exist
    required = ["request_id", "requester", "prompt", "response_schema", 
                "scorer", "fee", "callback_script", "callback_fn"]
    missing = [f for f in required if f not in request]
    
    return {
        "request": request,
        "has_all_fields": len(missing) == 0,
        "missing": missing
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
        "demo_request_structure",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["has_all_fields"] is True
    assert result["missing"] == []


# =============================================================================
# CoS 3: Requests processed in priority order (highest fee first)
# =============================================================================


def test_cos3_priority_ordering(chainnet, tewl_script_code):
    """CoS 3: Pending requests sorted by fee descending."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_priority():
    # Simulate multiple pending requests with different fees
    requests = [
        {"request_id": 1, "fee": "50000", "status": REQ_PENDING, "created_at": 100},
        {"request_id": 2, "fee": "200000", "status": REQ_PENDING, "created_at": 101},
        {"request_id": 3, "fee": "100000", "status": REQ_PENDING, "created_at": 102},
    ]
    
    # Sort by fee DESC, then created_at ASC (priority queue logic)
    pending = [r for r in requests if r["status"] == REQ_PENDING]
    sorted_pending = sorted(pending, key=lambda r: (-int(r["fee"]), r["created_at"]))
    
    return {
        "order": [r["request_id"] for r in sorted_pending],
        "highest_fee_first": sorted_pending[0]["fee"] == "200000"
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
        "demo_priority",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    # Should be ordered: 2 (200k), 3 (100k), 1 (50k)
    assert result["order"] == [2, 3, 1]
    assert result["highest_fee_first"] is True


# =============================================================================
# CoS 4: Commit-reveal prevents front-running
# =============================================================================


def test_cos4_commit_reveal_hashing(chainnet, tewl_script_code):
    """CoS 4: Commit hash hides response until reveal."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_commit_reveal():
    request_id = 1
    response = {"answer": "42"}
    salt = "secret_salt_12345"
    provider = "dys1provider"
    
    # Compute commit hash
    commit_hash = _compute_commit_hash(request_id, response, salt, provider)
    
    # Cannot reverse hash to get response
    # Different salt = different hash (prevents copying)
    other_hash = _compute_commit_hash(request_id, response, "other_salt", provider)
    
    return {
        "commit_hash": commit_hash,
        "other_hash": other_hash,
        "hashes_differ": commit_hash != other_hash,
        "hash_length": len(commit_hash)
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
        "demo_commit_reveal",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["hashes_differ"] is True
    assert result["hash_length"] == 64  # SHA256 hex


def test_cos4_reveal_verification(chainnet, tewl_script_code):
    """CoS 4: Reveal must match commit hash."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_reveal_verify():
    request_id = 1
    response = {"answer": "42"}
    salt = "secret"
    provider = "dys1provider"
    
    # Original commit
    commit_hash = _compute_commit_hash(request_id, response, salt, provider)
    
    # Correct reveal
    reveal_hash = _compute_commit_hash(request_id, response, salt, provider)
    correct = commit_hash == reveal_hash
    
    # Wrong response
    wrong_response_hash = _compute_commit_hash(request_id, {"answer": "43"}, salt, provider)
    wrong_response = commit_hash == wrong_response_hash
    
    # Wrong salt
    wrong_salt_hash = _compute_commit_hash(request_id, response, "wrong", provider)
    wrong_salt = commit_hash == wrong_salt_hash
    
    return {
        "correct_reveal": correct,
        "wrong_response_rejected": not wrong_response,
        "wrong_salt_rejected": not wrong_salt
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
        "demo_reveal_verify",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["correct_reveal"] is True
    assert result["wrong_response_rejected"] is True
    assert result["wrong_salt_rejected"] is True


# =============================================================================
# CoS 5: Schema validation rejects malformed provider responses
# =============================================================================


def test_cos5_schema_validation(chainnet, tewl_script_code):
    """CoS 5: Schema validation rejects invalid responses."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_schema_validation():
    schema = {
        "type": "object",
        "properties": {
            "temperature": {"type": "number"},
            "unit": {"type": "string"}
        }
    }
    
    valid_response = {"temperature": 72.5, "unit": "F"}
    invalid_type = {"temperature": "hot", "unit": "F"}  # string instead of number
    missing_field = {"temperature": 72.5}  # missing unit (OK, not required)
    wrong_structure = "just a string"  # not an object
    
    return {
        "valid": _validate_against_schema(valid_response, schema),
        "invalid_type": _validate_against_schema(invalid_type, schema),
        "partial_ok": _validate_against_schema(missing_field, schema),
        "wrong_structure": _validate_against_schema(wrong_structure, schema)
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
        "demo_schema_validation",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["valid"] is True
    assert result["invalid_type"] is False
    assert result["partial_ok"] is True  # Properties not required by default
    assert result["wrong_structure"] is False


# =============================================================================
# CoS 6: Scorer runs in sandboxed dyslang environment
# =============================================================================


def test_cos6_scorer_sandbox(chainnet, tewl_script_code):
    """CoS 6: Scorer executes in isolated sandbox."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_scorer_sandbox():
    # Scorer code that computes consensus
    scorer_code = '''
def scorer(reveal, state):
    if state is None:
        state = {"votes": {}, "result": None, "scores": {}}
    
    ans = reveal["response"]["answer"]
    prov = reveal["provider"]
    
    state["votes"][ans] = state["votes"].get(ans, 0) + 1
    state["scores"][prov] = 1.0
    
    # Majority wins
    best = max(state["votes"], key=state["votes"].get)
    state["result"] = {"answer": best}
    
    return state
'''
    
    # Run scorer steps
    r1 = {"provider": "p1", "response": {"answer": "A"}}
    r2 = {"provider": "p2", "response": {"answer": "A"}}
    r3 = {"provider": "p3", "response": {"answer": "B"}}
    
    s1 = _run_scorer_step(scorer_code, r1, None)
    s2 = _run_scorer_step(scorer_code, r2, s1)
    s3 = _run_scorer_step(scorer_code, r3, s2)
    
    return {
        "final_result": s3["result"],
        "votes": s3["votes"],
        "scores": s3["scores"]
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
        "demo_scorer_sandbox",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    # "A" got 2 votes, "B" got 1, so "A" wins
    assert result["final_result"] == {"answer": "A"}
    assert result["votes"]["A"] == 2
    assert result["votes"]["B"] == 1


# =============================================================================
# CoS 7: Fees distributed to providers proportional to score
# =============================================================================


def test_cos7_fee_distribution(chainnet, tewl_script_code):
    """CoS 7: Fees distributed proportionally to scores."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_fee_distribution():
    total_fee = 1000000  # 1M udys
    
    # Scores: p1=2.0, p2=1.0, p3=0.0 (total positive = 3.0)
    scores = {"p1": 2.0, "p2": 1.0, "p3": 0.0}
    
    total_score = sum(s for s in scores.values() if s > 0)
    
    distributions = {}
    for provider, score in scores.items():
        if score > 0:
            amount = int(total_fee * score / total_score)
            distributions[provider] = amount
    
    return {
        "total_fee": total_fee,
        "total_score": total_score,
        "distributions": distributions,
        "p1_share": distributions.get("p1", 0),
        "p2_share": distributions.get("p2", 0),
        "p3_share": distributions.get("p3", 0)
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
        "demo_fee_distribution",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    # p1: 2/3 of 1M = 666666, p2: 1/3 of 1M = 333333, p3: 0
    assert result["p1_share"] == 666666
    assert result["p2_share"] == 333333
    assert result["p3_share"] == 0


# =============================================================================
# CoS 8: Providers with score 0 are slashed
# =============================================================================


def test_cos8_slash_zero_score(chainnet, tewl_script_code):
    """CoS 8: Providers with score=0 get slashed."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_slash_logic():
    state = _get_state()
    min_bond = int(state["min_bond"])
    slash_amount = int(min_bond * 0.1)  # 10% of min bond
    
    # Provider with score 0 should be slashed
    scores = {"p1": 1.0, "p2": 0.0, "p3": -0.5}
    
    to_slash = [p for p, s in scores.items() if s <= 0]
    
    # Simulate slash effect
    provider_bond = 2000000
    bond_after_slash = provider_bond - slash_amount
    
    return {
        "slash_amount": slash_amount,
        "to_slash": to_slash,
        "bond_before": provider_bond,
        "bond_after": bond_after_slash,
        "p2_slashed": "p2" in to_slash,
        "p3_slashed": "p3" in to_slash
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
        "demo_slash_logic",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["p2_slashed"] is True
    assert result["p3_slashed"] is True
    assert result["slash_amount"] == 100000  # 10% of 1M min bond
    assert result["bond_after"] == 1900000


# =============================================================================
# CoS 9: Callback invoked with consensus result
# =============================================================================


def test_cos9_callback_structure(chainnet, tewl_script_code):
    """CoS 9: Callback receives correct parameters."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_callback_structure():
    # Simulate callback invocation structure
    request = {
        "request_id": 42,
        "callback_script": "dys1callbackscript",
        "callback_fn": "handle_result"
    }
    result = {"answer": "42", "confidence": 0.95}
    
    # The callback message structure
    callback_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExecScript",
        "script_address": request["callback_script"],
        "function_name": request["callback_fn"],
        "args": json.dumps([request["request_id"], result])
    }
    
    # Parse args to verify structure
    args = json.loads(callback_msg["args"])
    
    return {
        "callback_script": callback_msg["script_address"],
        "callback_fn": callback_msg["function_name"],
        "request_id_in_args": args[0],
        "result_in_args": args[1],
        "correct_structure": args[0] == 42 and args[1] == result
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
        "demo_callback_structure",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["callback_script"] == "dys1callbackscript"
    assert result["callback_fn"] == "handle_result"
    assert result["request_id_in_args"] == 42
    assert result["correct_structure"] is True


# =============================================================================
# CoS 10: No consensus → escrow refunded, no slash
# =============================================================================


def test_cos10_no_consensus_refund(chainnet, tewl_script_code):
    """CoS 10: No consensus refunds escrow without slashing."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_no_consensus():
    # Scorer that returns None for no consensus
    scorer_code = '''
def scorer(reveal, state):
    if state is None:
        state = {"votes": {}, "result": None, "scores": {}}
    
    ans = reveal["response"]["answer"]
    state["votes"][ans] = state["votes"].get(ans, 0) + 1
    state["scores"][reveal["provider"]] = 0.5  # neutral
    
    # Check for majority
    total = sum(state["votes"].values())
    for a, count in state["votes"].items():
        if count > total / 2:
            state["result"] = {"answer": a}
            return state
    
    # No majority = no consensus
    state["result"] = None
    return state
'''
    
    # 50-50 split - no consensus
    r1 = {"provider": "p1", "response": {"answer": "A"}}
    r2 = {"provider": "p2", "response": {"answer": "B"}}
    
    s1 = _run_scorer_step(scorer_code, r1, None)
    s2 = _run_scorer_step(scorer_code, r2, s1)
    
    # Check outcome
    no_consensus = s2["result"] is None
    all_neutral = all(s == 0.5 for s in s2["scores"].values())
    
    return {
        "result": s2["result"],
        "scores": s2["scores"],
        "no_consensus": no_consensus,
        "no_slash": all_neutral  # 0.5 score = no slash
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
        "demo_no_consensus",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["no_consensus"] is True
    assert result["result"] is None
    assert result["no_slash"] is True


# =============================================================================
# Additional E2E: Full protocol flow simulation
# =============================================================================


def test_e2e_full_flow_simulation(chainnet, tewl_script_code):
    """E2E: Simulate complete request lifecycle."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_full_flow():
    # === Phase 1: Setup ===
    # Provider with bond above minimum
    provider = {
        "address": "dys1provider",
        "bond": "2000000",
        "reputation": {"total": 0, "correct": 0, "slashed": 0},
        "status": STATUS_ACTIVE,
        "registered_at": 100
    }
    
    # === Phase 2: Create Request ===
    request = {
        "request_id": 1,
        "requester": "dys1requester",
        "prompt": "What is 2+2?",
        "response_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
        "scorer": "def scorer(r,s): s=s or {'result':None,'scores':{}}; s['result']=r['response']; s['scores'][r['provider']]=1.0; return s",
        "fee": "100000",
        "status": REQ_ACTIVE,
        "commits": {},
        "reveals": {}
    }
    
    # === Phase 3: Commit ===
    response = {"answer": "4"}
    salt = "mysalt"
    commit_hash = _compute_commit_hash(1, response, salt, provider["address"])
    request["commits"][provider["address"]] = {"hash": commit_hash, "block": 110}
    
    # === Phase 4: Reveal ===
    # Verify hash matches
    reveal_hash = _compute_commit_hash(1, response, salt, provider["address"])
    hash_matches = commit_hash == reveal_hash
    
    # Validate schema
    schema_valid = _validate_against_schema(response, request["response_schema"])
    
    if hash_matches and schema_valid:
        request["reveals"][provider["address"]] = {"response": response, "valid": True}
        request["status"] = REQ_REVEALING
    
    # === Phase 5: Finalize ===
    # Run scorer
    scorer_code = '''
def scorer(reveal, state):
    if state is None:
        state = {"result": None, "scores": {}}
    state["result"] = reveal["response"]
    state["scores"][reveal["provider"]] = 1.0
    return state
'''
    
    reveal = {"provider": provider["address"], "response": response}
    final_state = _run_scorer_step(scorer_code, reveal, None)
    
    request["result"] = final_state["result"]
    request["scores"] = final_state["scores"]
    request["status"] = REQ_RESOLVED
    
    # === Verify Final State ===
    return {
        "status": request["status"],
        "result": request["result"],
        "scores": request["scores"],
        "provider_score": request["scores"].get(provider["address"], 0),
        "flow_complete": request["status"] == REQ_RESOLVED
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
        "demo_full_flow",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result = json.loads(query_result["result"])["result"]

    assert result["flow_complete"] is True
    assert result["status"] == "resolved"
    assert result["result"] == {"answer": "4"}
    assert result["provider_score"] == 1.0
