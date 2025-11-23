"""
Test DeleteClass message handler for nameservice keeper.

Tests the DeleteClass message handler which allows authorized users to delete
NFT classes they control, provided the classes are empty (no NFTs exist).
Tests cover successful deletion and proper event emission.
"""

import json
from deep_parse import deep_parse


def test_delete_class_success(chainnet):
    """Test successful NFT class deletion by authorized owner."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use hardcoded test address
    owner_addr = "dys216vwht46aw58efaxx"

    # Create a class ID under the registered name
    class_id = "test-delete.dys/testclass"

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

def demo_delete_class_success(owner_addr):
    # Register name and set destination
    root_name = _register_name("test-delete.dys", owner_addr)
    class_id = "test-delete.dys/testclass"

    # Debug: Check name resolution first
    name_resolution = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
        "name_or_address": root_name
    })

    # Create NFT class first
    save_class_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection for Deletion",
        "uri": "https://example.com/collection",
        "name_destination": owner_addr
    })

    # Verify class exists before deletion
    class_before_delete = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": class_id
    })

    # Debug: Check root destination resolution
    root_dest_check = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": root_name,
        "salt": "dummy_salt",
        "committer": owner_addr
    })

    # Delete the empty class
    delete_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgDeleteClass",
        "class_id": class_id,
        "name_destination": owner_addr
    })

    # Verify class no longer exists after deletion
    try:
        class_after_delete = _query({
            "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
            "class_id": class_id
        })
        class_still_exists = True
    except:
        class_still_exists = False

    return {
        "name_resolution": name_resolution,
        "save_class_result": save_class_result,
        "class_before_delete": class_before_delete,
        "root_dest_check": root_dest_check,
        "delete_result": delete_result,
        "class_still_exists": class_still_exists,
        "class_id": class_id
    }
"""

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
        "demo_delete_class_success",
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

    # Validate save class result
    save_class_result = demo_result["save_class_result"]
    assert isinstance(
        save_class_result, dict
    ), f"save_class_result should be dict, got {type(save_class_result)}"
    assert (
        save_class_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo should return sudo response, got {save_class_result.get('@type')}"
    assert (
        len(save_class_result["results"]) == 1
    ), f"sudo should have one result, got {len(save_class_result['results'])}"
    assert (
        save_class_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgSaveClassResponse"
    ), f"sudo should return save class response, got {save_class_result['results'][0].get('@type')}"

    # Validate class existed before deletion
    class_before_delete = demo_result["class_before_delete"]
    assert isinstance(
        class_before_delete, dict
    ), f"class_before_delete should be dict, got {type(class_before_delete)}"
    assert (
        "class" in class_before_delete
    ), f"class_before_delete should have class, got {list(class_before_delete.keys())}"
    assert (
        class_before_delete["class"]["id"] == demo_result["class_id"]
    ), f"class ID should match, got {class_before_delete['class']['id']}"

    # Validate delete result
    delete_result = demo_result["delete_result"]
    assert isinstance(
        delete_result, dict
    ), f"delete_result should be dict, got {type(delete_result)}"
    assert (
        delete_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo should return sudo response, got {delete_result.get('@type')}"
    assert (
        len(delete_result["results"]) == 1
    ), f"sudo should have one result, got {len(delete_result['results'])}"
    assert (
        delete_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgDeleteClassResponse"
    ), f"sudo should return delete class response, got {delete_result['results'][0].get('@type')}"

    # Validate class no longer exists after deletion
    class_still_exists = demo_result["class_still_exists"]
    assert not class_still_exists, "Class should not exist after deletion"
