"""
QueryBidsByBidder query handler coverage tests.

Validates listing of bids by bidder address, covering success paths,
pagination combinations (offset, key, reverse, count_total), status filtering,
IsCurrentHighest flag verification, and error handling (empty bidder, invalid bidder,
nil request). All tests run via stateless `dysond query script run`.
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

    return destination

def _setup_class_and_nft(root_name, nft_id, owner):
    class_id = root_name + "/collection"
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner,
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test",
    })
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner,
        "class_id": class_id,
        "nft_id": nft_id,
    })
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": True,
    })
    
    return class_id

def _place_bid(bidder, class_id, nft_id, bid_amount_str):
    bid_amount = _parse_coin(bid_amount_str)
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bidder,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": bid_amount,
    })
"""


def _random_root_name():
    return f"bid-{secrets.token_hex(4)}.dys"


def _assert_query_response(query_result):
    parsed = deep_parse(query_result)
    assert query_result.get("exception") is None, (
        f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    )
    demo_result = parsed["result"]["result"]
    assert isinstance(demo_result, dict), (
        f"Expected dict, got {type(demo_result)} full={json.dumps(demo_result, indent=2)}"
    )
    query_resp = demo_result["query_result"]
    assert isinstance(query_resp, dict), (
        f"Query result should be dict, got {type(query_resp)}"
    )
    assert "bids" in query_resp, (
        f"Missing bids key. Keys: {list(query_resp.keys())}, full={json.dumps(query_resp, indent=2)}"
    )
    assert "pagination" in query_resp, (
        f"Missing pagination key. Keys: {list(query_resp.keys())}, full={json.dumps(query_resp, indent=2)}"
    )
    return query_resp


def test_bids_by_bidder_comprehensive(chainnet):
    """Comprehensive test: success with bids, status filtering, IsCurrentHighest."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    owner_addr = alice_info["address"]
    bob_info = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )
    bidder1_addr = bob_info["address"]
    charlie_info = dysond(
        "keys", "show", "charlie", "--keyring-backend", "test", "--output", "json"
    )
    bidder2_addr = charlie_info["address"]
    root_name = _random_root_name()
    nft_id = "nft-1"

    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_bids_comprehensive(root_name, nft_id, owner_addr, bidder1_addr, bidder2_addr):
    _register_root_name(root_name, owner_addr)
    class_id = _setup_class_and_nft(root_name, nft_id, owner_addr)
    
    _place_bid(bidder1_addr, class_id, nft_id, "100udys")
    _place_bid(bidder2_addr, class_id, nft_id, "200udys")
    
    all_bids = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder1_addr,
    })
    
    active_only = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder1_addr,
        "status_filter": [1],
    })
    
    return {"all_bids": all_bids, "active_only": active_only}
"""
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
        "demo_bids_comprehensive",
        "--kwargs",
        json.dumps(
            {
                "root_name": root_name,
                "nft_id": nft_id,
                "owner_addr": owner_addr,
                "bidder1_addr": bidder1_addr,
                "bidder2_addr": bidder2_addr,
            }
        ),
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert query_result.get("exception") is None, (
        f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    )
    result = parsed["result"]["result"]

    all_bids = result["all_bids"]
    bids = all_bids["bids"]
    assert isinstance(bids, list), f"bids should be list, got {type(bids)}"
    assert len(bids) >= 1, f"Expected at least 1 bid, got {len(bids)}"

    nft_bids = [b for b in bids if b.get("bid", {}).get("nft_id") == nft_id]
    assert len(nft_bids) >= 1, f"Expected at least 1 bid for NFT, got {len(nft_bids)}"

    bidder1_bid = nft_bids[-1]
    assert isinstance(bidder1_bid.get("is_current_highest"), bool), (
        f"is_current_highest should be bool, got {type(bidder1_bid.get('is_current_highest'))}"
    )
    assert bidder1_bid["is_current_highest"] is False, (
        f"Bidder1 should not be current highest (bidder2 outbid). Got: {json.dumps(bidder1_bid, indent=2)}"
    )

    active_only = result["active_only"]
    active_bids = active_only["bids"]
    for bid in active_bids:
        bid_record = bid.get("bid", {})
        status = bid_record.get("status")
        assert status == 1, (
            f"Expected status 1 (ACTIVE), got {status} in bid {json.dumps(bid_record, indent=2)}"
        )


