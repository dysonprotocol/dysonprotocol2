"""
AuctionsBySeller query handler coverage tests.

Tests the AuctionsBySeller query endpoint which retrieves auctions
created by a specific seller address. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_auctions_by_seller_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AuctionsBySeller query with valid seller address."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_auctions_by_seller(alice_addr, foo_name, bar_name):
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "sell": {"denom": foo_name, "amount": "500"},
        "bid_denom": bar_name
    })
    auction_id = auction_result["results"][0]["auction_id"]

    auctions_response = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionsBySellerRequest",
        "seller": alice_addr
    })
    return {"auction_id": auction_id, "auctions_response": auctions_response}
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_auctions_by_seller",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    auction_id = demo_result["auction_id"]
    auctions_response = demo_result["auctions_response"]

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"AuctionsBySeller response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"AuctionsBySeller response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Verify auction is in results
    auction_ids_found = [int(a.get("auction_id")) for a in auctions_list]
    assert (
        int(auction_id) in auction_ids_found
    ), f"Auction ID {auction_id} not found in seller's auctions. Found IDs: {auction_ids_found}"

    # Verify all auctions belong to seller
    for auction in auctions_list:
        assert (
            auction.get("seller") == alice_addr
        ), f"Auction {auction.get('auction_id')} seller mismatch: expected {alice_addr}, got {auction.get('seller')}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_by_seller_empty_seller(chainnet):
    """Test AuctionsBySeller query with empty seller address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_auctions_by_seller_empty():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionsBySellerRequest",
        "seller": ""
    })
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
        "demo_auctions_by_seller_empty",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for empty seller. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2).lower()
    assert (
        "seller required" in exception_str
    ), f"Error should mention seller required. Exception: {exception_str}"


def test_auctions_by_seller_no_auctions(chainnet, generate_account, faucet):
    """Test AuctionsBySeller query for seller with no auctions."""
    dysond = chainnet[0]
    seller_name, seller_addr = generate_account(
        "no_auctions_seller", faucet_amount=1_000_000
    )

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = f"""
from dys import _query

def demo_auctions_by_seller_empty():
    auctions_response = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionsBySellerRequest",
        "seller": "{seller_addr}"
    }})
    return auctions_response
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
        "demo_auctions_by_seller_empty",
        "--extra-code",
        extra_code,
    )

    parsed_result = deep_parse(query_result)
    assert isinstance(parsed_result, dict)
    assert "result" in parsed_result
    assert "result" in parsed_result["result"]
    auctions_response = parsed_result["result"]["result"]

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"AuctionsBySeller response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"AuctionsBySeller response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list is empty (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        len(auctions_list) == 0
    ), f"Seller with no auctions should return empty list. Got {len(auctions_list)}: {json.dumps(auctions_list, indent=2)}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"
