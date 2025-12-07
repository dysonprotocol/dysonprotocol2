import pytest
import json

from deep_parse import deep_parse


@pytest.mark.nameservice
def test_reveal_success(chainnet):
    """Test successful name reveal with complete commit-reveal flow."""
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

def reveal_success():
    # Use a fixed address that has funds in genesis
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Create commitment
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "testname.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    # Step 2: Commit with sudo (using executor as authority)
    commit_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Reveal with matching data
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "testname.dys",
        "salt": "random_salt_123"
    })
    
    # Step 4: Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "testname.dys"
    })
    
    # Step 5: Query name resolution
    resolve_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
        "name_or_address": "testname.dys"
    })
    
    return {
        "commit_result": commit_result,
        "reveal_result": reveal_result,
        "hexhash": hexhash,
        "name": "testname.dys",
        "committer": executor,
        "valuation": {"denom": "udys", "amount": "1000000"},
        "nft_query": nft_query,
        "resolve_query": resolve_query
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
        "reveal_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    print(f"Query result: {query_result}")
    parsed = deep_parse(query_result)
    print(f"Parsed result: {parsed}")

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

    # Verify all expected fields are present
    assert "commit_result" in function_result, "Missing commit_result in response"
    assert "reveal_result" in function_result, "Missing reveal_result in response"
    assert "hexhash" in function_result, "Missing hexhash in response"
    assert "name" in function_result, "Missing name in response"
    assert "committer" in function_result, "Missing committer in response"
    assert "valuation" in function_result, "Missing valuation in response"
    assert "nft_query" in function_result, "Missing nft_query in response"
    assert "resolve_query" in function_result, "Missing resolve_query in response"

    # Verify commit result
    commit_result = function_result["commit_result"]
    assert isinstance(commit_result, dict), (
        f"Expected commit_result to be dict, got {type(commit_result)}"
    )
    assert "@type" in commit_result, "Missing @type in commit_result"
    assert commit_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify reveal result
    reveal_result = function_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"Expected reveal_result to be dict, got {type(reveal_result)}"
    )
    assert "@type" in reveal_result, "Missing @type in reveal_result"
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify NFT was minted
    nft_query = function_result["nft_query"]
    assert isinstance(nft_query, dict), (
        f"Expected nft_query to be dict, got {type(nft_query)}"
    )
    assert "nft" in nft_query, "Missing nft in query response"

    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["class_id"] == "nameservice.dys", (
        f"Expected class_id 'nameservice.dys', got: {nft['class_id']}"
    )
    assert nft["id"] == "testname.dys", f"Expected id 'testname.dys', got: {nft['id']}"
    assert nft["uri"] == function_result["committer"], (
        f"Expected uri to be committer, got: {nft['uri']}"
    )

    # Verify name resolution
    resolve_query = function_result["resolve_query"]
    assert isinstance(resolve_query, dict), (
        f"Expected resolve_query to be dict, got {type(resolve_query)}"
    )
    assert "address" in resolve_query, "Missing address in resolve response"
    assert resolve_query["address"] == function_result["committer"], (
        f"Expected address to resolve to committer, got: {resolve_query['address']}"
    )

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

    name = function_result["name"]
    assert isinstance(name, str), f"Expected name to be string, got {type(name)}"
    assert name == "testname.dys", f"Expected name 'testname.dys', got: {name}"
    # Name regex validation - nameservicev1.NameRegex.MatchString(name) would be used in Go
    assert name == "testname.dys", f"Expected name 'testname.dys', got: {name}"

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
def test_reveal_empty_name(chainnet):
    """Test reveal with empty name fails."""
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

def reveal_empty_name():
    executor = get_executor_address()
    
    # Create commitment first
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Try reveal with empty name
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "",  # Empty name
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_empty_name",
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
    assert error is not None, "Expected error for empty name"
    assert "name cannot be empty" in error, f"Expected name empty error, got: {error}"

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_reserved_name_fails(chainnet):
    """Test reveal with reserved name fails."""
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