def test_bids_by_bidder_pagination(chainnet):
    """Comprehensive pagination test: offset, key, reverse, count_total."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    owner_addr = alice_info["address"]
    bob_info = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )
    bidder_addr = bob_info["address"]
    root_name = _random_root_name()
    nft_ids = [f"nft-{i}" for i in range(5)]

    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_bids_pagination(root_name, nft_ids, owner_addr, bidder_addr):
    _register_root_name(root_name, owner_addr)
    class_id = root_name + "/collection"
    
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner_addr,
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test",
    })
    
    for nft_id in nft_ids:
        _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
            "name_destination": owner_addr,
            "class_id": class_id,
            "nft_id": nft_id,
        })
        _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
            "nft_owner": owner_addr,
            "nft_class_id": class_id,
            "nft_id": nft_id,
            "listed": True,
        })
        _place_bid(bidder_addr, class_id, nft_id, "100udys")
    
    offset_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder_addr,
        "pagination": {
            "limit": 2,
            "offset": 1
        }
    })
    
    page1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder_addr,
        "pagination": {
            "limit": 2
        }
    })
    
    page2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder_addr,
        "pagination": {
            "limit": 2,
            "key": page1["pagination"]["next_key"]
        }
    })
    
    reverse_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder_addr,
        "pagination": {
            "limit": 2,
            "reverse": True
        }
    })
    
    count_total_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder_addr,
        "pagination": {
            "count_total": True
        }
    })
    
    return {
        "offset": offset_result,
        "page1": page1,
        "page2": page2,
        "reverse": reverse_result,
        "count_total": count_total_result
    }
"""
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
        "demo_bids_pagination",
        "--kwargs",
        json.dumps(
            {
                "root_name": root_name,
                "nft_ids": nft_ids,
                "owner_addr": owner_addr,
                "bidder_addr": bidder_addr,
            }
        ),
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert query_result.get("exception") is None, (
        f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    )
    result = parsed["result"]["result"]

    assert len(result["offset"]["bids"]) == 2, f"Offset pagination should return 2 bids"
    assert len(result["page1"]["bids"]) == 2, f"Page1 should have 2 bids"
    assert len(result["page2"]["bids"]) == 2, f"Page2 should have 2 bids"
    assert result["page1"]["pagination"]["next_key"] is not None, (
        f"Expected next_key, got {result['page1']['pagination']}"
    )
    assert len(result["reverse"]["bids"]) == 2, (
        f"Reverse pagination should return 2 bids"
    )
    assert result["count_total"]["pagination"].get("total") == str(len(nft_ids)), (
        f"Expected total {len(nft_ids)}, got {json.dumps(result['count_total']['pagination'], indent=2)}"
    )


def test_bids_by_bidder_no_bids(chainnet):
    """QueryBidsByBidder returns empty list when bidder has no bids."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    bob_info = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )
    bidder_addr = bob_info["address"]

    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_bids_by_bidder_no_bids(bidder_addr):
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder_addr,
    })
    return {"query_result": query_result}
"""
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
        "demo_bids_by_bidder_no_bids",
        "--kwargs",
        json.dumps({"bidder_addr": bidder_addr}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    bids = query_resp["bids"]
    assert isinstance(bids, list), f"bids should be list, got {type(bids)}"
    assert len(bids) == 0, f"Expected empty list, got {len(bids)} bids"


def test_bids_by_bidder_empty_bidder(chainnet):
    """Empty bidder should raise invalid argument."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_bids_empty_bidder():
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
            "bidder": "",
        })
        return {"error": "Should have failed", "result": query_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_bids_empty_bidder",
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    demo_result = parsed["result"]["result"]
    assert demo_result["expected"] is True, (
        f"Expected error flag, got {json.dumps(demo_result, indent=2)}"
    )
    assert "empty" in demo_result["error"].lower(), (
        f"Error should mention empty. Got {demo_result['error']}"
    )


def test_bids_by_bidder_invalid_bidder(chainnet):
    """Invalid bidder address returns empty list (no validation error)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_bids_invalid_bidder():
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": "invalid-address-123",
    })
    return {"query_result": query_result}
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_bids_invalid_bidder",
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    bids = query_resp["bids"]
    assert isinstance(bids, list), f"bids should be list, got {type(bids)}"
    assert len(bids) == 0, (
        f"Invalid bidder should return empty list, got {len(bids)} bids"
    )


