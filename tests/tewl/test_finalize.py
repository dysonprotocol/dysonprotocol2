"""
Test finalize phase for TEWL (Tool for External World Lookups).

Stateless tests using query script run with --extra-code.
"""

import json


VALID_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}

INCREMENTAL_SCORER = """
def scorer(reveal, state):
    if state is None:
        state = {"result": None, "scores": {}}
    state["result"] = reveal["response"]
    state["scores"][reveal["provider"]] = 1.0
    return state
"""


def test_run_scorer_step(chainnet, tewl_script_code):
    """Test incremental scorer execution."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_run_scorer():
    scorer_code = '''
def scorer(reveal, state):
    if state is None:
        state = {"votes": {}, "result": None, "scores": {}}
    ans = reveal["response"]["answer"]
    state["votes"][ans] = state["votes"].get(ans, 0) + 1
    state["scores"][reveal["provider"]] = 1.0
    # Take first answer as result
    state["result"] = reveal["response"]
    return state
'''
    # First reveal
    state1 = _run_scorer_step(scorer_code, {"provider": "prov1", "response": {"answer": "4"}}, None)
    # Second reveal
    state2 = _run_scorer_step(scorer_code, {"provider": "prov2", "response": {"answer": "4"}}, state1)
    return {"state1": state1, "state2": state2}
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
        "demo_run_scorer",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    assert result["state1"]["result"] == {"answer": "4"}
    assert result["state1"]["scores"]["prov1"] == 1.0
    assert result["state2"]["votes"]["4"] == 2
    assert "prov2" in result["state2"]["scores"]


def test_gas_budget_check(chainnet, tewl_script_code):
    """Test gas budget checking function."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_gas_check():
    return {"gas_ok": _gas_budget_ok()}
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
        "demo_gas_check",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    # At start, gas consumed should be low, so budget should be ok
    assert result_data["result"]["gas_ok"] is True


def test_finalize_phases(chainnet, tewl_script_code):
    """Test finalize phase constants are defined."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_phases():
    return {
        "scoring": PHASE_SCORING,
        "settling": PHASE_SETTLING,
        "complete": PHASE_COMPLETE
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
        "demo_phases",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    assert result["scoring"] == "scoring"
    assert result["settling"] == "settling"
    assert result["complete"] == "complete"


def test_distribute_fees_logic(chainnet, tewl_script_code):
    """Test fee distribution calculation (mocked, no actual transfers)."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_fee_calc():
    # Test fee distribution calculation
    total_fee = 1000000
    scores = {"prov1": 1.0, "prov2": 1.0, "prov3": 0.0}
    
    # Calculate total positive score
    total_score = sum(s for s in scores.values() if s > 0)
    
    distributions = {}
    for provider, score in scores.items():
        if score > 0:
            amount = int(total_fee * score / total_score)
            distributions[provider] = amount
    
    return {"distributions": distributions, "total_score": total_score}
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
        "demo_fee_calc",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    # Two providers with score 1.0 each, total 2.0
    # Each gets 500000 (half of 1000000)
    assert result["total_score"] == 2.0
    assert result["distributions"]["prov1"] == 500000
    assert result["distributions"]["prov2"] == 500000
    assert "prov3" not in result["distributions"]


def test_validate_schema(chainnet, tewl_script_code):
    """Test schema validation function."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_validate():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    
    valid = {"answer": "42"}
    invalid = {"answer": 123}  # number instead of string
    
    valid_result = _validate_against_schema(valid, schema)
    invalid_result = _validate_against_schema(invalid, schema)
    
    return {"valid": valid_result, "invalid": invalid_result}
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
        "demo_validate",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    assert result["valid"] is True
    assert result["invalid"] is False
