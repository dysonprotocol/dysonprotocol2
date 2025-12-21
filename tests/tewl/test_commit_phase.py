"""
Test commit phase for TEWL (Tool for External World Lookups).

Stateless tests using query script run with --extra-code.
"""

import json
import hashlib


def test_compute_commit_hash(chainnet, tewl_script_code):
    """Test commit hash computation."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_hash():
    h = _compute_commit_hash(1, {"answer": "42"}, "secret", "dys1provider")
    return {"hash": h}
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
        "demo_hash",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])

    # Compute expected hash locally
    data = json.dumps(
        {
            "request_id": 1,
            "response": {"answer": "42"},
            "salt": "secret",
            "provider": "dys1provider",
        },
        sort_keys=True,
    )
    expected = hashlib.sha256(data.encode()).hexdigest()

    assert result_data["result"]["hash"] == expected


def test_commit_hash_deterministic(chainnet, tewl_script_code):
    """Test commit hash is deterministic."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_deterministic():
    h1 = _compute_commit_hash(1, {"answer": "42"}, "salt", "prov")
    h2 = _compute_commit_hash(1, {"answer": "42"}, "salt", "prov")
    return {"h1": h1, "h2": h2, "equal": h1 == h2}
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
        "demo_deterministic",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    assert result_data["result"]["equal"] is True


def test_commit_hash_different_inputs(chainnet, tewl_script_code):
    """Test commit hash differs for different inputs."""
    dysond = chainnet[0]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = (
        tewl_script_code
        + """
def demo_different():
    h1 = _compute_commit_hash(1, {"answer": "42"}, "salt1", "prov")
    h2 = _compute_commit_hash(1, {"answer": "42"}, "salt2", "prov")
    h3 = _compute_commit_hash(1, {"answer": "43"}, "salt1", "prov")
    return {"h1": h1, "h2": h2, "h3": h3}
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
        "demo_different",
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is None, f"Failed: {query_result}"
    result_data = json.loads(query_result["result"])
    result = result_data["result"]

    # All hashes should be different
    assert result["h1"] != result["h2"]
    assert result["h1"] != result["h3"]
    assert result["h2"] != result["h3"]
