"""
QueryBidsForNFT query handler coverage tests.

Validates listing of all historical bids for a specific NFT, covering success paths
with and without bids, pagination combinations (offset, key, reverse, count_total),
and error handling (nil request, empty class_id/nft_id). All tests run via stateless
`dysond query script run`.
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


def test_bids_for_nft_success_with_bids(chainnet):
    """Test BidsForNFT returns historical bids for an NFT."""
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
def demo_bids_for_nft_success(root_name, nft_id, owner_addr, bidder1_addr, bidder2_addr):
    _register_root_name(root_name, owner_addr)
    class_id = _setup_class_and_nft(root_name, nft_id, owner_addr)

    # Place multiple bids on the same NFT
    _place_bid(bidder1_addr, class_id, nft_id, "100udys")
    _place_bid(bidder2_addr, class_id, nft_id, "200udys")
    _place_bid(bidder1_addr, class_id, nft_id, "300udys")

    # Query all bids for this NFT
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
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
        "demo_bids_for_nft_success",
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

    query_resp = _assert_query_response(query_result)
    bids = query_resp["bids"]
    assert isinstance(bids, list), f"bids should be list, got {type(bids)}"
    assert len(bids) == 3, f"Expected 3 bids, got {len(bids)}"

    # Verify bids are in chronological order (increasing bid_ids)
    bid_ids = [int(bid["bid_id"]) for bid in bids]
    assert bid_ids == sorted(
        bid_ids
    ), f"Bids should be in chronological order, got {bid_ids}"

    # Verify all bids are for the correct NFT
    # Extract class_id from the first bid since it's not available in test scope
    expected_class_id = bids[0]["class_id"]
    for bid in bids:
        assert bid["class_id"] == expected_class_id, f"Bid class_id mismatch"
        assert bid["nft_id"] == nft_id, f"Bid nft_id mismatch"

    # Verify bid amounts are correct
    bid_amounts = [int(bid["amount"]["amount"]) for bid in bids]
    assert 100 in bid_amounts, f"Expected 100udys bid"
    assert 200 in bid_amounts, f"Expected 200udys bid"
    assert 300 in bid_amounts, f"Expected 300udys bid"


def test_bids_for_nft_no_bids(chainnet):
    """Test BidsForNFT returns empty list when NFT has no bids."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_info = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )
    owner_addr = alice_info["address"]
    root_name = _random_root_name()
    nft_id = "nft-no-bids"

    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_bids_for_nft_no_bids(root_name, nft_id, owner_addr):
    _register_root_name(root_name, owner_addr)
    class_id = _setup_class_and_nft(root_name, nft_id, owner_addr)

    # Don't place any bids

    # Query bids for this NFT
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
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
        "demo_bids_for_nft_no_bids",
        "--kwargs",
        json.dumps(
            {
                "root_name": root_name,
                "nft_id": nft_id,
                "owner_addr": owner_addr,
            }
        ),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    bids = query_resp["bids"]
    assert isinstance(bids, list), f"bids should be list, got {type(bids)}"
    assert len(bids) == 0, f"Expected empty list, got {len(bids)} bids"


