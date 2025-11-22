"""
Test RejectBid message handler for nameservice keeper.

Tests the bid rejection functionality which allows NFT owners
to reject bids and refund the bidder's tokens.
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

    return name


def _send_coins(from_addr, to_addr, amount):
    return {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": from_addr,
        "to_address": to_addr,
        "amount": [_parse_coin(amount)]
    }


def _create_nft_class_and_mint_nft(class_id, nft_id, owner):
    # If using existing nameservice.dys class, just mint the NFT
    if class_id == "nameservice.dys":
        # Register a name for the NFT
        name = nft_id  # Use nft_id as the name
        _register_root_name(name, owner)

        # Mint the NFT
        _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
            "name_destination": owner,
            "class_id": class_id,
            "nft_id": nft_id,
            "uri": "",
            "uri_hash": "",
        })
    else:
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
            "description": "Test class for RejectBid",
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

    return class_id


def _set_nft_listed(class_id, nft_id, owner, listed):
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": listed,
    })


def _place_bid(class_id, nft_id, bidder, amount):
    return _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bidder,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": _parse_coin(amount),
    })


def _reject_bid(class_id, nft_id, owner, new_valuation="100udys"):
    return _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgRejectBid",
        "owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "new_valuation": _parse_coin(new_valuation),
    })


def demo_reject_bid_success(class_id, nft_id, owner, bidder, bid_amount, alice_addr):
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
        "to_address": bidder,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Setup: Create NFT class, mint NFT with initial valuation, and place bid
    class_id = _create_nft_class_and_mint_nft(class_id, nft_id, owner)
    _set_nft_listed(class_id, nft_id, owner, True)

    # Place bid
    bid_result = _place_bid(class_id, nft_id, bidder, bid_amount)

    # Reject bid
    reject_result = _reject_bid(class_id, nft_id, owner, "260udys")

    return {"bid_result": bid_result, "reject_result": reject_result}


def demo_reject_bid_no_active_bid(class_id, nft_id, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Setup: Create NFT class and mint NFT, but don't place bid
    class_id = _create_nft_class_and_mint_nft(class_id, nft_id, owner)
    _set_nft_listed(class_id, nft_id, owner, True)

    # Try to reject bid when none exists
    reject_result = _reject_bid(class_id, nft_id, owner, "100udys")

    return {"reject_result": reject_result}


def demo_reject_bid_nft_not_found(nft_id, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Try to reject bid on non-existent NFT - use a non-existent class_id
    class_id = "nonexistent.dys"
    reject_result = _reject_bid(class_id, nft_id, owner, "100udys")

    return {"reject_result": reject_result}


def demo_reject_bid_new_valuation_too_low(class_id, nft_id, owner, bidder, bid_amount, alice_addr):
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
        "to_address": bidder,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Setup: Create NFT class, mint NFT with initial valuation, and place bid
    class_id = _create_nft_class_and_mint_nft(class_id, nft_id, owner)
    _set_nft_listed(class_id, nft_id, owner, True)

    # Place bid
    _place_bid(class_id, nft_id, bidder, bid_amount)

    # Try to reject bid with new valuation too low (below minimum 1% increase)
    reject_result = _reject_bid(class_id, nft_id, owner, "100udys")

    return {"reject_result": reject_result}


def demo_reject_bid_unauthorized(class_id, nft_id, owner, unauthorized_owner, bidder, bid_amount, alice_addr):
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
        "to_address": bidder,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": unauthorized_owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Setup: Create NFT class, mint NFT with initial valuation, and place bid
    class_id = _create_nft_class_and_mint_nft(class_id, nft_id, owner)
    _set_nft_listed(class_id, nft_id, owner, True)

    # Place bid
    _place_bid(class_id, nft_id, bidder, bid_amount)

    # Try to reject bid as unauthorized owner
    reject_result = _reject_bid(class_id, nft_id, unauthorized_owner, "260udys")

    return {"reject_result": reject_result}
"""


