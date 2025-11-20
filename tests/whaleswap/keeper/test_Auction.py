"""
Auction query handler coverage tests.

Tests the Auction query endpoint which retrieves a single auction by ID.
Covers all validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_auction_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Auction query with valid auction ID."""
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

def demo_auction_query(alice_addr, foo_name, bar_name):
    # Open auction
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "bid_denom": bar_name,
        "sell": {"denom": foo_name, "amount": "500"}
    })
    
    auction_id = auction_result["results"][0]["auction_id"]
    
    # Query auction
    auction_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionRequest",
        "auction_id": auction_id
    })
    
    return {
        "auction_id": auction_id,
        "auction_query": auction_query
    }
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
        "demo_auction_query",
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
        result is not None
    ), f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    assert (
        "auction_query" in demo_result
    ), f"Script should return auction_query. Result: {json.dumps(demo_result, indent=2)}"

    auction_response = demo_result["auction_query"]

    # Validate response structure (Type)
    assert isinstance(
        auction_response, dict
    ), f"Auction response should be dict, got {type(auction_response)}"
    assert (
        "auction" in auction_response
    ), f"Auction response missing 'auction' key. Keys: {list(auction_response.keys())}"

    auction = auction_response["auction"]

    # Validate auction structure (Type + Shape)
    assert isinstance(auction, dict), f"Auction should be dict, got {type(auction)}"
    assert (
        "auction_id" in auction
    ), f"Auction missing 'auction_id' key. Keys: {list(auction.keys())}"
    assert (
        "seller" in auction
    ), f"Auction missing 'seller' key. Keys: {list(auction.keys())}"
    assert (
        "sell" in auction
    ), f"Auction missing 'sell' key. Keys: {list(auction.keys())}"
    assert (
        "bid_denom" in auction
    ), f"Auction missing 'bid_denom' key. Keys: {list(auction.keys())}"

    # Validate values
    assert (
        int(auction["auction_id"]) == int(demo_result["auction_id"])
    ), f"Auction ID mismatch: expected {demo_result['auction_id']}, got {auction['auction_id']}"
    assert (
        auction["seller"] == alice_addr
    ), f"Seller mismatch: expected {alice_addr}, got {auction['seller']}"
    assert (
        auction["sell"]["denom"] == foo_name
    ), f"Sell denom mismatch: expected {foo_name}, got {auction['sell']['denom']}"
    assert (
        auction["sell"]["amount"] == "500"
    ), f"Sell amount mismatch: expected '500', got {auction['sell']['amount']}"
    assert (
        auction["bid_denom"] == bar_name
    ), f"Bid denom mismatch: expected {bar_name}, got {auction['bid_denom']}"


def test_auction_zero_id(chainnet):
    """Test Auction query with zero auction ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_auction_zero_id():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionRequest",
        "auction_id": 0
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
        "demo_auction_zero_id",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for zero auction_id. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "auction_id required" in exception_str
    ), f"Expected 'auction_id required' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"


def test_auction_not_found(chainnet):
    """Test Auction query with non-existent auction ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_auction_not_found():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionRequest",
        "auction_id": 999999
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
        "demo_auction_not_found",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for non-existent auction. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "auction not found" in exception_str
    ), f"Expected 'auction not found' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"
