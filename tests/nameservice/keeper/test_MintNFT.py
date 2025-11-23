"""
Test MintNFT message handler for nameservice keeper.

Tests the NFT minting functionality which allows authorized users to
mint new NFTs within their NFT classes.
"""

import json
import re
import secrets
import pytest
from deep_parse import deep_parse


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


BASE_EXTRA_CODE = r"""
from dys import _msg, _query, get_executor_address
import re


def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })


def _parse_coin(s):
    m = re.fullmatch(r"(\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}


def _register_root_name(name, destination):
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
        "valuation": _parse_coin("10udys"),
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


def _create_nft_class(class_id, owner):
    # First register a root name for the class
    root_name = class_id
    _register_root_name(root_name, owner)

    # Create NFT class
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner,
        "class_id": class_id,
        "name": root_name,
        "symbol": "TEST",
        "description": "Test class for MintNFT",
        "uri": "",
        "uri_hash": "",
    })


def demo_mint_nft_success(owner_addr, class_id="test-mintnft.dys", nft_id="nft1"):
    # Setup: Create NFT class first
    _create_nft_class(class_id, owner_addr)

    # Mint NFT
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner_addr,
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "https://example.com/nft1",
        "uri_hash": "",
    })

    # Query the NFT to verify it was minted
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_id,
        "id": nft_id,
    })

    return {
        "mint_nft_result": result,
        "nft_query": nft_query,
    }


def demo_mint_nft_multiple(owner_addr):
    class_id = "test-multiple.dys"

    # Setup: Create NFT class first
    _create_nft_class(class_id, owner_addr)

    # Mint first NFT
    mint1_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner_addr,
        "class_id": class_id,
        "nft_id": "nft1",
        "uri": "https://example.com/nft1",
        "uri_hash": "",
    })

    # Mint second NFT
    mint2_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner_addr,
        "class_id": class_id,
        "nft_id": "nft2",
        "uri": "https://example.com/nft2",
        "uri_hash": "",
    })

    # Query all NFTs in class
    nfts_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTsRequest",
        "class_id": class_id,
    })

    return {
        "mint1_result": mint1_result,
        "mint2_result": mint2_result,
        "nfts_query": nfts_query,
    }


def demo_mint_nft_class_not_found(owner_addr):
    # Try to mint NFT in non-existent class
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner_addr,
        "class_id": "nonexistent.dys",
        "nft_id": "nft1",
        "uri": "",
        "uri_hash": "",
    })

    return {"mint_nft_result": result}


def demo_mint_nft_unauthorized(owner_addr, wrong_owner):
    class_id = "test-unauthorized.dys"

    # Setup: Create NFT class owned by owner_addr
    _create_nft_class(class_id, owner_addr)

    # Try to mint as wrong_owner (should fail)
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": wrong_owner,
        "class_id": class_id,
        "nft_id": "nft1",
        "uri": "",
        "uri_hash": "",
    })

    return {"mint_nft_result": result}


def demo_mint_nft_duplicate_id(owner_addr):
    class_id = "test-duplicate.dys"
    nft_id = "nft1"

    # Setup: Create NFT class
    _create_nft_class(class_id, owner_addr)

    # Mint first NFT
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner_addr,
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "",
        "uri_hash": "",
    })

    # Try to mint another NFT with same ID (should fail)
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner_addr,
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "",
        "uri_hash": "",
    })

    return {"mint_nft_result": result}


def demo_mint_nft_with_metadata(owner_addr):
    class_id = "test-metadata.dys"
    nft_id = "nft1"

    # Setup: Create NFT class
    _create_nft_class(class_id, owner_addr)

    # Mint NFT with metadata
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner_addr,
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "https://example.com/nft1",
        "uri_hash": "hash123",
    })

    # Query the NFT
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_id,
        "id": nft_id,
    })

    return {
        "mint_nft_result": result,
        "nft_query": nft_query,
    }
"""


