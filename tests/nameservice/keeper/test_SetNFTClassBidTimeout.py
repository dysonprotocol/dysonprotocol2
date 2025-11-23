"""
Test SetNFTClassBidTimeout message handler for nameservice keeper.

Tests the SetNFTClassBidTimeout functionality which allows name owners to set
the bid_timeout field for NFT classes.
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


def demo_set_bid_timeout_success(class_id, owner, bid_timeout_seconds, alice_addr):
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

    # Set bid_timeout field
    set_bid_timeout_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassBidTimeout",
        "name_destination": owner,
        "class_id": class_id,
        "bid_timeout": f"{bid_timeout_seconds}s",
    })

    # Query the updated class data to verify
    class_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": class_id,
    })

    return {
        "set_bid_timeout_result": set_bid_timeout_result,
        "class_data": class_query,
        "expected_bid_timeout_seconds": bid_timeout_seconds,
    }


def demo_set_bid_timeout_unauthorized(class_id, owner, unauthorized_owner, alice_addr):
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

    # Try to set bid_timeout with unauthorized owner - should fail
    set_bid_timeout_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassBidTimeout",
        "name_destination": unauthorized_owner,
        "class_id": class_id,
        "bid_timeout": "3600s",
    })

    return {"set_bid_timeout_result": set_bid_timeout_result}


def demo_set_bid_timeout_class_not_found(class_id, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register the root name but do NOT create the NFT class
    _register_root_name(class_id, owner)

    # Try to set bid_timeout on non-existent class - should fail at GetNFTClassData
    set_bid_timeout_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassBidTimeout",
        "name_destination": owner,
        "class_id": class_id,
        "bid_timeout": "3600s",
    })

    return {"set_bid_timeout_result": set_bid_timeout_result}


def demo_set_bid_timeout_bounds_check(class_id, owner, bid_timeout_seconds, alice_addr):
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

    # Try to set bid_timeout with value that should be within bounds
    set_bid_timeout_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassBidTimeout",
        "name_destination": owner,
        "class_id": class_id,
        "bid_timeout": f"{bid_timeout_seconds}s",
    })

    return {
        "set_bid_timeout_result": set_bid_timeout_result,
        "expected_bid_timeout_seconds": bid_timeout_seconds,
    }
"""


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_set_bid_timeout_success_min_value(chainnet):
    """Test successfully setting bid_timeout to minimum allowed value (0 seconds)."""
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

    # Test with minimum value (0 seconds)
    bid_timeout_seconds = 0

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "bid_timeout_seconds": bid_timeout_seconds,
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
        "demo_set_bid_timeout_success",
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

    # Verify SetNFTClassBidTimeout succeeded
    assert (
        script_result["set_bid_timeout_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTClassBidTimeout failed: {script_result['set_bid_timeout_result']}"

    # Verify the bid_timeout field was set correctly
    class_data = script_result["class_data"]
    assert "class" in class_data, f"Class data missing: {class_data}"
    nft_class_data = class_data["class"]["data"]

    assert "bid_timeout" in nft_class_data, f"bid_timeout field missing from class data: {nft_class_data}"
    actual_bid_timeout = nft_class_data["bid_timeout"]
    expected_bid_timeout_seconds = script_result["expected_bid_timeout_seconds"]

    # Parse the duration string (e.g., "0s" -> 0)
    import re
    match = re.match(r"(\d+)s", actual_bid_timeout)
    assert match, f"bid_timeout format unexpected: {actual_bid_timeout}"
    actual_seconds = int(match.group(1))

    assert actual_seconds == expected_bid_timeout_seconds, f"Expected bid_timeout seconds {expected_bid_timeout_seconds}, got {actual_seconds}"


def test_set_bid_timeout_success_max_value(chainnet):
    """Test successfully setting bid_timeout to maximum allowed value (90 days = 7776000 seconds)."""
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

    # Test with maximum value (90 days = 7776000 seconds)
    bid_timeout_seconds = 7776000

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "bid_timeout_seconds": bid_timeout_seconds,
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
        "demo_set_bid_timeout_success",
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

    # Verify SetNFTClassBidTimeout succeeded
    assert (
        script_result["set_bid_timeout_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTClassBidTimeout failed: {script_result['set_bid_timeout_result']}"

    # Verify the bid_timeout field was set correctly
    class_data = script_result["class_data"]
    assert "class" in class_data, f"Class data missing: {class_data}"
    nft_class_data = class_data["class"]["data"]

    assert "bid_timeout" in nft_class_data, f"bid_timeout field missing from class data: {nft_class_data}"
    actual_bid_timeout = nft_class_data["bid_timeout"]
    expected_bid_timeout_seconds = script_result["expected_bid_timeout_seconds"]

    # Parse the duration string (e.g., "7776000s" -> 7776000)
    import re
    match = re.match(r"(\d+)s", actual_bid_timeout)
    assert match, f"bid_timeout format unexpected: {actual_bid_timeout}"
    actual_seconds = int(match.group(1))

    assert actual_seconds == expected_bid_timeout_seconds, f"Expected bid_timeout seconds {expected_bid_timeout_seconds}, got {actual_seconds}"


def test_set_bid_timeout_success_mid_value(chainnet):
    """Test successfully setting bid_timeout to a middle value (1 day = 86400 seconds)."""
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

    # Test with middle value (1 day = 86400 seconds)
    bid_timeout_seconds = 86400

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "bid_timeout_seconds": bid_timeout_seconds,
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
        "demo_set_bid_timeout_success",
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

    # Verify SetNFTClassBidTimeout succeeded
    assert (
        script_result["set_bid_timeout_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTClassBidTimeout failed: {script_result['set_bid_timeout_result']}"

    # Verify the bid_timeout field was set correctly
    class_data = script_result["class_data"]
    assert "class" in class_data, f"Class data missing: {class_data}"
    nft_class_data = class_data["class"]["data"]

    assert "bid_timeout" in nft_class_data, f"bid_timeout field missing from class data: {nft_class_data}"
    actual_bid_timeout = nft_class_data["bid_timeout"]
    expected_bid_timeout_seconds = script_result["expected_bid_timeout_seconds"]

    # Parse the duration string (e.g., "86400s" -> 86400)
    import re
    match = re.match(r"(\d+)s", actual_bid_timeout)
    assert match, f"bid_timeout format unexpected: {actual_bid_timeout}"
    actual_seconds = int(match.group(1))

    assert actual_seconds == expected_bid_timeout_seconds, f"Expected bid_timeout seconds {expected_bid_timeout_seconds}, got {actual_seconds}"


def test_set_bid_timeout_unauthorized(chainnet):
    """Test setting bid_timeout with unauthorized owner fails."""
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
        "demo_set_bid_timeout_unauthorized",
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


def test_set_bid_timeout_class_not_found(chainnet):
    """Test setting bid_timeout on non-existent NFT class fails."""
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
        "demo_set_bid_timeout_class_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "not found" error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for class not found"
    exception_msg = result["exception"]["msg"]
    assert "not found" in exception_msg.lower(), f"Expected 'not found' in error message: {exception_msg}"


def test_set_bid_timeout_bounds_check_too_low(chainnet):
    """Test setting bid_timeout below minimum bound fails."""
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
    owner = get_test_address(dysond, "0x777777")

    # Test with value below minimum (-1 second, which should fail bounds check)
    bid_timeout_seconds = -1

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "bid_timeout_seconds": bid_timeout_seconds,
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
        "demo_set_bid_timeout_bounds_check",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with bounds error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for bounds violation"
    exception_msg = result["exception"]["msg"]
    assert "invalid request" in exception_msg.lower(), f"Expected 'invalid request' in error message: {exception_msg}"


def test_set_bid_timeout_bounds_check_too_high(chainnet):
    """Test setting bid_timeout above maximum bound fails."""
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
    owner = get_test_address(dysond, "0x888888")

    # Test with value above maximum (90 days + 1 second = 7776001 seconds, which should fail bounds check)
    bid_timeout_seconds = 7776001

    # Execute script
    kwargs = json.dumps({
        "class_id": class_id,
        "owner": owner,
        "bid_timeout_seconds": bid_timeout_seconds,
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
        "demo_set_bid_timeout_bounds_check",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with bounds error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for bounds violation"
    exception_msg = result["exception"]["msg"]
    assert "invalid request" in exception_msg.lower(), f"Expected 'invalid request' in error message: {exception_msg}"