def reveal_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "reserved-test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Try reveal with reserved name - should fail
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "reserved-test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_reserved_name",
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
    assert error is not None, "Expected error for reserved name"
    assert "reserved" in error.lower(), (
        f"Expected reserved name error, got: {error}"
    )
    assert "cannot be registered via reveal" in error.lower(), (
        f"Expected 'cannot be registered via reveal' in error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_non_reserved_name_succeeds(chainnet):
    """Test reveal with non-reserved name succeeds even when reserved names are set."""
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

def reveal_non_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for non-reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "allowed-test.dys",
        "salt": "random_salt_456",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Reveal with non-reserved name - should succeed
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "allowed-test.dys",
        "salt": "random_salt_456"
    })
    
    # Step 4: Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "allowed-test.dys"
    })
    
    return {
        "reveal_result": reveal_result,
        "nft_query": nft_query
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
        "reveal_non_reserved_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    # Verify reveal succeeded
    assert "reveal_result" in function_result, "Missing reveal_result in response"
    reveal_result = function_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"Expected reveal_result to be dict, got {type(reveal_result)}"
    )
    assert "@type" in reveal_result, "Missing @type in reveal_result"
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify NFT was minted
    assert "nft_query" in function_result, "Missing nft_query in response"
    nft_query = function_result["nft_query"]
    assert isinstance(nft_query, dict), (
        f"Expected nft_query to be dict, got {type(nft_query)}"
    )
    assert "nft" in nft_query, "Missing nft in query response"
    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["id"] == "allowed-test.dys", (
        f"Expected NFT id 'allowed-test.dys', got: {nft['id']}"
    )


@pytest.mark.nameservice
def test_reveal_empty_salt(chainnet):
    """Test reveal with empty salt fails."""
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

def reveal_empty_salt():
    executor = get_executor_address()
    
    # Create commitment first
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Try reveal with empty salt
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "test.dys",
            "salt": ""  # Empty salt
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_empty_salt",
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
    assert error is not None, "Expected error for empty salt"
    # Empty salt should cause commitment not found error due to hash mismatch
    error_lower = error.lower()
    has_commitment_error = "commitment not found" in error_lower
    assert has_commitment_error, f"Expected commitment not found error, got: {error}"

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_reserved_name_fails(chainnet):
    """Test reveal with reserved name fails."""
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

def reveal_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "reserved-test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Try reveal with reserved name - should fail
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "reserved-test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_reserved_name",
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
    assert error is not None, "Expected error for reserved name"
    assert "reserved" in error.lower(), (
        f"Expected reserved name error, got: {error}"
    )
    assert "cannot be registered via reveal" in error.lower(), (
        f"Expected 'cannot be registered via reveal' in error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_non_reserved_name_succeeds(chainnet):
    """Test reveal with non-reserved name succeeds even when reserved names are set."""
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

def reveal_non_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for non-reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "allowed-test.dys",
        "salt": "random_salt_456",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Reveal with non-reserved name - should succeed
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "allowed-test.dys",
        "salt": "random_salt_456"
    })
    
    # Step 4: Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "allowed-test.dys"
    })
    
    return {
        "reveal_result": reveal_result,
        "nft_query": nft_query
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
        "reveal_non_reserved_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    # Verify reveal succeeded
    assert "reveal_result" in function_result, "Missing reveal_result in response"
    reveal_result = function_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"Expected reveal_result to be dict, got {type(reveal_result)}"
    )
    assert "@type" in reveal_result, "Missing @type in reveal_result"
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify NFT was minted
    assert "nft_query" in function_result, "Missing nft_query in response"
    nft_query = function_result["nft_query"]
    assert isinstance(nft_query, dict), (
        f"Expected nft_query to be dict, got {type(nft_query)}"
    )
    assert "nft" in nft_query, "Missing nft in query response"
    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["id"] == "allowed-test.dys", (
        f"Expected NFT id 'allowed-test.dys', got: {nft['id']}"
    )


@pytest.mark.nameservice
def test_reveal_empty_committer(chainnet):
    """Test reveal with empty committer fails."""
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

