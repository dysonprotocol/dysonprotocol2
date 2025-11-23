"""
Test SetNFTClassAllowedDenoms message handler for nameservice keeper.

Tests the SetNFTClassAllowedDenoms functionality which allows name owners to set
the allowed denominations for NFT class bidding.
"""

import json
import secrets
import pytest
from deep_parse import deep_parse


BASE_EXTRA_CODE = r"""
from dys import _msg, _query, get_executor_address
import re


def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })


def _parse_coin(value):
    match = re.fullmatch(r"(\d+)([a-zA-Z0-9./_]+)", value)
    if not match:
        raise Exception("invalid coin value: " + str(value))
    return {"denom": match.group(2), "amount": match.group(1)}


def _register_root_name(name, owner):
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
        "destination": owner,
    })

    return name


def demo_set_allowed_denoms_success(class_id, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register name and create NFT class
    _register_root_name(class_id, owner)

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "https://example.com/collection",
        "name_destination": owner,
    })

    # Mint coins to create supply for test denoms
    test_denom1 = class_id + "/token1"
    test_denom2 = class_id + "/token2"

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": [
            {"denom": test_denom1, "amount": "1000"},
            {"denom": test_denom2, "amount": "2000"}
        ],
        "mint_fee": {"denom": "udys", "amount": "30"},
    })

    # Set allowed denoms including udys (which has supply) and our custom denoms
    allowed_denoms = ["udys", test_denom1, test_denom2]
    set_denoms_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassAllowedDenoms",
        "name_destination": owner,
        "class_id": class_id,
        "allowed_denoms": allowed_denoms,
    })

    # Query the updated class data to verify
    class_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": class_id,
    })

    return {
        "set_denoms_result": set_denoms_result,
        "class_data": class_query,
        "allowed_denoms": allowed_denoms,
    }


def demo_set_allowed_denoms_empty_list(class_id, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register name and create NFT class
    _register_root_name(class_id, owner)

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "https://example.com/collection",
        "name_destination": owner,
    })

    # Try to set empty allowed denoms list - should fail
    set_denoms_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassAllowedDenoms",
        "name_destination": owner,
        "class_id": class_id,
        "allowed_denoms": [],
    })

    return {"set_denoms_result": set_denoms_result}


def demo_set_allowed_denoms_unauthorized(class_id, owner, unauthorized_owner, alice_addr):
    # Fund test accounts from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": unauthorized_owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register name and create NFT class
    _register_root_name(class_id, owner)

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "https://example.com/collection",
        "name_destination": owner,
    })

    # Mint coins to create supply for test denom
    test_denom = class_id + "/token1"
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": [{"denom": test_denom, "amount": "1000"}],
        "mint_fee": {"denom": "udys", "amount": "30"},
    })

    # Try to set allowed denoms with unauthorized owner - should fail
    set_denoms_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassAllowedDenoms",
        "name_destination": unauthorized_owner,
        "class_id": class_id,
        "allowed_denoms": ["udys", test_denom],
    })

    return {"set_denoms_result": set_denoms_result}


def demo_set_allowed_denoms_no_supply(class_id, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register name and create NFT class
    _register_root_name(class_id, owner)

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test NFT Collection",
        "uri": "https://example.com/collection",
        "name_destination": owner,
    })

    # Try to set allowed denoms with a denom that has no supply - should fail
    nonexistent_denom = "nonexistent-token.dys"
    set_denoms_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassAllowedDenoms",
        "name_destination": owner,
        "class_id": class_id,
        "allowed_denoms": ["udys", nonexistent_denom],
    })

    return {"set_denoms_result": set_denoms_result}
"""


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_set_allowed_denoms_success(chainnet):
    """Test successfully setting allowed denoms for an NFT class."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x111111")

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "alice_addr": alice_addr,
    })

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_set_allowed_denoms_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate
    parsed = deep_parse(result)
    assert (
        result.get("exception") is None
    ), f"Script exception: {json.dumps(result.get('exception'), indent=2)}"
    script_result = parsed["result"]["result"]

    # Verify SetNFTClassAllowedDenoms succeeded
    assert (
        script_result["set_denoms_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTClassAllowedDenoms failed: {script_result['set_denoms_result']}"

    # Verify the allowed denoms were set correctly
    class_data = script_result["class_data"]
    assert "class" in class_data, f"Class data missing: {class_data}"
    nft_class_data = class_data["class"]["data"]

    assert "allowed_denoms" in nft_class_data, f"Allowed denoms missing from class data: {nft_class_data}"
    actual_denoms = nft_class_data["allowed_denoms"]
    expected_denoms = script_result["allowed_denoms"]

    assert actual_denoms == expected_denoms, f"Expected allowed denoms {expected_denoms}, got {actual_denoms}"


def test_set_allowed_denoms_empty_list(chainnet):
    """Test setting allowed denoms with empty list fails."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x222222")

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "alice_addr": alice_addr,
    })

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_set_allowed_denoms_empty_list",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "allowed_denoms list cannot be empty" error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for empty allowed denoms list"
    exception_msg = result["exception"]["msg"]
    assert (
        "allowed_denoms list cannot be empty" in exception_msg
    ), f"Expected 'allowed_denoms list cannot be empty' in error message: {exception_msg}"


def test_set_allowed_denoms_unauthorized(chainnet):
    """Test setting allowed denoms with unauthorized owner fails."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x333333")
    unauthorized_owner = get_test_address(dysond, "0x444444")

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "unauthorized_owner": unauthorized_owner,
        "alice_addr": alice_addr,
    })

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_set_allowed_denoms_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "unauthorized" error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for unauthorized access"
    exception_msg = result["exception"]["msg"]
    assert (
        "unauthorized" in exception_msg
    ), f"Expected 'unauthorized' in error message: {exception_msg}"


def test_set_allowed_denoms_no_supply(chainnet):
    """Test setting allowed denoms with denom that has no supply fails."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x555555")

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "alice_addr": alice_addr,
    })

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_set_allowed_denoms_no_supply",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "denom has no current supply" error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for denom without supply"
    exception_msg = result["exception"]["msg"]
    assert (
        "denom has no current supply" in exception_msg
    ), f"Expected 'denom has no current supply' in error message: {exception_msg}"
