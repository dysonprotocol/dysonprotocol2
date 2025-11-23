"""
Test PlaceBid message handler for nameservice keeper.

Tests the bid placement functionality which allows users to place bids
on listed NFTs, with proper validation and escrow handling.
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
        "description": "Test class for PlaceBid",
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


def _set_nft_listed(class_id, nft_id, owner, listed):
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": listed,
    })


def _set_nft_valuation(class_id, nft_id, owner, valuation):
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetValuation",
        "owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "valuation": _parse_coin(valuation),
        "max_valuation_fee_pct": "1.0",
    })


def _setup_class_and_nft(root_name, nft_id, owner):
    class_id = root_name
    # Create NFT class
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner,
        "class_id": class_id,
        "name": root_name,
        "symbol": "TEST",
        "description": "Test class for PlaceBid",
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

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": True,
    })

    return class_id


def demo_place_bid_nft_not_listed(bidder_addr, owner_addr):
    class_id = "test-not-listed.dys"
    nft_id = "nft1"

    # Setup: Create NFT class and mint NFT but don't list it
    _create_nft_class_and_mint_nft(class_id, nft_id, owner_addr)

    # Explicitly set the class to not be always listed
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassAlwaysListed",
        "name_destination": owner_addr,
        "class_id": class_id,
        "always_listed": False,
    })

    # Set a valuation but don't list the NFT
    _set_nft_valuation(class_id, nft_id, owner_addr, "10udys")

    # Check NFT status before bidding
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_id,
        "id": nft_id,
    })

    class_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryClassRequest",
        "class_id": class_id,
    })

    # Try to place bid (should fail)
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bidder_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": _parse_coin("15udys"),
    })

    return {
        "place_bid_result": result,
        "nft_status": nft_query,
        "class_status": class_query,
    }


def demo_place_bid_nft_not_found(bidder_addr):
    # Try to place bid on non-existent NFT
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bidder_addr,
        "nft_class_id": "nonexistent.dys",
        "nft_id": "nft1",
        "bid_amount": _parse_coin("15udys"),
    })

    return {"place_bid_result": result}


def demo_place_bid_insufficient_bid(bidder_addr, owner_addr):
    class_id = "test-low-bid.dys"
    nft_id = "nft1"

    # Setup: Create NFT class and mint NFT
    _create_nft_class_and_mint_nft(class_id, nft_id, owner_addr)

    # Set NFT as listed
    _set_nft_listed(class_id, nft_id, owner_addr, True)

    # Set a high valuation
    _set_nft_valuation(class_id, nft_id, owner_addr, "100udys")

    # Try to place bid lower than valuation (should fail)
    result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bidder_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": _parse_coin("50udys"),
    })

    return {"place_bid_result": result}


def demo_place_bid_outbid_existing(bidder_addr, owner_addr, competitor_addr):
    class_id = "test-outbid.dys"
    nft_id = "nft1"

    # Setup: Create NFT class and mint NFT
    _create_nft_class_and_mint_nft(class_id, nft_id, owner_addr)

    # Set NFT as listed
    _set_nft_listed(class_id, nft_id, owner_addr, True)

    # Set a valuation
    _set_nft_valuation(class_id, nft_id, owner_addr, "10udys")

    # First bid
    first_bid = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bidder_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": _parse_coin("15udys"),
    })

    # Second bid (outbid)
    second_bid = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": competitor_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": _parse_coin("20udys"),
    })

    # Query final bid
    bid_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
    })

    return {
        "first_bid": first_bid,
        "second_bid": second_bid,
        "bid_query": bid_query,
    }
"""


def _random_root_name():
    return f"placebid-{secrets.token_hex(4)}.dys"