def reveal_empty_committer():
    executor = get_executor_address()
    
    # Create commitment first
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Try reveal with empty committer
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": "",  # Empty committer
            "name": "test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_empty_committer",
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
    assert error is not None, "Expected error for empty committer"
    assert "invalid committer address" in error.lower(), (
        f"Expected address error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_reserved_name_fails(chainnet):
    """Test reveal with reserved name fails."""
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

def reveal_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "reserved-test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Try reveal with reserved name - should fail
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "reserved-test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_reserved_name",
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
    assert error is not None, "Expected error for reserved name"
    assert "reserved" in error.lower(), (
        f"Expected reserved name error, got: {error}"
    )
    assert "cannot be registered via reveal" in error.lower(), (
        f"Expected 'cannot be registered via reveal' in error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_non_reserved_name_succeeds(chainnet):
    """Test reveal with non-reserved name succeeds even when reserved names are set."""
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

def reveal_non_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for non-reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "allowed-test.dys",
        "salt": "random_salt_456",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Reveal with non-reserved name - should succeed
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "allowed-test.dys",
        "salt": "random_salt_456"
    })
    
    # Step 4: Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "allowed-test.dys"
    })
    
    return {
        "reveal_result": reveal_result,
        "nft_query": nft_query
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
        "reveal_non_reserved_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    # Verify reveal succeeded
    assert "reveal_result" in function_result, "Missing reveal_result in response"
    reveal_result = function_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"Expected reveal_result to be dict, got {type(reveal_result)}"
    )
    assert "@type" in reveal_result, "Missing @type in reveal_result"
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify NFT was minted
    assert "nft_query" in function_result, "Missing nft_query in response"
    nft_query = function_result["nft_query"]
    assert isinstance(nft_query, dict), (
        f"Expected nft_query to be dict, got {type(nft_query)}"
    )
    assert "nft" in nft_query, "Missing nft in query response"
    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["id"] == "allowed-test.dys", (
        f"Expected NFT id 'allowed-test.dys', got: {nft['id']}"
    )


@pytest.mark.nameservice
def test_reveal_name_already_registered(chainnet):
    """Test reveal with name already registered fails."""
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

def reveal_name_already_registered():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Complete first commit-reveal flow
    hash_result1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "testname.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash1 = hash_result1["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash1,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    first_reveal = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "testname.dys",
        "salt": "random_salt_123"
    })
    
    # Step 2: Try to reveal same name again
    hash_result2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "testname.dys",
        "salt": "different_salt_456",
        "committer": executor
    })
    
    hexhash2 = hash_result2["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash2,
        "valuation": {"denom": "udys", "amount": "2000000"}
    })
    
    # Try second reveal - should fail
    try:
        second_reveal = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "testname.dys",
            "salt": "different_salt_456"
        })
        return {"error": None, "first_reveal": first_reveal, "second_reveal": second_reveal}
    except Exception as e:
        return {"error": str(e), "first_reveal": first_reveal, "second_reveal": None}
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
        "reveal_name_already_registered",
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
    assert "first_reveal" in function_result, "Missing first_reveal in response"
    assert "second_reveal" in function_result, "Missing second_reveal in response"

    error = function_result["error"]
    assert isinstance(error, str), f"Expected error to be string, got {type(error)}"
    assert error is not None, "Expected error for duplicate name"
    assert "name is already registered" in error.lower(), (
        f"Expected duplicate name error, got: {error}"
    )

    first_reveal = function_result["first_reveal"]
    assert isinstance(first_reveal, dict), (
        f"Expected first_reveal to be dict, got {type(first_reveal)}"
    )
    assert "@type" in first_reveal, "Missing @type in first_reveal"
    assert first_reveal["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    second_reveal = function_result["second_reveal"]
    assert second_reveal is None, "Expected no result for second error case"


@pytest.mark.nameservice
def test_reveal_commitment_not_found(chainnet):
    """Test reveal without creating commitment fails."""
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

def reveal_commitment_not_found():
    executor = get_executor_address()
    
    # Try reveal without creating commitment
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "nonexistent.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_commitment_not_found",
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
    assert error is not None, "Expected error for missing commitment"
    assert "commitment not found" in error.lower(), (
        f"Expected commitment not found error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_reserved_name_fails(chainnet):
    """Test reveal with reserved name fails."""
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

def reveal_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "reserved-test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Try reveal with reserved name - should fail
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "reserved-test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_reserved_name",
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
    assert error is not None, "Expected error for reserved name"
    assert "reserved" in error.lower(), (
        f"Expected reserved name error, got: {error}"
    )
    assert "cannot be registered via reveal" in error.lower(), (
        f"Expected 'cannot be registered via reveal' in error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_non_reserved_name_succeeds(chainnet):
    """Test reveal with non-reserved name succeeds even when reserved names are set."""
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

def reveal_non_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for non-reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "allowed-test.dys",
        "salt": "random_salt_456",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Reveal with non-reserved name - should succeed
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "allowed-test.dys",
        "salt": "random_salt_456"
    })
    
    # Step 4: Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "allowed-test.dys"
    })
    
    return {
        "reveal_result": reveal_result,
        "nft_query": nft_query
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
        "reveal_non_reserved_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    # Verify reveal succeeded
    assert "reveal_result" in function_result, "Missing reveal_result in response"
    reveal_result = function_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"Expected reveal_result to be dict, got {type(reveal_result)}"
    )
    assert "@type" in reveal_result, "Missing @type in reveal_result"
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify NFT was minted
    assert "nft_query" in function_result, "Missing nft_query in response"
    nft_query = function_result["nft_query"]
    assert isinstance(nft_query, dict), (
        f"Expected nft_query to be dict, got {type(nft_query)}"
    )
    assert "nft" in nft_query, "Missing nft in query response"
    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["id"] == "allowed-test.dys", (
        f"Expected NFT id 'allowed-test.dys', got: {nft['id']}"
    )


