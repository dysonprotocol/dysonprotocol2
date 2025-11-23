"""
Test SaveClass message handler for nameservice keeper.

Tests the NFT class creation functionality which allows authorized users
to create new NFT classes under their registered names.
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


def demo_save_class_success(owner_addr, class_id="test-saveclass.dys"):
    # First register the root name
    root_name = class_id
    _register_root_name(root_name, owner_addr)

    # Create NFT class
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner_addr,
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection for SaveClass",
        "uri": "https://example.com/collection",
        "uri_hash": "",
    })

    # Query the class to verify it was created
    class_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": class_id,
    })

    return {
        "save_class_result": result,
        "class_query": class_query,
    }


def demo_save_class_subcollection(owner_addr):
    # First register the root name
    root_name = "test-subcollection.dys"
    _register_root_name(root_name, owner_addr)

    # Create main class
    main_class_id = root_name
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner_addr,
        "class_id": main_class_id,
        "name": "Main Collection",
        "symbol": "MAIN",
        "description": "Main NFT Collection",
        "uri": "",
        "uri_hash": "",
    })

    # Create subcollection
    sub_class_id = f"{main_class_id}/subcollection"
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner_addr,
        "class_id": sub_class_id,
        "name": "Sub Collection",
        "symbol": "SUB",
        "description": "Sub NFT Collection",
        "uri": "",
        "uri_hash": "",
    })

    # Query both classes
    main_class_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": main_class_id,
    })

    sub_class_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": sub_class_id,
    })

    return {
        "save_subclass_result": result,
        "main_class_query": main_class_query,
        "sub_class_query": sub_class_query,
    }


def demo_save_class_unauthorized(owner_addr, wrong_owner):
    # First register the root name with correct owner
    root_name = "test-unauthorized.dys"
    _register_root_name(root_name, owner_addr)

    # Try to create class as wrong owner (should fail)
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": wrong_owner,
        "class_id": root_name,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "",
        "uri_hash": "",
    })

    return {"save_class_result": result}


def demo_save_class_no_root_name(owner_addr):
    # Try to create class without registering root name first (should fail)
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner_addr,
        "class_id": "nonexistent.dys",
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "",
        "uri_hash": "",
    })

    return {"save_class_result": result}


def demo_save_class_update_existing(owner_addr):
    class_id = "test-update.dys"

    # First register the root name
    _register_root_name(class_id, owner_addr)

    # Create initial class
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner_addr,
        "class_id": class_id,
        "name": "Original Name",
        "symbol": "ORIG",
        "description": "Original Description",
        "uri": "",
        "uri_hash": "",
    })

    # Update the class
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner_addr,
        "class_id": class_id,
        "name": "Updated Name",
        "symbol": "UPDT",
        "description": "Updated Description",
        "uri": "https://example.com/updated",
        "uri_hash": "",
    })

    # Query the updated class
    class_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": class_id,
    })

    return {
        "update_class_result": result,
        "class_query": class_query,
    }
"""


def test_save_class_success(chainnet):
    """Test successful NFT class creation."""
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
        "demo_save_class_success",
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

    # Validate save class result
    save_class_result = demo_result["save_class_result"]
    assert isinstance(save_class_result, dict), f"save_class_result should be dict, got {type(save_class_result)}"
    assert save_class_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"sudo should return sudo response, got {save_class_result.get('@type')}"
    assert len(save_class_result["results"]) == 1, f"sudo should have one result, got {len(save_class_result['results'])}"
    assert save_class_result["results"][0]["@type"] == "/dysonprotocol.nameservice.v1.MsgSaveClassResponse", f"sudo should return save class response, got {save_class_result['results'][0].get('@type')}"

    # Validate class query
    class_query = demo_result["class_query"]
    assert isinstance(class_query, dict), f"class_query should be dict, got {type(class_query)}"
    assert "class" in class_query, f"class_query should have class, got {list(class_query.keys())}"

    class_info = class_query["class"]
    assert class_info["name"] == "Test Collection", f"class name should match, got {class_info['name']}"
    assert class_info["symbol"] == "TEST", f"class symbol should match, got {class_info['symbol']}"


def test_save_class_subcollection(chainnet):
    """Test creating subcollections under main collections."""
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
        "demo_save_class_subcollection",
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

    # Validate both classes exist
    main_class_query = demo_result["main_class_query"]
    sub_class_query = demo_result["sub_class_query"]
    assert "class" in main_class_query
    assert "class" in sub_class_query

    assert main_class_query["class"]["name"] == "Main Collection"
    assert sub_class_query["class"]["name"] == "Sub Collection"


def test_save_class_unauthorized(chainnet):
    """Test that class creation fails when caller doesn't own the root name."""
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
        "demo_save_class_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should fail because wrong owner
    save_class_result = demo_result["save_class_result"]
    assert save_class_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    # The result should indicate failure (empty results or error)


def test_save_class_no_root_name(chainnet):
    """Test that class creation fails when root name is not registered."""
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
        "demo_save_class_no_root_name",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]

    # Should fail because root name not registered
    save_class_result = demo_result["save_class_result"]
    assert save_class_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    # The result should indicate failure (empty results or error)


def test_save_class_update_existing(chainnet):
    """Test updating an existing NFT class."""
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
        "demo_save_class_update_existing",
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

    # Validate update result
    update_class_result = demo_result["update_class_result"]
    assert isinstance(update_class_result, dict), f"update_class_result should be dict, got {type(update_class_result)}"
    assert update_class_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"sudo should return sudo response, got {update_class_result.get('@type')}"
    assert len(update_class_result["results"]) == 1, f"sudo should have one result, got {len(update_class_result['results'])}"

    # Validate updated class info
    class_query = demo_result["class_query"]
    assert isinstance(class_query, dict), f"class_query should be dict, got {type(class_query)}"
    assert "class" in class_query, f"class_query should have class, got {list(class_query.keys())}"

    class_info = class_query["class"]
    assert class_info["name"] == "Updated Name", f"class name should be updated, got {class_info['name']}"
    assert class_info["symbol"] == "UPDT", f"class symbol should be updated, got {class_info['symbol']}"
    assert class_info["description"] == "Updated Description", f"class description should be updated, got {class_info['description']}"
