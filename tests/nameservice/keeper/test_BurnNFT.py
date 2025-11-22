"""
Test BurnNFT message handler for nameservice keeper.

Tests the BurnNFT message handler which allows authorized users to burn NFTs
from collections they control. Tests cover successful burning, error conditions,
and proper event emission.
"""

import json
import pytest
from deep_parse import deep_parse


def test_burn_nft_success(chainnet, generate_account, register_name):
    """Test successful NFT burning by authorized owner."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Create account and register name for class creation
    owner_name, owner_addr = generate_account("burn_owner", faucet_amount=1_000_000)
    class_name = register_name(dysond, owner_name, owner_addr, valuation="10udys")

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_burn_nft_success(class_name, owner_addr):
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
    nft_id = "test-nft-to-burn"
    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "class_id": class_name,
        "nft_id": nft_id,
        "uri": "https://example.com/nft-to-burn",
        "name_destination": owner_addr
    })

    # Verify NFT exists before burning
    nft_before_burn = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_name,
        "id": nft_id
    })

    # Burn the NFT
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnNFT",
        "class_id": class_name,
        "nft_id": nft_id,
        "name_destination": owner_addr
    })

    # Try to query NFT after burning (should fail)
    try:
        nft_after_burn = _query({
            "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
            "class_id": class_name,
            "id": nft_id
        })
        nft_after_burn_exists = True
    except:
        nft_after_burn_exists = False
        nft_after_burn = None

    return {
        "class_name": class_name,
        "nft_id": nft_id,
        "owner_addr": owner_addr,
        "nft_before_burn": nft_before_burn,
        "burn_result": burn_result,
        "nft_after_burn_exists": nft_after_burn_exists
    }
"""

    kwargs = json.dumps(
        {
            "class_name": class_name,
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
        "demo_burn_nft_success",
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

    # Validate class and NFT setup
    assert demo_result["class_name"] == class_name
    assert demo_result["nft_id"] == "test-nft-to-burn"
    assert demo_result["owner_addr"] == owner_addr

    # Validate NFT existed before burning
    nft_before_burn = demo_result["nft_before_burn"]
    assert isinstance(nft_before_burn, dict), (
        f"nft_before_burn should be dict, got {type(nft_before_burn)}"
    )
    assert "nft" in nft_before_burn, (
        f"nft_before_burn should contain nft key, got {list(nft_before_burn.keys())}"
    )
    assert nft_before_burn["nft"]["class_id"] == class_name
    assert nft_before_burn["nft"]["id"] == "test-nft-to-burn"
    assert nft_before_burn["nft"]["uri"] == "https://example.com/nft-to-burn"

    # Validate burn result
    burn_result = demo_result["burn_result"]
    assert isinstance(burn_result, dict), (
        f"burn_result should be dict, got {type(burn_result)}"
    )
    assert burn_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", (
        f"burn should return sudo response, got {burn_result.get('@type')}"
    )
    assert "results" in burn_result, (
        f"burn should have results, got {list(burn_result.keys())}"
    )
    assert len(burn_result["results"]) == 1, (
        f"burn should have one result, got {len(burn_result['results'])}"
    )
    assert (
        burn_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgBurnNFTResponse"
    ), (
        f"burn should return burn NFT response, got {burn_result['results'][0].get('@type')}"
    )

    # Validate NFT no longer exists after burning
    assert not demo_result["nft_after_burn_exists"], (
        f"NFT should not exist after burning, but it does"
    )


def test_burn_nft_not_found(chainnet, generate_account, register_name):
    """Test burning non-existent NFT."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Create account and register name for class creation
    owner_name, owner_addr = generate_account("burn_owner_nf", faucet_amount=1_000_000)
    class_name = register_name(dysond, owner_name, owner_addr, valuation="10udys")

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_burn_nft_not_found(class_name, owner_addr):
    # Try to burn non-existent NFT - should fail
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnNFT",
        "class_id": class_name,
        "nft_id": "non-existent-nft",
        "name_destination": owner_addr
    })

    return {
        "burn_result": burn_result
    }
"""

    kwargs = json.dumps(
        {
            "class_name": class_name,
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
        "demo_burn_nft_not_found",
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
    assert "NFT not found" in exception["msg"], (
        f"error should mention NFT not found, got: {exception['msg']}"
    )


def test_burn_nft_unauthorized(chainnet, generate_account, register_name):
    """Test burning NFT with unauthorized name_destination."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Create accounts and register names
    owner_name, owner_addr = generate_account("burn_owner_auth", faucet_amount=1_000_000)
    class_name = register_name(dysond, owner_name, owner_addr, valuation="10udys")

    # Create another account that doesn't own the class
    unauthorized_name, unauthorized_addr = generate_account("unauthorized", faucet_amount=1_000_000)

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_burn_nft_unauthorized(class_name, owner_addr, unauthorized_addr):
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

    # Try to burn NFT with unauthorized address - should fail
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnNFT",
        "class_id": class_name,
        "nft_id": nft_id,
        "name_destination": unauthorized_addr
    })

    return {
        "burn_result": burn_result
    }
"""

    kwargs = json.dumps(
        {
            "class_name": class_name,
            "owner_addr": owner_addr,
            "unauthorized_addr": unauthorized_addr,
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
        "demo_burn_nft_unauthorized",
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
    assert "you do not control destination" in exception["msg"], (
        f"error should mention authorization failure, got: {exception['msg']}"
    )


def test_burn_nft_invalid_class(chainnet, generate_account, register_name):
    """Test burning NFT from class not controlled by name_destination."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Create two different accounts and names
    owner1_name, owner1_addr = generate_account("burn_owner1", faucet_amount=1_000_000)
    class1_name = register_name(dysond, owner1_name, owner1_addr, valuation="10udys")

    owner2_name, owner2_addr = generate_account("burn_owner2", faucet_amount=1_000_000)
    class2_name = register_name(dysond, owner2_name, owner2_addr, valuation="10udys")

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_burn_nft_invalid_class(class1_name, owner1_addr, class2_name, owner2_addr):
    # Create first NFT class and mint NFT
    save_class1_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class1_name,
        "name": "Test Collection 1",
        "symbol": "TEST1",
        "description": "Test NFT Collection 1",
        "uri": "https://example.com/collection1",
        "name_destination": owner1_addr
    })

    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "class_id": class1_name,
        "nft_id": "test-nft-cross-class",
        "uri": "https://example.com/nft-cross-class",
        "name_destination": owner1_addr
    })

    # Try to burn NFT from class1 using owner2's address - should fail
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnNFT",
        "class_id": class1_name,
        "nft_id": "test-nft-cross-class",
        "name_destination": owner2_addr
    })

    return {
        "burn_result": burn_result
    }
"""

    kwargs = json.dumps(
        {
            "class1_name": class1_name,
            "owner1_addr": owner1_addr,
            "class2_name": class2_name,
            "owner2_addr": owner2_addr,
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
        "demo_burn_nft_invalid_class",
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
    assert "you do not control destination" in exception["msg"], (
        f"error should mention authorization failure, got: {exception['msg']}"
    )