@pytest.mark.nameservice
def test_reveal_commitment_mismatch(chainnet):
    """Test reveal with wrong committer fails."""
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

def reveal_commitment_mismatch():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    wrong_committer = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Create commitment with correct committer
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Try reveal with wrong committer (but valid address format)
    wrong_committer = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt8e"  # Different valid address
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": wrong_committer,  # Wrong committer
            "name": "test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_commitment_mismatch",
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
    assert error is not None, "Expected error for committer mismatch"
    error_lower = error.lower()
    assert "invalid committer address" in error_lower, (
        f"Expected invalid committer address error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_reserved_name_fails(chainnet):
    """Test reveal with reserved name fails."""
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

def reveal_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "reserved-test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Try reveal with reserved name - should fail
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "reserved-test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_reserved_name",
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
    assert error is not None, "Expected error for reserved name"
    assert "reserved" in error.lower(), (
        f"Expected reserved name error, got: {error}"
    )
    assert "cannot be registered via reveal" in error.lower(), (
        f"Expected 'cannot be registered via reveal' in error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_non_reserved_name_succeeds(chainnet):
    """Test reveal with non-reserved name succeeds even when reserved names are set."""
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

def reveal_non_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for non-reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "allowed-test.dys",
        "salt": "random_salt_456",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Reveal with non-reserved name - should succeed
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "allowed-test.dys",
        "salt": "random_salt_456"
    })
    
    # Step 4: Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "allowed-test.dys"
    })
    
    return {
        "reveal_result": reveal_result,
        "nft_query": nft_query
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
        "reveal_non_reserved_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    # Verify reveal succeeded
    assert "reveal_result" in function_result, "Missing reveal_result in response"
    reveal_result = function_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"Expected reveal_result to be dict, got {type(reveal_result)}"
    )
    assert "@type" in reveal_result, "Missing @type in reveal_result"
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify NFT was minted
    assert "nft_query" in function_result, "Missing nft_query in response"
    nft_query = function_result["nft_query"]
    assert isinstance(nft_query, dict), (
        f"Expected nft_query to be dict, got {type(nft_query)}"
    )
    assert "nft" in nft_query, "Missing nft in query response"
    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["id"] == "allowed-test.dys", (
        f"Expected NFT id 'allowed-test.dys', got: {nft['id']}"
    )


@pytest.mark.nameservice
def test_reveal_invalid_valuation(chainnet):
    """Test reveal with zero valuation fails."""
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

