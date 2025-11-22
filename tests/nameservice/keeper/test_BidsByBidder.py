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

    return owner

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
    assert (
        query_result.get("exception") is None
    ), f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    demo_result = parsed["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Expected dict, got {type(demo_result)} full={json.dumps(demo_result, indent=2)}"
    query_resp = demo_result["query_result"]
    assert isinstance(
        query_resp, dict
    ), f"Query result should be dict, got {type(query_resp)}"
    assert (
        "bids" in query_resp
    ), f"Missing bids key. Keys: {list(query_resp.keys())}, full={json.dumps(query_resp, indent=2)}"
    assert (
        "pagination" in query_resp
    ), f"Missing pagination key. Keys: {list(query_resp.keys())}, full={json.dumps(query_resp, indent=2)}"
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
    assert (
        query_result.get("exception") is None
    ), f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    result = parsed["result"]["result"]

    all_bids = result["all_bids"]
    bids = all_bids["bids"]
    assert isinstance(bids, list), f"bids should be list, got {type(bids)}"
    assert len(bids) >= 1, f"Expected at least 1 bid, got {len(bids)}"

    nft_bids = [b for b in bids if b.get("bid", {}).get("nft_id") == nft_id]
    assert len(nft_bids) >= 1, f"Expected at least 1 bid for NFT, got {len(nft_bids)}"

    bidder1_bid = nft_bids[-1]
    assert isinstance(
        bidder1_bid.get("is_current_highest"), bool
    ), f"is_current_highest should be bool, got {type(bidder1_bid.get('is_current_highest'))}"
    assert (
        bidder1_bid["is_current_highest"] is False
    ), f"Bidder1 should not be current highest (bidder2 outbid). Got: {json.dumps(bidder1_bid, indent=2)}"

    active_only = result["active_only"]
    active_bids = active_only["bids"]
    for bid in active_bids:
        bid_record = bid.get("bid", {})
        status = bid_record.get("status")
        assert (
            status == 1
        ), f"Expected status 1 (ACTIVE), got {status} in bid {json.dumps(bid_record, indent=2)}"


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
    assert (
        query_result.get("exception") is None
    ), f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    result = parsed["result"]["result"]

    assert len(result["offset"]["bids"]) == 2, f"Offset pagination should return 2 bids"
    assert len(result["page1"]["bids"]) == 2, f"Page1 should have 2 bids"
    assert len(result["page2"]["bids"]) == 2, f"Page2 should have 2 bids"
    assert (
        result["page1"]["pagination"]["next_key"] is not None
    ), f"Expected next_key, got {result['page1']['pagination']}"
    assert (
        len(result["reverse"]["bids"]) == 2
    ), f"Reverse pagination should return 2 bids"
    assert result["count_total"]["pagination"].get("total") == str(
        len(nft_ids)
    ), f"Expected total {len(nft_ids)}, got {json.dumps(result['count_total']['pagination'], indent=2)}"


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
    assert (
        demo_result["expected"] is True
    ), f"Expected error flag, got {json.dumps(demo_result, indent=2)}"
    assert (
        "empty" in demo_result["error"].lower()
    ), f"Error should mention empty. Got {demo_result['error']}"


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
    assert (
        len(bids) == 0
    ), f"Invalid bidder should return empty list, got {len(bids)} bids"


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
    assert (
        demo_result["expected"] is True
    ), f"Expected nil request error, got {json.dumps(demo_result, indent=2)}"
    assert (
        "@type" in demo_result["error"].lower()
    ), f"Error should mention @type. Got {demo_result['error']}"