def test_bids_by_bidder_nil_request(chainnet):
    """Nil request surfaces missing @type error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_bids_nil_request():
    try:
        query_result = _query(None)
        return {"error": "Should have failed", "result": query_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_bids_nil_request",
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    demo_result = parsed["result"]["result"]
    assert demo_result["expected"] is True, (
        f"Expected nil request error, got {json.dumps(demo_result, indent=2)}"
    )
    assert "@type" in demo_result["error"].lower(), (
        f"Error should mention @type. Got {demo_result['error']}"
    )


def test_bids_by_bidder_nft_caching(chainnet):
    """Test NFT data caching when multiple bids are for the same NFT."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    owner_addr = alice_info["address"]
    bob_info = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )
    bidder_addr = bob_info["address"]
    charlie_info = dysond(
        "keys", "show", "charlie", "--keyring-backend", "test", "--output", "json"
    )
    other_bidder_addr = charlie_info["address"]
    root_name = _random_root_name()

    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_bids_nft_caching(root_name, owner_addr, bidder_addr, other_bidder_addr):
    _register_root_name(root_name, owner_addr)
    class_id = _setup_class_and_nft(root_name, "nft-1", owner_addr)
    
    # Place multiple bids on the same NFT to trigger caching
    _place_bid(bidder_addr, class_id, "nft-1", "100udys")
    _place_bid(other_bidder_addr, class_id, "nft-1", "200udys")
    _place_bid(bidder_addr, class_id, "nft-1", "300udys")
    
    # Query bids for both bidders
    bidder_bids = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": bidder_addr,
    })
    
    other_bidder_bids = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsByBidderRequest",
        "bidder": other_bidder_addr,
    })
    
    return {
        "bidder_bids": bidder_bids,
        "other_bidder_bids": other_bidder_bids
    }
