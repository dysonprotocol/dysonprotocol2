import pytest
import json

from deep_parse import deep_parse


@pytest.mark.nameservice
def test_commit_success(chainnet):
    """Test successful commitment creation with valid parameters."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def commit_success():
    # Get a valid user address
    executor = get_executor_address()
    
    # Create a valid commitment hash using ComputeHash
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    # Create commitment with valid valuation
    commit_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    return {
        "commit_result": commit_result,
        "hexhash": hexhash,
        "committer": executor,
        "valuation": {"denom": "udys", "amount": "1000000"}
    }
"""

    kwargs = json.dumps({})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "commit_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert "result" in parsed, "Missing result in response"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    # The function return is the dict itself
    function_result = nested_result

    # The function should return the commitment details
    assert "commit_result" in function_result, "Missing commit_result in response"
    assert "hexhash" in function_result, "Missing hexhash in response"
    assert "committer" in function_result, "Missing committer in response"
    assert "valuation" in function_result, "Missing valuation in response"

    commit_result = function_result["commit_result"]
    assert isinstance(commit_result, dict), (
        f"Expected commit_result to be dict, got {type(commit_result)}"
    )

    # Commit response should contain MsgSudoResponse with success indicator
    assert "@type" in commit_result, "Missing @type in commit_result"
    assert commit_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", (
        f"Expected MsgSudoResponse, got: {commit_result['@type']}"
    )
    assert "results" in commit_result, "Missing results in commit_result"
    assert isinstance(commit_result["results"], list), "Expected results to be list"
    assert len(commit_result["results"]) == 1, "Expected one result in commit response"

    # Check the actual MsgCommitResponse
    msg_commit_response = commit_result["results"][0]
    assert isinstance(msg_commit_response, dict), (
        "Expected MsgCommitResponse to be dict"
    )
    assert (
        msg_commit_response["@type"]
        == "/dysonprotocol.nameservice.v1.MsgCommitResponse"
    ), f"Expected MsgCommitResponse, got: {msg_commit_response['@type']}"

    # Verify commitment details
    hexhash = function_result["hexhash"]
    assert isinstance(hexhash, str), (
        f"Expected hexhash to be string, got {type(hexhash)}"
    )
    assert len(hexhash) == 64, (
        f"Expected 64-character hex hash, got length {len(hexhash)}"
    )
    assert all(c in "0123456789abcdef" for c in hexhash), (
        "Expected hex hash to contain only hex characters"
    )

    committer = function_result["committer"]
    assert isinstance(committer, str), (
        f"Expected committer to be string, got {type(committer)}"
    )
    assert committer.startswith("dys"), f"Expected dys address prefix, got: {committer}"

    valuation = function_result["valuation"]
    assert isinstance(valuation, dict), (
        f"Expected valuation to be dict, got {type(valuation)}"
    )
    assert valuation["denom"] == "udys", (
        f"Expected denom 'udys', got: {valuation['denom']}"
    )
    assert valuation["amount"] == "1000000", (
        f"Expected amount '1000000', got: {valuation['amount']}"
    )


