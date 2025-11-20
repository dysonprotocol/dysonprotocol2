"""
Test MakeOffer keeper function for orderbook offers.

Tests the MakeOffer message handler which creates orderbook offers with either
ESCROW or LIQUID settlement modes. Covers validation paths and happy paths.
"""

import json
import pytest
from deep_parse import deep_parse


def test_make_offer_escrow_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful offer creation in ESCROW mode (happy path)."""
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

def demo_make_offer_escrow(alice_addr, foo_name, bar_name):
    # Create offer in ESCROW mode
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Query offer to verify
    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": int(offer_id)
    })
    
    return {
        "offer_id": offer_id,
        "offer_query": offer_query
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
        "demo_make_offer_escrow",
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
    offer_query = demo_result["offer_query"]

    assert "offer" in offer_query, f"Missing offer: {offer_query}"
    offer = offer_query["offer"]
    assert offer["offer_id"] == demo_result["offer_id"], f"Offer ID mismatch"
    assert offer["status"] == "open", f"Offer should be open, got: {offer['status']}"
    assert offer["maker"] == alice_addr, f"Maker mismatch"
    assert offer["settlement_mode"] == "SETTLEMENT_ESCROW", f"Settlement mode mismatch"
    assert offer["initial_have"]["denom"] == foo_name, f"Have denom mismatch"
    assert offer["initial_have"]["amount"] == "1000", f"Have amount mismatch"
    assert offer["initial_want"]["denom"] == bar_name, f"Want denom mismatch"
    assert offer["initial_want"]["amount"] == "2000", f"Want amount mismatch"
    assert offer["remaining_have"]["amount"] == "1000", f"Remaining have mismatch"
    assert offer["remaining_want"]["amount"] == "2000", f"Remaining want mismatch"


def test_make_offer_liquid_success_with_pfand(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful offer creation in LIQUID mode with PFAND."""
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

def demo_make_offer_liquid_pfand(alice_addr, foo_name, bar_name):
    # Create offer in LIQUID mode (requires PFAND)
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_LIQUID"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Query offer to verify
    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": int(offer_id)
    })
    
    return {
        "offer_id": offer_id,
        "offer_query": offer_query
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
        "demo_make_offer_liquid_pfand",
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
    offer_query = demo_result["offer_query"]

    assert "offer" in offer_query, f"Missing offer: {offer_query}"
    offer = offer_query["offer"]
    assert offer["offer_id"] == demo_result["offer_id"], f"Offer ID mismatch"
    assert offer["status"] == "open", f"Offer should be open, got: {offer['status']}"
    assert offer["maker"] == alice_addr, f"Maker mismatch"
    assert offer["settlement_mode"] == "SETTLEMENT_LIQUID", f"Settlement mode mismatch"
    assert offer["initial_have"]["denom"] == foo_name, f"Have denom mismatch"
    assert offer["initial_have"]["amount"] == "1000", f"Have amount mismatch"
    assert offer["initial_want"]["denom"] == bar_name, f"Want denom mismatch"
    assert offer["initial_want"]["amount"] == "2000", f"Want amount mismatch"
    # PFAND should be locked
    assert "pfand_locked" in offer, f"Missing pfand_locked"
    assert offer["pfand_locked"]["amount"] == "1", f"PFAND amount mismatch"


def test_make_offer_invalid_maker_address(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeOffer with invalid maker address."""
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

def demo_make_offer_invalid_maker(foo_name, bar_name):
    try:
        offer_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": "invalid_address",
            "have": {"denom": foo_name, "amount": "1000"},
            "want": {"denom": bar_name, "amount": "2000"},
            "settlement_mode": "SETTLEMENT_ESCROW"
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
        "demo_make_offer_invalid_maker",
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


def test_make_offer_invalid_have_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeOffer with invalid have denom."""
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

def demo_make_offer_invalid_have_denom(alice_addr, bar_name):
    try:
        # Use invalid denom (empty string or invalid format)
        offer_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": alice_addr,
            "have": {"denom": "", "amount": "1000"},
            "want": {"denom": bar_name, "amount": "2000"},
            "settlement_mode": "SETTLEMENT_ESCROW"
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
        "demo_make_offer_invalid_have_denom",
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
        "denom" in demo_result["error"].lower()
    ), f"Error should mention denom: {demo_result['error']}"


def test_make_offer_same_denom(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test MakeOffer with same denom for have and want."""
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

def demo_make_offer_same_denom(alice_addr, foo_name):
    try:
        offer_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": alice_addr,
            "have": {"denom": foo_name, "amount": "1000"},
            "want": {"denom": foo_name, "amount": "2000"},
            "settlement_mode": "SETTLEMENT_ESCROW"
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
        "demo_make_offer_same_denom",
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
        "differ" in demo_result["error"].lower()
    ), f"Error should mention differ: {demo_result['error']}"


def test_make_offer_non_positive_amounts(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeOffer with non-positive amounts."""
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

def demo_make_offer_non_positive(alice_addr, foo_name, bar_name):
    try:
        offer_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": alice_addr,
            "have": {"denom": foo_name, "amount": "0"},
            "want": {"denom": bar_name, "amount": "2000"},
            "settlement_mode": "SETTLEMENT_ESCROW"
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
        "demo_make_offer_non_positive",
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
        "> 0" in demo_result["error"]
    ), f"Error should mention > 0: {demo_result['error']}"


def test_make_offer_insufficient_balance(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeOffer with insufficient balance for have amount."""
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

def demo_make_offer_insufficient_balance(alice_addr, foo_name, bar_name):
    try:
        # Try to create offer with amount exceeding balance
        offer_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": alice_addr,
            "have": {"denom": foo_name, "amount": "999999999"},
            "want": {"denom": bar_name, "amount": "2000"},
            "settlement_mode": "SETTLEMENT_ESCROW"
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
        "demo_make_offer_insufficient_balance",
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
        "insufficient" in demo_result["error"].lower()
    ), f"Error should mention insufficient: {demo_result['error']}"
