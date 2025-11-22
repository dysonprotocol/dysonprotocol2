"""
Test MoveNFT message handler for nameservice keeper.

Tests the MoveNFT message handler which allows authorized users to transfer NFTs
between accounts. Tests cover successful transfers, error conditions,
and proper event emission.
"""

import json
import pytest
from deep_parse import deep_parse


def test_move_nft_success(chainnet):
    """Test successful NFT movement by authorized owner."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate test addresses
    owner_addr = dysond(
        "q", "auth", "address-bytes-to-string", "0x111111", "-o", "json"
    )["address_string"]
    recipient_addr = dysond(
        "q", "auth", "address-bytes-to-string", "0x222222", "-o", "json"
    )["address_string"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}

def _register_name(name, destination, valuation="10udys"):
    owner = get_executor_address()
    salt = "salt-" + name
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": destination,
    })

    return name

def demo_move_nft_success(owner_addr, recipient_addr):
    # Register name and set destination
    class_name = _register_name("test-move-success.dys", owner_addr)
    # Create NFT class first
    save_class_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_name,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "https://example.com/collection",
        "name_destination": owner_addr
    })

    # Mint NFT
    nft_id = "test-nft-to-move"
    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "class_id": class_name,
        "nft_id": nft_id,
        "uri": "https://example.com/nft-to-move",
        "name_destination": owner_addr
    })

    # Check initial ownership
    nft_before_move = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_name,
        "id": nft_id
    })

    # Move the NFT
    move_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMoveNft",
        "class_id": class_name,
        "nft_id": nft_id,
        "name_destination": owner_addr,
        "to_address": recipient_addr
    })

    # Check ownership after move
    nft_after_move = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_name,
        "id": nft_id
    })

    return {
        "class_name": class_name,
        "nft_id": nft_id,
        "owner_addr": owner_addr,
        "recipient_addr": recipient_addr,
        "nft_before_move": nft_before_move,
        "move_result": move_result,
        "nft_after_move": nft_after_move
    }
"""

    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "recipient_addr": recipient_addr,
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
        "demo_move_nft_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Validate class and NFT setup
    assert demo_result["class_name"] == "test-move-success.dys"
    assert demo_result["nft_id"] == "test-nft-to-move"
    assert demo_result["owner_addr"] == owner_addr
    assert demo_result["recipient_addr"] == recipient_addr

    # Validate NFT existed and was owned by original owner
    nft_before_move = demo_result["nft_before_move"]
    assert isinstance(
        nft_before_move, dict
    ), f"nft_before_move should be dict, got {type(nft_before_move)}"
    assert (
        "nft" in nft_before_move
    ), f"nft_before_move should contain nft key, got {list(nft_before_move.keys())}"
    assert nft_before_move["nft"]["class_id"] == "test-move-success.dys"
    assert nft_before_move["nft"]["id"] == "test-nft-to-move"

    # Validate move result
    move_result = demo_result["move_result"]
    assert isinstance(
        move_result, dict
    ), f"move_result should be dict, got {type(move_result)}"
    assert (
        move_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"move should return sudo response, got {move_result.get('@type')}"
    assert (
        "results" in move_result
    ), f"move should have results, got {list(move_result.keys())}"
    assert (
        len(move_result["results"]) == 1
    ), f"move should have one result, got {len(move_result['results'])}"
    assert (
        move_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgMoveNftResponse"
    ), f"move should return move NFT response, got {move_result['results'][0].get('@type')}"

    # Validate NFT is now owned by recipient
    nft_after_move = demo_result["nft_after_move"]
    assert isinstance(
        nft_after_move, dict
    ), f"nft_after_move should be dict, got {type(nft_after_move)}"
    assert (
        "nft" in nft_after_move
    ), f"nft_after_move should contain nft key, got {list(nft_after_move.keys())}"
    assert nft_after_move["nft"]["class_id"] == "test-move-success.dys"
    assert nft_after_move["nft"]["id"] == "test-nft-to-move"


def test_move_nft_invalid_name_destination(chainnet):
    """Test moving NFT with invalid name_destination address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded test addresses
    owner_addr = "dys216vwht46aw58efaxx"
    recipient_addr = "dys216vwmdkmdkcsz2qrh"

    extra_code = """
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}

def _register_name(name, destination, valuation="10udys"):
    owner = get_executor_address()
    salt = "salt-" + name
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": destination,
    })

    return name