"""
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
        "demo_bids_nft_caching",
        "--kwargs",
        json.dumps(
            {
                "root_name": root_name,
                "owner_addr": owner_addr,
                "bidder_addr": bidder_addr,
                "other_bidder_addr": other_bidder_addr,
            }
        ),
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, (
        f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    )
    demo_result = result["result"]["result"]

    # Validate first bidder's bids
    bidder_bids = demo_result["bidder_bids"]["bids"]
    assert isinstance(bidder_bids, list), f"bidder_bids should be list"
    assert len(bidder_bids) == 2, (
        f"Expected 2 bids for first bidder, got {len(bidder_bids)}"
    )

    # Both bids should be for the same NFT (testing caching)
    first_nft_id = bidder_bids[0]["bid"]["nft_id"]
    second_nft_id = bidder_bids[1]["bid"]["nft_id"]
    assert first_nft_id == second_nft_id, (
        f"Both bids should be for same NFT to test caching"
    )

    # NFT data should be consistent (caching ensures same data)
    first_nft_data = bidder_bids[0]["nft"]
    second_nft_data = bidder_bids[1]["nft"]

    # Type assertions for NFT data
    assert isinstance(first_nft_data, dict), f"First NFT data should be dict"
    assert isinstance(second_nft_data, dict), f"Second NFT data should be dict"

    # Key assertions for NFT data structure
    nft_keys = [
        "bid_height",
        "bid_timestamp",
        "current_bid",
        "current_bidder",
        "listed",
        "metadata",
        "valuation",
        "valuation_expiry",
    ]
    for key in nft_keys:
        assert key in first_nft_data, f"First NFT data missing key: {key}"
        assert key in second_nft_data, f"Second NFT data missing key: {key}"

    # Value assertions for NFT data consistency
    assert first_nft_data["bid_height"] == second_nft_data["bid_height"], (
        f"NFT bid_height should be consistent"
    )
    assert first_nft_data["bid_timestamp"] == second_nft_data["bid_timestamp"], (
        f"NFT bid_timestamp should be consistent"
    )
    assert first_nft_data["current_bid"] == second_nft_data["current_bid"], (
        f"NFT current_bid should be consistent"
    )
    assert first_nft_data["current_bidder"] == second_nft_data["current_bidder"], (
        f"NFT current_bidder should be consistent"
    )
    assert first_nft_data["listed"] == second_nft_data["listed"], (
        f"NFT listed status should be consistent"
    )
    assert first_nft_data["metadata"] == second_nft_data["metadata"], (
        f"NFT metadata should be consistent"
    )
    assert first_nft_data["valuation"] == second_nft_data["valuation"], (
        f"NFT valuation should be consistent"
    )
    assert first_nft_data["valuation_expiry"] == second_nft_data["valuation_expiry"], (
        f"NFT valuation_expiry should be consistent"
    )

    # Validate current highest flags
    first_bid_is_current = bidder_bids[0].get("is_current_highest")
    second_bid_is_current = bidder_bids[1].get("is_current_highest")
    assert isinstance(first_bid_is_current, bool), f"is_current_highest should be bool"
    assert isinstance(second_bid_is_current, bool), f"is_current_highest should be bool"
    # FIXED: IsCurrentHighest calculation now works correctly
    # The first bid (100udys, status BID_OUTBID) should have is_current_highest: False
    # Only the second bid (300udys, status BID_ACTIVE) should have is_current_highest: True
    assert first_bid_is_current is False, (
        f"First bid (outbid) should have is_current_highest=False"
    )
    assert second_bid_is_current is True, (
        f"Second bid (active) should have is_current_highest=True"
    )

    # Validate second bidder's bids
    other_bidder_bids = demo_result["other_bidder_bids"]["bids"]
    assert isinstance(other_bidder_bids, list), f"other_bidder_bids should be list"
    assert len(other_bidder_bids) == 1, (
        f"Expected 1 bid for second bidder, got {len(other_bidder_bids)}"
    )

    # Should be for the same NFT
    other_nft_id = other_bidder_bids[0]["bid"]["nft_id"]
    assert other_nft_id == first_nft_id, (
        f"Should be for same NFT as first bidder's bids"
    )

    # NFT data should be consistent with cached data
    other_nft_data = other_bidder_bids[0]["nft"]

    # Type assertion for other NFT data
    assert isinstance(other_nft_data, dict), f"Other NFT data should be dict"

    # Key assertions for other NFT data structure
    for key in nft_keys:
        assert key in other_nft_data, f"Other NFT data missing key: {key}"

    # Value assertions for NFT data consistency across bidders
    assert other_nft_data["bid_height"] == first_nft_data["bid_height"], (
        f"NFT bid_height should be consistent across bidders"
    )
    assert other_nft_data["bid_timestamp"] == first_nft_data["bid_timestamp"], (
        f"NFT bid_timestamp should be consistent across bidders"
    )
    assert other_nft_data["current_bid"] == first_nft_data["current_bid"], (
        f"NFT current_bid should be consistent across bidders"
    )
    assert other_nft_data["current_bidder"] == first_nft_data["current_bidder"], (
        f"NFT current_bidder should be consistent across bidders"
    )
    assert other_nft_data["listed"] == first_nft_data["listed"], (
        f"NFT listed status should be consistent across bidders"
    )
    assert other_nft_data["metadata"] == first_nft_data["metadata"], (
        f"NFT metadata should be consistent across bidders"
    )
    assert other_nft_data["valuation"] == first_nft_data["valuation"], (
        f"NFT valuation should be consistent across bidders"
    )
    assert other_nft_data["valuation_expiry"] == first_nft_data["valuation_expiry"], (
        f"NFT valuation_expiry should be consistent across bidders"
    )

    # Second bidder's bid should be outbid
    other_bid_is_current = other_bidder_bids[0].get("is_current_highest")
    assert isinstance(other_bid_is_current, bool), f"is_current_highest should be bool"
    assert other_bid_is_current is False, f"Second bidder's bid should be outbid"