@pytest.mark.nameservice
def test_commit_empty_hash(chainnet):
    """Test commitment creation with empty hash fails."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def commit_empty_hash():
    executor = get_executor_address()
    
    # Try to create commitment with empty hash
    try:
        commit_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": executor,
            "hexhash": "",  # Empty hash
            "valuation": {"denom": "udys", "amount": "1000000"}
        })
        return {"error": None, "result": commit_result}
    except Exception as e:
        return {"error": str(e), "result": None}
"""

    kwargs = json.dumps({})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "commit_empty_hash",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert "result" in parsed, "Missing result in response"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    assert "error" in function_result, "Missing error in response"
    assert "result" in function_result, "Missing result in response"

    error = function_result["error"]
    assert isinstance(error, str), f"Expected error to be string, got {type(error)}"
    assert error is not None, "Expected error for empty hash"
    assert "commitment hash cannot be empty" in error, (
        f"Expected hash error message, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_commit_empty_valuation(chainnet):
    """Test commitment creation with empty valuation fails."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def commit_empty_valuation():
    executor = get_executor_address()
    
    # Create valid hash first
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    # Try to create commitment with empty valuation
    try:
        commit_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": executor,
            "hexhash": hexhash,
            "valuation": ""  # Empty valuation
        })
        return {"error": None, "result": commit_result}
    except Exception as e:
        return {"error": str(e), "result": None}
"""

    kwargs = json.dumps({})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "commit_empty_valuation",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert "result" in parsed, "Missing result in response"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    assert "error" in function_result, "Missing error in response"
    assert "result" in function_result, "Missing result in response"

    error = function_result["error"]
    assert isinstance(error, str), f"Expected error to be string, got {type(error)}"
    assert error is not None, "Expected error for empty valuation"

    # Error should be related to invalid valuation format
    error_lower = error.lower()
    has_valuation_error = "valuation" in error_lower
    assert has_valuation_error, f"Expected valuation error, got: {error}"

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_commit_invalid_committer(chainnet):
    """Test commitment creation with invalid committer address fails."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def commit_invalid_committer():
    # Create valid hash first
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": "dys1valid_address_for_hash"
    })
    
    hexhash = hash_result["hex_hash"]
    
    # Try to create commitment with invalid committer address
    try:
        commit_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": "invalid_address",  # Invalid address
            "hexhash": hexhash,
            "valuation": {"denom": "udys", "amount": "1000000"}
        })
        return {"error": None, "result": commit_result}
    except Exception as e:
        return {"error": str(e), "result": None}
"""

    kwargs = json.dumps({})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "commit_invalid_committer",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert "result" in parsed, "Missing result in response"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    assert "error" in function_result, "Missing error in response"
    assert "result" in function_result, "Missing result in response"

    error = function_result["error"]
    assert isinstance(error, str), f"Expected error to be string, got {type(error)}"
    assert error is not None, "Expected error for invalid committer"
    assert "invalid committer address" in error.lower(), (
        f"Expected address error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_commit_duplicate_commitment(chainnet):
    """Test commitment creation with duplicate hash fails."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def commit_duplicate_commitment():
    executor = get_executor_address()
    
    # Create valid hash
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    # Create first commitment (should succeed)
    first_commit = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Try to create duplicate commitment (should fail)
    try:
        second_commit = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": executor,
            "hexhash": hexhash,  # Same hash
            "valuation": {"denom": "udys", "amount": "2000000"}
        })
        return {"error": None, "first_commit": first_commit, "second_commit": second_commit}
    except Exception as e:
        return {"error": str(e), "first_commit": first_commit, "second_commit": None}
"""

    kwargs = json.dumps({})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "commit_duplicate_commitment",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert "result" in parsed, "Missing result in response"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    assert "error" in function_result, "Missing error in response"
    assert "first_commit" in function_result, "Missing first_commit in response"
    assert "second_commit" in function_result, "Missing second_commit in response"

    error = function_result["error"]
    assert isinstance(error, str), f"Expected error to be string, got {type(error)}"
    assert error is not None, "Expected error for duplicate commitment"
    assert "commitment already exists" in error.lower(), (
        f"Expected duplicate error, got: {error}"
    )

    first_commit = function_result["first_commit"]
    assert isinstance(first_commit, dict), (
        f"Expected first_commit to be dict, got {type(first_commit)}"
    )

    # First commit should contain MsgSudoResponse with success indicator
    assert "@type" in first_commit, "Missing @type in first_commit"
    assert first_commit["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", (
        f"Expected MsgSudoResponse, got: {first_commit['@type']}"
    )
    assert "results" in first_commit, "Missing results in first_commit"
    assert isinstance(first_commit["results"], list), "Expected results to be list"
    assert len(first_commit["results"]) == 1, (
        "Expected one result in first commit response"
    )

    second_commit = function_result["second_commit"]
    assert second_commit is None, "Expected no result for second error case"


@pytest.mark.nameservice
def test_commit_nil_request(chainnet):
    """Test commitment creation with nil request fails."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def commit_nil_request():
    try:
        # Try to create commitment with nil message
        commit_result = _sudo(None)  # Nil request
        return {"error": None, "result": commit_result}
    except Exception as e:
        return {"error": str(e), "result": None}
"""

    kwargs = json.dumps({})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "commit_nil_request",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert "result" in parsed, "Missing result in response"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    assert "error" in function_result, "Missing error in response"
    assert "result" in function_result, "Missing result in response"

    error = function_result["error"]
    assert isinstance(error, str), f"Expected error to be string, got {type(error)}"
    assert error is not None, "Expected error for nil request"

    # Error should indicate nil/invalid request
    error_lower = error.lower()
    has_nil_error = "nil" in error_lower
    assert has_nil_error, f"Expected nil request error, got: {error}"

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"
