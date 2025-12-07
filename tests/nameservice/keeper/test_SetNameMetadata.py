import json
import pytest

from deep_parse import deep_parse


def test_set_name_metadata_success(chainnet):
    """Test successful name metadata setting by owner."""
    dysond = chainnet[0]
    # Use a funded address from genesis
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
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

def _register_root_name(name, owner):
    # Get a valid commitment hash using ComputeHash
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": "test_salt_123",
        "committer": owner
    })
    
    hexhash = hash_result["hex_hash"]
    
    # Register a root name via reveal
    commit_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": "test_salt_123"
    })
    
    return {
        "commit_result": commit_result,
        "reveal_result": reveal_result
    }

def demo_set_name_metadata(name, owner, metadata):
    # First register the name
    register_result = _register_root_name(name, owner)
    
    # Then set metadata as owner
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNameMetadata",
        "owner": owner,
        "name": name,
        "metadata": metadata
    })
    
    return {
        "register_result": register_result,
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps(
        {
            "name": "mytestname.dys",
            "owner": owner_addr,
            "metadata": "https://example.com/metadata.json",
        }
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
        "demo_set_name_metadata",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(result, dict), (
        f"deep_parse should return dict. Got: {type(result)}"
    )
    assert "result" in result, (
        f"result missing 'result' key. Keys: {list(result.keys())}"
    )

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), (
        f"demo_result should be dict, got {type(demo_result)}"
    )

    # Validate register result
    register_result = demo_result["register_result"]
    assert isinstance(register_result, dict), (
        f"register_result should be dict, got {type(register_result)}"
    )
    reveal_result = register_result["reveal_result"]
    assert isinstance(reveal_result, dict), (
        f"reveal_result should be dict, got {type(reveal_result)}"
    )
    assert reveal_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", (
        f"reveal should return sudo response, got {reveal_result.get('@type')}"
    )
    assert "results" in reveal_result, (
        f"reveal should have results, got {list(reveal_result.keys())}"
    )
    assert len(reveal_result["results"]) == 1, (
        f"reveal should have one result, got {len(reveal_result['results'])}"
    )
    assert (
        reveal_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgRevealResponse"
    ), (
        f"reveal should return reveal response, got {reveal_result['results'][0].get('@type')}"
    )

    # Validate sudo result
    sudo_result = demo_result["sudo_result"]
    assert isinstance(sudo_result, dict), (
        f"sudo_result should be dict, got {type(sudo_result)}"
    )
    assert sudo_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", (
        f"sudo should return sudo response, got {sudo_result.get('@type')}"
    )
    assert "results" in sudo_result, (
        f"sudo should have results, got {list(sudo_result.keys())}"
    )
    assert len(sudo_result["results"]) == 1, (
        f"sudo should have one result, got {len(sudo_result['results'])}"
    )
    assert (
        sudo_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgSetNameMetadataResponse"
    ), (
        f"sudo should return set name metadata response, got {sudo_result['results'][0].get('@type')}"
    )


def test_set_name_metadata_empty_name(chainnet):
    """Test name metadata setting with empty name."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_empty_name(owner, metadata):
    # Try to set metadata with empty name - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNameMetadata",
        "owner": owner,
        "name": "",
        "metadata": metadata
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps(
        {"owner": gov_addr, "metadata": "https://example.com/metadata.json"}
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
        "demo_empty_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(result, dict), (
        f"deep_parse should return dict. Got: {type(result)}"
    )

    assert "exception" in result, (
        f"result should have exception. Keys: {list(result.keys())}"
    )

    exception = result["exception"]
    assert exception["class"] == "DysRuntimeError", (
        f"should be DysRuntimeError, got {exception['class']}"
    )
    assert "name not found" in exception["msg"], (
        f"error should mention name not found, got: {exception['msg']}"
    )


def test_set_name_metadata_name_not_found(chainnet):
    """Test name metadata setting with non-existent name."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_name_not_found(owner, metadata):
    # Try to set metadata for non-existent name - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNameMetadata",
        "owner": owner,
        "name": "nonexistent.dys",
        "metadata": metadata
    })
    
    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps(
        {"owner": gov_addr, "metadata": "https://example.com/metadata.json"}
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
        "demo_name_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(result, dict), (
        f"deep_parse should return dict. Got: {type(result)}"
    )

    assert "exception" in result, (
        f"result should have exception. Keys: {list(result.keys())}"
    )

    exception = result["exception"]
    assert exception["class"] == "DysRuntimeError", (
        f"should be DysRuntimeError, got {exception['class']}"
    )
    assert "name not found" in exception["msg"], (
        f"error should mention name not found, got: {exception['msg']}"
    )