def test_bids_for_nft_pagination(chainnet):
    """Test BidsForNFT pagination: offset, key, reverse, count_total."""
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
    nft_id = "nft-pagination"

    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_bids_for_nft_pagination(root_name, nft_id, owner_addr, bidder_addr):
    _register_root_name(root_name, owner_addr)
    class_id = _setup_class_and_nft(root_name, nft_id, owner_addr)

    # Place 5 bids on the same NFT
    for i in range(5):
        _place_bid(bidder_addr, class_id, nft_id, f"{100 + i * 50}udys")

    # Test offset pagination
    offset_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
        "pagination": {
            "limit": 2,
            "offset": 1
        }
    })

    # Test key-based pagination
    page1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
        "pagination": {
            "limit": 2
        }
    })

    page2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
        "pagination": {
            "limit": 2,
            "key": page1["pagination"]["next_key"]
        }
    })

    # Test reverse pagination
    reverse_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
        "pagination": {
            "limit": 2,
            "reverse": True
        }
    })

    # Test count_total
    count_total_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": nft_id,
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
        "demo_bids_for_nft_pagination",
        "--kwargs",
        json.dumps(
            {
                "root_name": root_name,
                "nft_id": nft_id,
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

    # Verify offset pagination
    assert len(result["offset"]["bids"]) == 2, f"Offset pagination should return 2 bids"

    # Verify key-based pagination
    assert len(result["page1"]["bids"]) == 2, f"Page1 should have 2 bids"
    assert len(result["page2"]["bids"]) == 2, f"Page2 should have 2 bids"
    assert (
        result["page1"]["pagination"]["next_key"] is not None
    ), f"Expected next_key, got {result['page1']['pagination']}"

    # Verify reverse pagination
    assert (
        len(result["reverse"]["bids"]) == 2
    ), f"Reverse pagination should return 2 bids"

    # Verify count_total
    assert result["count_total"]["pagination"].get("total") == str(
        5
    ), f"Expected total 5, got {json.dumps(result['count_total']['pagination'], indent=2)}"


def test_bids_for_nft_empty_class_id(chainnet):
    """Empty class_id should raise invalid argument error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_bids_for_nft_empty_class_id():
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
            "class_id": "",
            "nft_id": "nft-1",
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
        "demo_bids_for_nft_empty_class_id",
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    demo_result = parsed["result"]["result"]
    assert (
        demo_result["expected"] is True
    ), f"Expected error flag, got {json.dumps(demo_result, indent=2)}"
    assert (
        "required" in demo_result["error"].lower()
    ), f"Error should mention required. Got {demo_result['error']}"


def test_bids_for_nft_empty_nft_id(chainnet):
    """Empty nft_id should raise invalid argument error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_bids_for_nft_empty_nft_id():
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
            "class_id": "test.dys/collection",
            "nft_id": "",
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
        "demo_bids_for_nft_empty_nft_id",
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    demo_result = parsed["result"]["result"]
    assert (
        demo_result["expected"] is True
    ), f"Expected error flag, got {json.dumps(demo_result, indent=2)}"
    assert (
        "required" in demo_result["error"].lower()
    ), f"Error should mention required. Got {demo_result['error']}"


def test_bids_for_nft_nil_request(chainnet):
    """Nil request surfaces missing @type error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_bids_for_nft_nil_request():
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
        "demo_bids_for_nft_nil_request",
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


def test_bids_for_nft_multiple_nfts_isolated(chainnet):
    """Test BidsForNFT correctly isolates bids by NFT (different NFTs don't interfere)."""
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

    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_bids_for_nft_isolation(root_name, owner_addr, bidder_addr):
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

    # Create two NFTs
    for nft_id in ["nft-1", "nft-2"]:
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

    # Place bids on different NFTs
    _place_bid(bidder_addr, class_id, "nft-1", "100udys")
    _place_bid(bidder_addr, class_id, "nft-1", "200udys")  # 2 bids on nft-1
    _place_bid(bidder_addr, class_id, "nft-2", "150udys")  # 1 bid on nft-2

    # Query bids for each NFT separately
    nft1_bids = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "nft-1",
    })

    nft2_bids = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "nft-2",
    })

    return {
        "nft1_bids": nft1_bids,
        "nft2_bids": nft2_bids
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
        "demo_bids_for_nft_isolation",
        "--kwargs",
        json.dumps(
            {
                "root_name": root_name,
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

    # Verify NFT-1 has 2 bids
    nft1_bids = result["nft1_bids"]["bids"]
    assert isinstance(nft1_bids, list), f"nft1_bids should be list"
    assert len(nft1_bids) == 2, f"Expected 2 bids for nft-1, got {len(nft1_bids)}"

    # Verify NFT-2 has 1 bid
    nft2_bids = result["nft2_bids"]["bids"]
    assert isinstance(nft2_bids, list), f"nft2_bids should be list"
    assert len(nft2_bids) == 1, f"Expected 1 bid for nft-2, got {len(nft2_bids)}"

    # Verify bids are correctly attributed to their NFTs
    for bid in nft1_bids:
        assert bid["nft_id"] == "nft-1", f"Bid should be for nft-1"
    for bid in nft2_bids:
        assert bid["nft_id"] == "nft-2", f"Bid should be for nft-2"
