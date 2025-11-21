"""
Test OpenAuction keeper function for auction creation.

Tests the OpenAuction message handler which escrows sell coins, creates NFT
classes, mints NFTs, and records auction metadata.

Covers validation paths and happy paths for OpenAuction function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_open_auction_basic_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful auction opening (happy path)."""
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

def demo_open_auction_basic(alice_addr, foo_name, bar_name):
    # Open auction: sell foo, bid bar
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "bid_denom": bar_name,
        "sell": {"denom": foo_name, "amount": "500"}
    })
    
    auction_id = auction_result["results"][0]["auction_id"]
    
    # Query auction to verify
    auction_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionRequest",
        "auction_id": auction_id
    })
    
    return {
        "auction_result": auction_result["results"][0],
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
        "demo_open_auction_basic",
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
    auction_result = demo_result["auction_result"]
    auction_query = demo_result["auction_query"]

    assert "auction_id" in auction_result, f"Missing auction_id: {auction_result}"
    assert auction_result["auction_id"] is not None, f"Auction ID should not be None"

    assert "auction" in auction_query, f"Missing auction: {auction_query}"
    auction = auction_query["auction"]
    assert auction["sell"]["denom"] == foo_name, f"Sell denom mismatch"
    assert auction["sell"]["amount"] == "500", f"Sell amount mismatch"
    assert auction["bid_denom"] == bar_name, f"Bid denom mismatch"
    assert auction["seller"] == alice_addr, f"Seller mismatch"


def test_open_auction_invalid_seller(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OpenAuction with invalid seller address."""
    dysond = chainnet[0]
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

def demo_open_auction_invalid_seller(foo_name, bar_name):
    try:
        # Invalid seller address
        auction_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
            "seller": "invalid_address",
            "bid_denom": bar_name,
            "sell": {"denom": foo_name, "amount": "500"}
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"foo_name": foo_name, "bar_name": bar_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_open_auction_invalid_seller",
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


def test_open_auction_zero_sell_amount(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OpenAuction with zero sell amount."""
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

def demo_open_auction_zero_sell_amount(alice_addr, foo_name, bar_name):
    try:
        # Zero sell amount
        auction_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
            "seller": alice_addr,
            "bid_denom": bar_name,
            "sell": {"denom": foo_name, "amount": "0"}
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
        "demo_open_auction_zero_sell_amount",
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
        "must be > 0" in demo_result["error"].lower()
    ), f"Error should mention must be > 0: {demo_result['error']}"


def test_open_auction_invalid_sell_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OpenAuction with invalid sell denom."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
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

def demo_open_auction_invalid_sell_denom(alice_addr, bar_name):
    try:
        # Invalid sell denom
        auction_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
            "seller": alice_addr,
            "bid_denom": bar_name,
            "sell": {"denom": "invalid/denom", "amount": "500"}
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"alice_addr": alice_addr, "bar_name": bar_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_open_auction_invalid_sell_denom",
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


def test_open_auction_invalid_bid_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OpenAuction with invalid bid denom."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
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

def demo_open_auction_invalid_bid_denom(alice_addr, foo_name):
    try:
        # Invalid bid denom
        auction_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
            "seller": alice_addr,
            "bid_denom": "invalid/denom",
            "sell": {"denom": foo_name, "amount": "500"}
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"alice_addr": alice_addr, "foo_name": foo_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_open_auction_invalid_bid_denom",
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


def test_open_auction_same_denoms(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OpenAuction with sell and bid denoms the same."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
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

def demo_open_auction_same_denoms(alice_addr, foo_name):
    try:
        # Same denoms for sell and bid
        auction_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
            "seller": alice_addr,
            "bid_denom": foo_name,
            "sell": {"denom": foo_name, "amount": "500"}
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"alice_addr": alice_addr, "foo_name": foo_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_open_auction_same_denoms",
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
        "must differ" in demo_result["error"].lower()
    ), f"Error should mention must differ: {demo_result['error']}"


def test_open_auction_insufficient_balance(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OpenAuction with insufficient seller balance."""
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

def demo_open_auction_insufficient_balance(alice_addr, foo_name, bar_name):
    try:
        # Try to sell more than available balance
        auction_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
            "seller": alice_addr,
            "bid_denom": bar_name,
            "sell": {"denom": foo_name, "amount": "999999999"}
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
        "demo_open_auction_insufficient_balance",
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
        "insufficient" in error_lower
    ), f"Error should mention insufficient: {demo_result['error']}"
