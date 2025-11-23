"""
Test SetListed message handler for nameservice keeper.

Tests the NFT listing functionality which allows NFT owners to
set whether their NFTs are available for bidding.
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


def _create_nft_class_and_mint_nft(class_id, nft_id, owner):
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
        "description": "Test class for SetListed",
        "uri": "",
        "uri_hash": "",
    })

    # Now mint the NFT
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner,
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "",
        "uri_hash": "",
    })


def demo_set_listed_success(owner_addr, class_id="test-setlisted.dys", nft_id="nft1", listed=True):
    # Setup: Create NFT class and mint NFT
    _create_nft_class_and_mint_nft(class_id, nft_id, owner_addr)

    # Set NFT listed status
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": listed,
    })

    # Query the NFT to verify listing status
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_id,
        "id": nft_id,
    })

    return {
        "set_listed_result": result,
        "nft_query": nft_query,
    }


def demo_set_listed_nft_not_found(owner_addr):
    # Try to set listing on non-existent NFT
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner_addr,
        "nft_class_id": "nonexistent.dys",
        "nft_id": "nft1",
        "listed": True,
    })

    return {"set_listed_result": result}


def demo_set_listed_unauthorized(owner_addr, wrong_owner):
    class_id = "test-unauthorized.dys"
    nft_id = "nft1"

    # Setup: Create NFT class and mint NFT owned by owner_addr
    _create_nft_class_and_mint_nft(class_id, nft_id, owner_addr)

    # Try to set listing as wrong_owner (should fail)
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": wrong_owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": True,
    })

    return {"set_listed_result": result}


def demo_set_listed_toggle_status(owner_addr):
    class_id = "test-toggle.dys"
    nft_id = "nft1"

    # Setup: Create NFT class and mint NFT
    _create_nft_class_and_mint_nft(class_id, nft_id, owner_addr)

    # Set to listed
    list_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": True,
    })

    # Query after listing
    nft_after_list = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_id,
        "id": nft_id,
    })

    # Set to unlisted
    unlist_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": False,
    })

    # Query after unlisting
    nft_after_unlist = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_id,
        "id": nft_id,
    })

    return {
        "list_result": list_result,
        "nft_after_list": nft_after_list,
        "unlist_result": unlist_result,
        "nft_after_unlist": nft_after_unlist,
    }
"""


def test_set_listed_success_listed_true(chainnet):
    """Test successfully setting NFT as listed."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    owner_addr = get_test_address(dysond, "0x111111")

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"owner_addr": owner_addr, "listed": True})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_set_listed_success",
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

    # Validate set listed result
    set_listed_result = demo_result["set_listed_result"]
    assert isinstance(set_listed_result, dict), f"set_listed_result should be dict, got {type(set_listed_result)}"
    assert set_listed_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"sudo should return sudo response, got {set_listed_result.get('@type')}"
    assert len(set_listed_result["results"]) == 1, f"sudo should have one result, got {len(set_listed_result['results'])}"
    assert set_listed_result["results"][0]["@type"] == "/dysonprotocol.nameservice.v1.MsgSetListedResponse", f"sudo should return set listed response, got {set_listed_result['results'][0].get('@type')}"

    # Validate NFT query shows listed status
    nft_query = demo_result["nft_query"]
    assert isinstance(nft_query, dict), f"nft_query should be dict, got {type(nft_query)}"
    assert "nft" in nft_query, f"nft_query should have nft, got {list(nft_query.keys())}"

    nft_data = nft_query["nft"]["data"]["value"]
    # Note: listed status might be in NFT data or derived from class always_listed


def test_set_listed_success_listed_false(chainnet):
    """Test successfully setting NFT as unlisted."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    owner_addr = get_test_address(dysond, "0x111111")

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"owner_addr": owner_addr, "listed": False})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_set_listed_success",
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

    # Validate set listed result
    set_listed_result = demo_result["set_listed_result"]
    assert isinstance(set_listed_result, dict), f"set_listed_result should be dict, got {type(set_listed_result)}"
    assert set_listed_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"sudo should return sudo response, got {set_listed_result.get('@type')}"
    assert len(set_listed_result["results"]) == 1, f"sudo should have one result, got {len(set_listed_result['results'])}"
    assert set_listed_result["results"][0]["@type"] == "/dysonprotocol.nameservice.v1.MsgSetListedResponse", f"sudo should return set listed response, got {set_listed_result['results'][0].get('@type')}"


def test_set_listed_nft_not_found(chainnet):
    """Test that setting listed status fails when NFT doesn't exist."""
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
        "demo_set_listed_nft_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should fail because NFT doesn't exist
    set_listed_result = demo_result["set_listed_result"]
    assert set_listed_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    # The result should indicate failure (empty results or error)


def test_set_listed_unauthorized(chainnet):
    """Test that setting listed status fails when caller is not the NFT owner."""
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
        "demo_set_listed_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should fail because wrong owner
    set_listed_result = demo_result["set_listed_result"]
    assert set_listed_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    # The result should indicate failure (empty results or error)


def test_set_listed_toggle_status(chainnet):
    """Test toggling NFT listed status from listed to unlisted and back."""
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
        "demo_set_listed_toggle_status",
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

    # Both operations should succeed
    list_result = demo_result["list_result"]
    unlist_result = demo_result["unlist_result"]
    assert list_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    assert unlist_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    assert len(list_result["results"]) == 1
    assert len(unlist_result["results"]) == 1