def _assert_query_response(query_result):
    parsed = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    demo_result = parsed["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Expected dict, got {type(demo_result)} full={json.dumps(demo_result, indent=2)}"
    return demo_result


def test_place_bid_success(chainnet):
    """Test successful bid placement on a listed NFT."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use existing test keys
    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    owner_addr = alice_info["address"]
    bob_info = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )
    bidder_addr = bob_info["address"]
    root_name = _random_root_name()
    nft_id = "nft1"

    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_place_bid_success(root_name, nft_id, owner_addr, bidder_addr):
    _register_root_name(root_name, owner_addr)
    class_id = _setup_class_and_nft(root_name, nft_id, owner_addr)

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetValuation",
        "owner": owner_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "valuation": _parse_coin("10udys"),
        "max_valuation_fee_pct": "1.0",
    })

    place_bid_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bidder_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": _parse_coin("15udys"),
    })

    bid_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
    })

    return {
        "place_bid_result": place_bid_result,
        "bid_query": bid_query,
    }
"""
    )

    kwargs = json.dumps(
        {
            "root_name": root_name,
            "nft_id": nft_id,
            "owner_addr": owner_addr,
            "bidder_addr": bidder_addr,
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
        "demo_place_bid_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    demo_result = _assert_query_response(query_result)

    # Validate place bid result
    place_bid_result = demo_result["place_bid_result"]
    assert isinstance(
        place_bid_result, dict
    ), f"place_bid_result should be dict, got {type(place_bid_result)}"
    assert (
        place_bid_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo should return sudo response, got {place_bid_result.get('@type')}"
    assert (
        len(place_bid_result["results"]) == 1
    ), f"sudo should have one result, got {len(place_bid_result['results'])}"
    assert (
        place_bid_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgPlaceBidResponse"
    ), f"sudo should return place bid response, got {place_bid_result['results'][0].get('@type')}"

    # Validate bid query
    bid_query = demo_result["bid_query"]
    assert isinstance(
        bid_query, dict
    ), f"bid_query should be dict, got {type(bid_query)}"
    assert (
        "bids" in bid_query
    ), f"bid_query should have bids, got {list(bid_query.keys())}"
    assert (
        len(bid_query["bids"]) == 1
    ), f"should have one bid, got {len(bid_query['bids'])}"

    bid = bid_query["bids"][0]
    assert bid["bidder"] == bidder_addr, f"bidder should match, got {bid['bidder']}"
    assert (
        bid["amount"]["denom"] == "udys"
    ), f"bid denom should be udys, got {bid['amount']['denom']}"
    assert (
        bid["amount"]["amount"] == "15"
    ), f"bid amount should be 15, got {bid['amount']['amount']}"


def test_place_bid_nft_not_listed(chainnet):
    """Test that bid placement fails when NFT is not listed."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use existing test keys that have coins
    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    bidder_addr = alice_info["address"]
    bob_info = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )
    owner_addr = bob_info["address"]

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"bidder_addr": bidder_addr, "owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_place_bid_nft_not_listed",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert (
        parsed.get("exception") is not None
    ), "Expected exception when placing bid on unlisted NFT"
    exception_msg = parsed["exception"]["msg"]
    assert (
        "not listed" in exception_msg.lower()
    ), f"Expected 'not listed' in error message: {exception_msg}"


def test_place_bid_nft_not_found(chainnet):
    """Test that bid placement fails when NFT doesn't exist."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use existing test key that has coins
    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    bidder_addr = alice_info["address"]

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"bidder_addr": bidder_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_place_bid_nft_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert (
        parsed.get("exception") is not None
    ), "Expected exception when placing bid on non-existent NFT"
    exception_msg = parsed["exception"]["msg"]
    assert (
        "not found" in exception_msg.lower()
    ), f"Expected 'not found' in error message: {exception_msg}"


def test_place_bid_insufficient_bid(chainnet):
    """Test that bid placement fails when bid amount is below valuation."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use existing test keys that have coins
    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    bidder_addr = alice_info["address"]
    bob_info = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )
    owner_addr = bob_info["address"]

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps({"bidder_addr": bidder_addr, "owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_place_bid_insufficient_bid",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert (
        parsed.get("exception") is not None
    ), "Expected exception when placing insufficient bid"
    exception_msg = parsed["exception"]["msg"]
    assert (
        "must be greater than or equal to current valuation" in exception_msg.lower()
    ), f"Expected 'must be greater than or equal to current valuation' in error message: {exception_msg}"


def test_place_bid_outbid_existing(chainnet):
    """Test successful outbidding of an existing bid."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use existing test keys that have coins
    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    bidder_addr = alice_info["address"]
    bob_info = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )
    owner_addr = bob_info["address"]
    competitor_addr = bidder_addr  # Use alice as competitor too (simplified)

    extra_code = BASE_EXTRA_CODE

    kwargs = json.dumps(
        {
            "bidder_addr": bidder_addr,
            "owner_addr": owner_addr,
            "competitor_addr": competitor_addr,
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
        "demo_place_bid_outbid_existing",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

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

    # Both bids should succeed
    first_bid = demo_result["first_bid"]
    second_bid = demo_result["second_bid"]
    assert first_bid["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    assert second_bid["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"

    # Should have 2 historical bids (both from the same bidder)
    bid_query = demo_result["bid_query"]
    assert (
        len(bid_query["bids"]) == 2
    ), f"should have two historical bids, got {len(bid_query['bids'])}"

    # Find the bids by amount
    bids_by_amount = {bid["amount"]["amount"]: bid for bid in bid_query["bids"]}

    # Should have both the original bid (15) and the outbid (20)
    assert "15" in bids_by_amount, "should have original bid of 15udys"
    assert "20" in bids_by_amount, "should have outbid of 20udys"

    # Both bids should be from the same bidder (alice bidding against herself)
    for bid in bid_query["bids"]:
        assert (
            bid["bidder"] == bidder_addr
        ), f"all bids should be from the same bidder, got {bid['bidder']}"