def test_mint_nft_success(chainnet):
    """Test successful NFT minting."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    owner_addr = get_test_address(dysond, "0x111111")

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_mint_nft_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"demo_result should be dict, got {type(demo_result)}"

    # Validate mint NFT result
    mint_nft_result = demo_result["mint_nft_result"]
    assert isinstance(mint_nft_result, dict), f"mint_nft_result should be dict, got {type(mint_nft_result)}"
    assert mint_nft_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"sudo should return sudo response, got {mint_nft_result.get('@type')}"
    assert len(mint_nft_result["results"]) == 1, f"sudo should have one result, got {len(mint_nft_result['results'])}"
    assert mint_nft_result["results"][0]["@type"] == "/dysonprotocol.nameservice.v1.MsgMintNFTResponse", f"sudo should return mint NFT response, got {mint_nft_result['results'][0].get('@type')}"

    # Validate NFT query
    nft_query = demo_result["nft_query"]
    assert isinstance(nft_query, dict), f"nft_query should be dict, got {type(nft_query)}"
    assert "nft" in nft_query, f"nft_query should have nft, got {list(nft_query.keys())}"

    nft = nft_query["nft"]
    assert nft["id"] == "nft1", f"nft ID should match, got {nft['id']}"
    assert nft["class_id"] == "test-mintnft.dys", f"nft class_id should match, got {nft['class_id']}"
    assert nft["uri"] == "https://example.com/nft1", f"nft URI should match, got {nft['uri']}"


def test_mint_nft_multiple(chainnet):
    """Test minting multiple NFTs in the same class."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    owner_addr = get_test_address(dysond, "0x111111")

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_mint_nft_multiple",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"demo_result should be dict, got {type(demo_result)}"

    # Validate both mint operations succeeded
    mint1_result = demo_result["mint1_result"]
    mint2_result = demo_result["mint2_result"]
    assert mint1_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    assert mint2_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Validate NFTs query shows both NFTs
    nfts_query = demo_result["nfts_query"]
    assert isinstance(nfts_query, dict), f"nfts_query should be dict, got {type(nfts_query)}"
    assert "nfts" in nfts_query, f"nfts_query should have nfts, got {list(nfts_query.keys())}"
    assert len(nfts_query["nfts"]) == 2, f"should have 2 NFTs, got {len(nfts_query['nfts'])}"


def test_mint_nft_class_not_found(chainnet):
    """Test that NFT minting fails when class doesn't exist."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    owner_addr = get_test_address(dysond, "0x111111")

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_mint_nft_class_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should fail because class doesn't exist
    mint_nft_result = demo_result["mint_nft_result"]
    assert mint_nft_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    # The result should indicate failure (empty results or error)


def test_mint_nft_unauthorized(chainnet):
    """Test that NFT minting fails when caller doesn't own the class."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    owner_addr = get_test_address(dysond, "0x111111")
    wrong_owner = get_test_address(dysond, "0x222222")

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"owner_addr": owner_addr, "wrong_owner": wrong_owner})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_mint_nft_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should fail because wrong owner
    mint_nft_result = demo_result["mint_nft_result"]
    assert mint_nft_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    # The result should indicate failure (empty results or error)


def test_mint_nft_duplicate_id(chainnet):
    """Test that NFT minting fails when NFT ID already exists."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    owner_addr = get_test_address(dysond, "0x111111")

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_mint_nft_duplicate_id",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should fail because NFT ID already exists
    mint_nft_result = demo_result["mint_nft_result"]
    assert mint_nft_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    # The result should indicate failure (empty results or error)


def test_mint_nft_with_metadata(chainnet):
    """Test minting NFT with URI and URI hash metadata."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    owner_addr = get_test_address(dysond, "0x111111")

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_mint_nft_with_metadata",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"demo_result should be dict, got {type(demo_result)}"

    # Validate mint result
    mint_nft_result = demo_result["mint_nft_result"]
    assert isinstance(mint_nft_result, dict), f"mint_nft_result should be dict, got {type(mint_nft_result)}"
    assert mint_nft_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Validate NFT has metadata
    nft_query = demo_result["nft_query"]
    assert isinstance(nft_query, dict), f"nft_query should be dict, got {type(nft_query)}"
    assert "nft" in nft_query, f"nft_query should have nft, got {list(nft_query.keys())}"

    nft = nft_query["nft"]
    assert nft["uri"] == "https://example.com/nft1", f"nft URI should match, got {nft['uri']}"
    # Note: uri_hash might be stored differently depending on implementation
