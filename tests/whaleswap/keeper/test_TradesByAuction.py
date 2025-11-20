"""
TradesByAuction query handler coverage tests.

Tests the TradesByAuction query endpoint which retrieves all trades
involving auction redemptions for a specific auction. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_trades_by_auction_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test TradesByAuction query with valid auction ID."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
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

def demo_trades_by_auction(alice_addr, bob_addr, foo_name, bar_name):
    # Open auction
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "bid_denom": bar_name,
        "sell": {"denom": foo_name, "amount": "500"}
    })
    
    auction_id = auction_result["results"][0]["auction_id"]
    class_id = f"whaleswap.dys/auction/{bar_name}"
    nft_id = f"{int(auction_id):010d}"
    
    # Fund bob with bid denom
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": bob_addr,
        "amount": [{"denom": bar_name, "amount": "1000"}]
    })
    
    # Place bid
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bob_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": {"denom": bar_name, "amount": "1000"}
    })
    
    # Accept bid (transfers NFT to bob, sets valuation)
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgAcceptBid",
        "owner": alice_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id
    })
    
    # Redeem auction as winning bidder (creates trade)
    redeem_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRedeemAuction",
        "caller": bob_addr,
        "auction_id": auction_id
    })
    
    # Query trades by auction
    trades_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByAuctionRequest",
        "auction_id": auction_id
    })
    
    return {
        "auction_id": auction_id,
        "trades_query": trades_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
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
        "demo_trades_by_auction",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    assert "trades_query" in demo_result, f"Script should return trades_query. Result: {json.dumps(demo_result, indent=2)}"

    trades_response = demo_result["trades_query"]

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"TradesByAuction response should be dict, got {type(trades_response)}"
    assert (
        "pagination" in trades_response
    ), f"TradesByAuction response missing 'pagination' key. Keys: {list(trades_response.keys())}"

    # Validate trades list (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}"

    # Verify at least one trade exists
    assert (
        len(trades_list) > 0
    ), f"Should have at least one trade for auction with winning bidder. Trades: {json.dumps(trades_list, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_trades_by_auction_zero_id(chainnet):
    """Test TradesByAuction query with zero auction ID."""
    dysond = chainnet[0]

    # Query trades by auction with zero auction_id (should fail)
    result = dysond("query", "whaleswap", "trades-by-auction", "--auction-id", "0")

    # Should return error
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "auction_id required" in result.lower()
    ), f"Expected 'auction_id required' error. Got: {result}"


def test_trades_by_auction_no_trades(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test TradesByAuction query for auction with no trades."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create auction using multi-block transaction
    tx_auction = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        bar_name,
        "--sell",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        tx_auction.get("code", 1) == 0
    ), f"Open auction failed: {json.dumps(tx_auction, indent=2)}"

    # Extract auction_id from events
    auction_events = [
        e
        for e in tx_auction.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    assert (
        auction_events
    ), f"Missing EventAuctionCreated: {json.dumps(tx_auction, indent=2)}"
    auction_attrs = {
        a.get("key"): a.get("value") for a in auction_events[0].get("attributes", [])
    }
    auction_id = auction_attrs.get("auction_id")
    assert auction_id, f"auction_id missing: {json.dumps(auction_events[0], indent=2)}"
    auction_id = auction_id.strip('"')

    # Query trades by auction (no trades yet - auction not redeemed)
    trades_response = dysond(
        "query", "whaleswap", "trades-by-auction", "--auction-id", auction_id
    )

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"TradesByAuction response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"TradesByAuction response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list is empty (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        len(trades_list) == 0
    ), f"Auction with no trades should return empty list. Got {len(trades_list)}: {json.dumps(trades_list, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"