def test_reject_bid_success(chainnet):
    """Test successful bid rejection with refund."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Use custom NFT class that test owner controls
    class_id = "test-class-" + secrets.token_hex(4) + ".dys"
    nft_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x111111")
    bidder = get_test_address(dysond, "0x222222")
    bid_amount = "250udys"

    # Execute script
    kwargs = json.dumps(
        {
            "class_id": class_id,
            "nft_id": nft_id,
            "owner": owner,
            "bidder": bidder,
            "bid_amount": bid_amount,
            "alice_addr": alice_addr,
        }
    )

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_reject_bid_success",
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

    # Verify bid placement succeeded
    assert (
        script_result["bid_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"Bid placement failed: {script_result['bid_result']}"

    # Verify bid rejection succeeded
    assert (
        script_result["reject_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"Bid rejection failed: {script_result['reject_result']}"


def test_reject_bid_no_active_bid(chainnet):
    """Test rejecting bid when no active bid exists."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = "test-class-" + secrets.token_hex(4) + ".dys"
    nft_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x333333")

    # Execute script
    kwargs = json.dumps(
        {
            "class_id": class_id,
            "nft_id": nft_id,
            "owner": owner,
            "alice_addr": alice_addr,
        }
    )

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_reject_bid_no_active_bid",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "no active bid" error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for no active bid"
    exception_msg = result["exception"]["msg"]
    assert (
        "no active bid" in exception_msg
    ), f"Expected 'no active bid' in error message: {exception_msg}"


def test_reject_bid_nft_not_found(chainnet):
    """Test rejecting bid on non-existent NFT."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    nft_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x444444")

    # Execute script
    kwargs = json.dumps(
        {
            "nft_id": nft_id,
            "owner": owner,
            "alice_addr": alice_addr,
        }
    )

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_reject_bid_nft_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "NFT not found" error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for NFT not found"
    exception_msg = result["exception"]["msg"]
    assert (
        "not found" in exception_msg
    ), f"Expected 'not found' in error message: {exception_msg}"


def test_reject_bid_unauthorized(chainnet):
    """Test rejecting bid by non-owner."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = "test-class-" + secrets.token_hex(4) + ".dys"
    nft_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x555555")
    bidder = get_test_address(dysond, "0x666666")
    unauthorized_owner = get_test_address(dysond, "0x777777")
    bid_amount = "150udys"

    # Execute script
    kwargs = json.dumps(
        {
            "class_id": class_id,
            "nft_id": nft_id,
            "owner": owner,
            "unauthorized_owner": unauthorized_owner,
            "bidder": bidder,
            "bid_amount": bid_amount,
            "alice_addr": alice_addr,
        }
    )

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_reject_bid_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "unauthorized" error
    parsed = deep_parse(result)
    assert (
        result.get("exception") is not None
    ), "Expected exception for unauthorized access"
    exception_msg = result["exception"]["msg"]
    assert (
        "unauthorized" in exception_msg
    ), f"Expected 'unauthorized' in error message: {exception_msg}"


def test_reject_bid_new_valuation_too_low(chainnet):
    """Test rejecting bid with new valuation below minimum required increase."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = "test-class-" + secrets.token_hex(4) + ".dys"
    nft_id = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x888888")
    bidder = get_test_address(dysond, "0x999999")
    bid_amount = "250udys"

    # Execute script
    kwargs = json.dumps(
        {
            "class_id": class_id,
            "nft_id": nft_id,
            "owner": owner,
            "bidder": bidder,
            "bid_amount": bid_amount,
            "alice_addr": alice_addr,
        }
    )

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_reject_bid_new_valuation_too_low",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with minimum valuation error
    parsed = deep_parse(result)
    assert (
        result.get("exception") is not None
    ), "Expected exception for valuation too low"
    exception_msg = result["exception"]["msg"]
    assert (
        "minimum acceptable valuation" in exception_msg
    ), f"Expected minimum valuation error: {exception_msg}"
