"""
Test RedeemAuction keeper function for auction redemption.

Tests the RedeemAuction message handler which allows NFT owners to redeem
escrowed coins, burns NFTs, deletes indexes, and optionally records trades
for winning bidders.

Covers validation paths and happy paths for RedeemAuction function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_redeem_auction_seller_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful auction redemption by seller (no bidder, no trade)."""
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

def demo_redeem_auction_seller(alice_addr, foo_name, bar_name):
    # Open auction
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "bid_denom": bar_name,
        "sell": {"denom": foo_name, "amount": "500"}
    })
    
    auction_id = auction_result["results"][0]["auction_id"]
    
    # Redeem auction as seller
    redeem_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRedeemAuction",
        "caller": alice_addr,
        "auction_id": auction_id
    })
    
    # Verify auction is deleted
    try:
        auction_query = _query({
            "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionRequest",
            "auction_id": auction_id
        })
        return {"error": "Auction should be deleted"}
    except Exception as e:
        return {
            "auction_id": auction_id,
            "redeem_result": redeem_result["results"][0],
            "auction_deleted": True
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
        "demo_redeem_auction_seller",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    assert (
        "auction_deleted" in demo_result
    ), f"Should indicate auction deleted: {demo_result}"
    assert demo_result["auction_deleted"] is True, f"Auction should be deleted"


def test_redeem_auction_auction_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RedeemAuction with non-existent auction."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_redeem_auction_not_found(alice_addr):
    try:
        # Non-existent auction ID
        redeem_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgRedeemAuction",
            "caller": alice_addr,
            "auction_id": 99999
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"alice_addr": alice_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_redeem_auction_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "not found" in demo_result["error"].lower()
    ), f"Error should mention not found: {demo_result['error']}"


def test_redeem_auction_unauthorized_caller(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RedeemAuction with caller who is not the NFT owner."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_redeem_auction_unauthorized(alice_addr, bob_addr, foo_name, bar_name):
    # Open auction as alice
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "bid_denom": bar_name,
        "sell": {"denom": foo_name, "amount": "500"}
    })
    
    auction_id = auction_result["results"][0]["auction_id"]
    
    try:
        # Bob tries to redeem (not the owner)
        redeem_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgRedeemAuction",
            "caller": bob_addr,
            "auction_id": auction_id
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_redeem_auction_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    error_lower = demo_result["error"].lower()
    assert (
        "unauthorized" in error_lower
    ), f"Error should mention unauthorized: {demo_result['error']}"
    assert "owner" in error_lower, f"Error should mention owner: {demo_result['error']}"


def test_redeem_auction_invalid_caller(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RedeemAuction with invalid caller address."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_redeem_auction_invalid_caller(alice_addr, foo_name, bar_name):
    # Open auction
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "bid_denom": bar_name,
        "sell": {"denom": foo_name, "amount": "500"}
    })
    
    auction_id = auction_result["results"][0]["auction_id"]
    
    try:
        # Invalid caller address
        redeem_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgRedeemAuction",
            "caller": "invalid_address",
            "auction_id": auction_id
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_redeem_auction_invalid_caller",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "invalid" in demo_result["error"].lower()
    ), f"Error should mention invalid: {demo_result['error']}"


def test_redeem_auction_active_bidder(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RedeemAuction fails when active bidder exists."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_redeem_auction_active_bidder(alice_addr, bob_addr, foo_name, bar_name):
    # Open auction
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "bid_denom": bar_name,
        "sell": {"denom": foo_name, "amount": "500"}
    })
    
    auction_id = auction_result["results"][0]["auction_id"]
    
    # Place a bid (this creates an active bidder)
    class_id = f"whaleswap.dys/auction/{bar_name}"
    nft_id = f"{int(auction_id):010d}"
    
    bid_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bob_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": {"denom": bar_name, "amount": "1000"}
    })
    
    try:
        # Try to redeem while bid is active
        redeem_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgRedeemAuction",
            "caller": alice_addr,
            "auction_id": auction_id
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_redeem_auction_active_bidder",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    error_lower = demo_result["error"].lower()
    assert (
        "active" in error_lower
    ), f"Error should mention active: {demo_result['error']}"


def test_redeem_auction_winning_bidder_with_trade(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test RedeemAuction by winning bidder records trade."""
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

def demo_redeem_auction_winning_bidder(alice_addr, bob_addr, foo_name, bar_name):
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
    
    # Place bid
    bid_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bob_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": {"denom": bar_name, "amount": "1000"}
    })
    
    # Accept bid (transfers NFT to bob, sets valuation)
    accept_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgAcceptBid",
        "owner": alice_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id
    })
    
    # Redeem auction as winning bidder (should record trade)
    redeem_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRedeemAuction",
        "caller": bob_addr,
        "auction_id": auction_id
    })
    
    # Query trades by auction to verify trade was recorded
    trades_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByAuctionRequest",
        "auction_id": auction_id
    })
    
    return {
        "auction_id": auction_id,
        "redeem_result": redeem_result["results"][0],
        "trades": trades_query.get("trades", [])
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
        "demo_redeem_auction_winning_bidder",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    assert "redeem_result" in demo_result, f"Missing redeem_result: {demo_result}"
    assert "trades" in demo_result, f"Missing trades: {demo_result}"

    # Verify trade was recorded
    trades = demo_result["trades"]
    assert isinstance(trades, list), f"Trades should be list, got {type(trades)}"
    assert len(trades) > 0, f"Should have at least one trade recorded: {trades}"

    # Find the auction trade
    auction_trades = [
        t
        for t in trades
        if "operations" in t
        and len(t["operations"]) > 0
        and "auction" in str(t["operations"][0])
    ]
    assert len(auction_trades) > 0, f"Should have auction trade: {trades}"