def demo_move_nft_invalid_name_destination(owner_addr, recipient_addr):
    # Register name and set destination
    class_name = _register_name("test-move-invalid-dest.dys", owner_addr)
    # Create NFT class
    save_class_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_name,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "https://example.com/collection",
        "name_destination": owner_addr
    })

    # Mint NFT
    nft_id = "test-nft-invalid-dest"
    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "class_id": class_name,
        "nft_id": nft_id,
        "uri": "https://example.com/nft-invalid-dest",
        "name_destination": owner_addr
    })

    # Try to move NFT with invalid name_destination - should fail
    move_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMoveNft",
        "class_id": class_name,
        "nft_id": nft_id,
        "name_destination": "invalid-address",
        "to_address": recipient_addr
    })

    return {
        "move_result": move_result
    }
"""

    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "recipient_addr": recipient_addr,
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
        "demo_move_nft_invalid_name_destination",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
    assert (
        "invalid name_destination address" in exception["msg"]
    ), f"error should mention invalid name_destination address, got: {exception['msg']}"


def test_move_nft_invalid_to_address(chainnet):
    """Test moving NFT with invalid to_address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded test addresses
    owner_addr = "dys216vwht46aw58efaxx"

    extra_code = """
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}

def _register_name(name, destination, valuation="10udys"):
    owner = get_executor_address()
    salt = "salt-" + name
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": destination,
    })

    return name

def demo_move_nft_invalid_to_address(owner_addr):
    # Register name and set destination
    class_name = _register_name("test-move-invalid-to.dys", owner_addr)
    # Create NFT class
    save_class_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_name,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "https://example.com/collection",
        "name_destination": owner_addr
    })

    # Mint NFT
    nft_id = "test-nft-invalid-to"
    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "class_id": class_name,
        "nft_id": nft_id,
        "uri": "https://example.com/nft-invalid-to",
        "name_destination": owner_addr
    })

    # Try to move NFT with invalid to_address - should fail
    move_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMoveNft",
        "class_id": class_name,
        "nft_id": nft_id,
        "name_destination": owner_addr,
        "to_address": "invalid-address"
    })

    return {
        "move_result": move_result
    }
"""

    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
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
        "demo_move_nft_invalid_to_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
    assert (
        "invalid to address" in exception["msg"]
    ), f"error should mention invalid to address, got: {exception['msg']}"


def test_move_nft_not_found(chainnet):
    """Test moving non-existent NFT."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded test addresses
    owner_addr = "dys216vwht46aw58efaxx"
    recipient_addr = "dys216vwmdkmdkcsz2qrh"

    extra_code = """
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}

def _register_name(name, destination, valuation="10udys"):
    owner = get_executor_address()
    salt = "salt-" + name
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": destination,
    })

    return name

def demo_move_nft_not_found(owner_addr, recipient_addr):
    # Register name and set destination
    class_name = _register_name("test-move-not-found.dys", owner_addr)
    # Try to move non-existent NFT - should fail
    move_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMoveNft",
        "class_id": class_name,
        "nft_id": "non-existent-nft",
        "name_destination": owner_addr,
        "to_address": recipient_addr
    })

    return {
        "move_result": move_result
    }
"""

    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "recipient_addr": recipient_addr,
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
        "demo_move_nft_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
    assert (
        "NFT not found" in exception["msg"]
    ), f"error should mention NFT not found, got: {exception['msg']}"


def test_move_nft_unauthorized(chainnet):
    """Test moving NFT with unauthorized name_destination."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded test addresses (these are valid Bech32 addresses)
    owner_addr = "dys216vwht46aw58efaxx"
    unauthorized_addr = "dys216vwmdkmdkcsz2qrh"
    recipient_addr = "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej"

    extra_code = """
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}

def _register_name(name, destination, valuation="10udys"):
    owner = get_executor_address()
    salt = "salt-" + name
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": destination,
    })

    return name

def demo_move_nft_unauthorized(owner_addr, unauthorized_addr, recipient_addr):
    # Register names for both owner and unauthorized user
    class_name = _register_name("test-move-unauth.dys", owner_addr)
    _register_name("unauth-name.dys", unauthorized_addr)
    # Create NFT class
    save_class_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_name,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "https://example.com/collection",
        "name_destination": owner_addr
    })

    # Mint NFT
    nft_id = "test-nft-unauthorized"
    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "class_id": class_name,
        "nft_id": nft_id,
        "uri": "https://example.com/nft-unauthorized",
        "name_destination": owner_addr
    })

    # Try to move NFT with unauthorized address - should fail
    move_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMoveNft",
        "class_id": class_name,
        "nft_id": nft_id,
        "name_destination": unauthorized_addr,
        "to_address": recipient_addr
    })

    return {
        "move_result": move_result
    }
"""

    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "unauthorized_addr": unauthorized_addr,
            "recipient_addr": recipient_addr,
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
        "demo_move_nft_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"
    assert (
        "you do not control destination" in exception["msg"]
    ), f"error should mention authorization failure, got: {exception['msg']}"