def test_set_name_metadata_unauthorized(chainnet):
    """Test name metadata setting by non-owner."""
    dysond = chainnet[0]
    # Use a funded address from genesis
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
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

def _register_root_name(name, owner):
    # Get a valid commitment hash using ComputeHash
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": "test_salt_123",
        "committer": owner
    })
    
    hexhash = hash_result["hex_hash"]
    
    # Register a root name via reveal
    commit_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })
    
    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": "test_salt_123"
    })
    
    return {
        "commit_result": commit_result,
        "reveal_result": reveal_result
    }

def demo_unauthorized(name, owner, unauthorized_owner, metadata):
    # First register the name with owner
    register_result = _register_root_name(name, owner)
    
    # Then try to set metadata as unauthorized owner - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNameMetadata",
        "owner": unauthorized_owner,
        "name": name,
        "metadata": metadata
    })
    
    return {
        "register_result": register_result,
        "sudo_result": sudo_result
    }
"""

    # Use a random address that's not the owner
    unauthorized_owner = "dyson1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    kwargs = json.dumps(
        {
            "name": "mytestname.dys",
            "owner": owner_addr,
            "unauthorized_owner": unauthorized_owner,
            "metadata": "https://example.com/metadata.json",
        }
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
        "demo_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(result, dict), (
        f"deep_parse should return dict. Got: {type(result)}"
    )

    assert "exception" in result, (
        f"result should have exception. Keys: {list(result.keys())}"
    )

    exception = result["exception"]
    assert exception["class"] == "DysRuntimeError", (
        f"should be DysRuntimeError, got {exception['class']}"
    )
    assert "only the owner can set metadata" in exception["msg"], (
        f"error should mention owner restriction, got: {exception['msg']}"
    )


def test_set_name_metadata_metadata_too_large(chainnet):
    """Test name metadata setting with metadata exceeding 1KB limit."""
    dysond = chainnet[0]
    # Use a funded address from genesis
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    # Create metadata larger than 1KB (1024 bytes limit)
    large_metadata = "x" * 1025  # 1025 characters

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _register_root_name(name, owner):
    # Get a valid commitment hash using ComputeHash
    hash_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": "test_salt_123",
        "committer": owner
    })

    hexhash = hash_result["hex_hash"]

    # Register a root name via reveal
    commit_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "1000000"}
    })

    reveal_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": "test_salt_123"
    })

    return {
        "commit_result": commit_result,
        "reveal_result": reveal_result
    }

def demo_metadata_too_large(name, owner, metadata):
    # First register the name
    register_result = _register_root_name(name, owner)

    # Then try to set metadata that's too large - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNameMetadata",
        "owner": owner,
        "name": name,
        "metadata": metadata
    })

    return {
        "register_result": register_result,
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps(
        {
            "name": "mytestname.dys",
            "owner": owner_addr,
            "metadata": large_metadata,
        }
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
        "demo_metadata_too_large",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(result, dict), (
        f"deep_parse should return dict. Got: {type(result)}"
    )

    assert "exception" in result, (
        f"result should have exception. Keys: {list(result.keys())}"
    )

    exception = result["exception"]
    assert exception["class"] == "DysRuntimeError", (
        f"should be DysRuntimeError, got {exception['class']}"
    )
    assert "invalid NFT data" in exception["msg"], (
        f"error should mention invalid NFT data, got: {exception['msg']}"
    )


def test_set_name_metadata_nil_request(chainnet):
    """Test name metadata setting with nil request."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_nil_request():
    # Try to call with nil message - should fail at framework level
    sudo_result = _sudo(None)

    return {
        "sudo_result": sudo_result
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
        "demo_nil_request",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(result, dict), (
        f"deep_parse should return dict. Got: {type(result)}"
    )

    assert "exception" in result, (
        f"result should have exception. Keys: {list(result.keys())}"
    )

    exception = result["exception"]
    assert exception["class"] == "DysRuntimeError", (
        f"should be DysRuntimeError, got {exception['class']}"
    )
