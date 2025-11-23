"""
Test SetNFTClassValuationPeriod message handler for nameservice keeper.

Tests the SetNFTClassValuationPeriod functionality which allows name owners to set
the valuation_period field for NFT classes.
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


def demo_set_valuation_period_success(class_id, owner, valuation_period_seconds, alice_addr):
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

    # Set valuation_period field
    set_valuation_period_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassValuationPeriod",
        "name_destination": owner,
        "class_id": class_id,
        "valuation_period": f"{valuation_period_seconds}s",
    })

    # Query the updated class data to verify
    class_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": class_id,
    })

    return {
        "set_valuation_period_result": set_valuation_period_result,
        "class_data": class_query,
        "expected_valuation_period_seconds": valuation_period_seconds,
    }


def demo_set_valuation_period_unauthorized(class_id, owner, unauthorized_owner, alice_addr):
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

    # Try to set valuation_period with unauthorized owner - should fail
    set_valuation_period_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassValuationPeriod",
        "name_destination": unauthorized_owner,
        "class_id": class_id,
        "valuation_period": "3600s",
    })

    return {"set_valuation_period_result": set_valuation_period_result}


def demo_set_valuation_period_class_not_found(class_id, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Try to set valuation_period on non-existent class - should fail
    set_valuation_period_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassValuationPeriod",
        "name_destination": owner,
        "class_id": class_id,
        "valuation_period": "3600s",
    })

    return {"set_valuation_period_result": set_valuation_period_result}


def demo_set_valuation_period_bounds_check(class_id, owner, valuation_period_seconds, alice_addr):
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

    # Try to set valuation_period with value that should be within bounds
    set_valuation_period_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassValuationPeriod",
        "name_destination": owner,
        "class_id": class_id,
        "valuation_period": f"{valuation_period_seconds}s",
    })

    return {
        "set_valuation_period_result": set_valuation_period_result,
        "expected_valuation_period_seconds": valuation_period_seconds,
    }
"""


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_set_valuation_period_success_min_value(chainnet):
    """Test successfully setting valuation_period to minimum allowed value (1 hour = 3600s)."""
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

    # Test with minimum value (1 hour = 3600 seconds)
    valuation_period_seconds = 3600

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "valuation_period_seconds": valuation_period_seconds,
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
        "demo_set_valuation_period_success",
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

    # Verify SetNFTClassValuationPeriod succeeded
    assert (
        script_result["set_valuation_period_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTClassValuationPeriod failed: {script_result['set_valuation_period_result']}"

    # Verify the valuation_period field was set correctly
    class_data = script_result["class_data"]
    assert "class" in class_data, f"Class data missing: {class_data}"
    nft_class_data = class_data["class"]["data"]

    assert "valuation_period" in nft_class_data, f"valuation_period field missing from class data: {nft_class_data}"
    actual_valuation_period = nft_class_data["valuation_period"]
    expected_valuation_period_seconds = script_result["expected_valuation_period_seconds"]

    # Parse the duration string (e.g., "3600s" -> 3600)
    import re
    match = re.match(r"(\d+)s", actual_valuation_period)
    assert match, f"valuation_period format unexpected: {actual_valuation_period}"
    actual_seconds = int(match.group(1))

    assert actual_seconds == expected_valuation_period_seconds, f"Expected valuation_period seconds {expected_valuation_period_seconds}, got {actual_seconds}"


def test_set_valuation_period_success_max_value(chainnet):
    """Test successfully setting valuation_period to maximum allowed value (365 days = 31536000s)."""
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

    # Test with maximum value (365 days = 31536000 seconds)
    valuation_period_seconds = 31536000

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "valuation_period_seconds": valuation_period_seconds,
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
        "demo_set_valuation_period_success",
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

    # Verify SetNFTClassValuationPeriod succeeded
    assert (
        script_result["set_valuation_period_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTClassValuationPeriod failed: {script_result['set_valuation_period_result']}"

    # Verify the valuation_period field was set correctly
    class_data = script_result["class_data"]
    assert "class" in class_data, f"Class data missing: {class_data}"
    nft_class_data = class_data["class"]["data"]

    assert "valuation_period" in nft_class_data, f"valuation_period field missing from class data: {nft_class_data}"
    actual_valuation_period = nft_class_data["valuation_period"]
    expected_valuation_period_seconds = script_result["expected_valuation_period_seconds"]

    # Parse the duration string (e.g., "3600s" -> 3600)
    import re
    match = re.match(r"(\d+)s", actual_valuation_period)
    assert match, f"valuation_period format unexpected: {actual_valuation_period}"
    actual_seconds = int(match.group(1))

    assert actual_seconds == expected_valuation_period_seconds, f"Expected valuation_period seconds {expected_valuation_period_seconds}, got {actual_seconds}"


def test_set_valuation_period_success_mid_value(chainnet):
    """Test successfully setting valuation_period to a middle value (30 days = 2592000s)."""
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

    # Test with middle value (30 days = 2592000 seconds)
    valuation_period_seconds = 2592000

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "valuation_period_seconds": valuation_period_seconds,
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
        "demo_set_valuation_period_success",
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

    # Verify SetNFTClassValuationPeriod succeeded
    assert (
        script_result["set_valuation_period_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTClassValuationPeriod failed: {script_result['set_valuation_period_result']}"

    # Verify the valuation_period field was set correctly
    class_data = script_result["class_data"]
    assert "class" in class_data, f"Class data missing: {class_data}"
    nft_class_data = class_data["class"]["data"]

    assert "valuation_period" in nft_class_data, f"valuation_period field missing from class data: {nft_class_data}"
    actual_valuation_period = nft_class_data["valuation_period"]
    expected_valuation_period_seconds = script_result["expected_valuation_period_seconds"]

    # Parse the duration string (e.g., "3600s" -> 3600)
    import re
    match = re.match(r"(\d+)s", actual_valuation_period)
    assert match, f"valuation_period format unexpected: {actual_valuation_period}"
    actual_seconds = int(match.group(1))

    assert actual_seconds == expected_valuation_period_seconds, f"Expected valuation_period seconds {expected_valuation_period_seconds}, got {actual_seconds}"


def test_set_valuation_period_unauthorized(chainnet):
    """Test setting valuation_period with unauthorized owner fails."""
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
    owner = get_test_address(dysond, "0x444444")
    unauthorized_owner = get_test_address(dysond, "0x555555")

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
        "demo_set_valuation_period_unauthorized",
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
        "unauthorized" in exception_msg.lower()
    ), f"Expected 'unauthorized' in error message: {exception_msg}"


def test_set_valuation_period_class_not_found(chainnet):
    """Test setting valuation_period on non-existent NFT class fails."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"nonexistent{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x666666")

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
        "demo_set_valuation_period_class_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "not found" error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for class not found"
    exception_msg = result["exception"]["msg"]
    assert (
        "not found" in exception_msg.lower()
    ), f"Expected 'not found' in error message: {exception_msg}"