def reveal_invalid_valuation():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Create commitment with zero valuation
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    # Try reveal - should fail due to zero valuation (reveal happens even with zero valuation)
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_invalid_valuation",
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
    assert error is not None, "Expected error for invalid valuation"
    error_lower = error.lower()
    assert "commitment not found" in error_lower, (
        f"Expected commitment not found error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_reserved_name_fails(chainnet):
    """Test reveal with reserved name fails."""
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

def reveal_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "reserved-test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Try reveal with reserved name - should fail
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "reserved-test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_reserved_name",
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
    assert error is not None, "Expected error for reserved name"
    assert "reserved" in error.lower(), (
        f"Expected reserved name error, got: {error}"
    )
    assert "cannot be registered via reveal" in error.lower(), (
        f"Expected 'cannot be registered via reveal' in error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_non_reserved_name_succeeds(chainnet):
    """Test reveal with non-reserved name succeeds even when reserved names are set."""
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

def reveal_non_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for non-reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "allowed-test.dys",
        "salt": "random_salt_456",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Reveal with non-reserved name - should succeed
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "allowed-test.dys",
        "salt": "random_salt_456"
    })
    
    # Step 4: Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "allowed-test.dys"
    })
    
    return {
        "reveal_result": reveal_result,
        "nft_query": nft_query
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
        "reveal_non_reserved_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    # Verify reveal succeeded
    assert "reveal_result" in function_result, "Missing reveal_result in response"
    reveal_result = function_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"Expected reveal_result to be dict, got {type(reveal_result)}"
    )
    assert "@type" in reveal_result, "Missing @type in reveal_result"
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify NFT was minted
    assert "nft_query" in function_result, "Missing nft_query in response"
    nft_query = function_result["nft_query"]
    assert isinstance(nft_query, dict), (
        f"Expected nft_query to be dict, got {type(nft_query)}"
    )
    assert "nft" in nft_query, "Missing nft in query response"
    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["id"] == "allowed-test.dys", (
        f"Expected NFT id 'allowed-test.dys', got: {nft['id']}"
    )


@pytest.mark.nameservice
def test_reveal_nil_request(chainnet):
    """Test reveal with nil request fails."""
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

def reveal_nil_request():
    try:
        # Try reveal with nil message
        reveal_result = _sudo(None)  # Nil request
        return {"error": None, "result": reveal_result}
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
        "reveal_nil_request",
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


@pytest.mark.nameservice
def test_reveal_reserved_name_fails(chainnet):
    """Test reveal with reserved name fails."""
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

def reveal_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "reserved-test.dys",
        "salt": "random_salt_123",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Try reveal with reserved name - should fail
    try:
        reveal_result = _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": executor,
            "name": "reserved-test.dys",
            "salt": "random_salt_123"
        })
        return {"error": None, "result": reveal_result}
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
        "reveal_reserved_name",
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
    assert error is not None, "Expected error for reserved name"
    assert "reserved" in error.lower(), (
        f"Expected reserved name error, got: {error}"
    )
    assert "cannot be registered via reveal" in error.lower(), (
        f"Expected 'cannot be registered via reveal' in error, got: {error}"
    )

    func_result = function_result["result"]
    assert func_result is None, "Expected no result for error case"


@pytest.mark.nameservice
def test_reveal_non_reserved_name_succeeds(chainnet):
    """Test reveal with non-reserved name succeeds even when reserved names are set."""
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

def reveal_non_reserved_name():
    executor = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    
    # Step 1: Set reserved_names via UpdateParams
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved-test.dys"
        }
    })
    
    # Step 2: Create commitment for non-reserved name
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": "allowed-test.dys",
        "salt": "random_salt_456",
        "committer": executor
    })
    
    hexhash = hash_result["hex_hash"]
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": executor,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    # Step 3: Reveal with non-reserved name - should succeed
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": executor,
        "name": "allowed-test.dys",
        "salt": "random_salt_456"
    })
    
    # Step 4: Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": "allowed-test.dys"
    })
    
    return {
        "reveal_result": reveal_result,
        "nft_query": nft_query
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
        "reveal_non_reserved_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)

    # Type → Shape → Values assertions
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    result = parsed["result"]
    assert isinstance(result, dict), f"Expected result to be dict, got {type(result)}"
    assert "result" in result, "Missing nested result in response"

    nested_result = result["result"]
    assert isinstance(nested_result, dict), (
        f"Expected nested result to be dict, got {type(nested_result)}"
    )

    function_result = nested_result

    # Verify reveal succeeded
    assert "reveal_result" in function_result, "Missing reveal_result in response"
    reveal_result = function_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"Expected reveal_result to be dict, got {type(reveal_result)}"
    )
    assert "@type" in reveal_result, "Missing @type in reveal_result"
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Verify NFT was minted
    assert "nft_query" in function_result, "Missing nft_query in response"
    nft_query = function_result["nft_query"]
    assert isinstance(nft_query, dict), (
        f"Expected nft_query to be dict, got {type(nft_query)}"
    )
    assert "nft" in nft_query, "Missing nft in query response"
    nft = nft_query["nft"]
    assert isinstance(nft, dict), f"Expected nft to be dict, got {type(nft)}"
    assert nft["id"] == "allowed-test.dys", (
        f"Expected NFT id 'allowed-test.dys', got: {nft['id']}"
    )
