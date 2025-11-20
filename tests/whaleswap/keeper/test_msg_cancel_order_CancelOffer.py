"""
Test CancelOffer keeper function for orderbook offers.

Tests the CancelOffer message handler which allows makers or authorized third
parties to cancel open offers, refunding escrowed assets and releasing PFAND.

Covers all validation paths and happy paths for CancelOffer function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_cancel_offer_maker_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful cancellation by maker (happy path)."""
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

def demo_cancel_offer_maker(alice_addr, foo_name, bar_name):
    # Create offer
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Cancel offer as maker
    cancel_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": alice_addr,
        "offer_id": int(offer_id)
    })
    
    # Query offer to verify status
    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": int(offer_id)
    })
    
    return {
        "offer_id": offer_id,
        "cancel_result": cancel_result["results"][0],
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
        "demo_cancel_offer_maker",
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
    assert (
        offer["status"] == "cancelled"
    ), f"Offer should be cancelled, got: {offer['status']}"


def test_cancel_offer_not_found(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test CancelOffer fails when offer does not exist (line 42-44)."""
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

def demo_cancel_offer_nonexistent(alice_addr):
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": alice_addr,
        "offer_id": 99999
    })
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
        "demo_cancel_offer_nonexistent",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for non-existent offer: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "not found" in exception_msg
    ), f"Should mention 'not found', got: {exception_msg}"


def test_cancel_offer_not_open(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test CancelOffer fails when offer is not open (line 46-47)."""
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

def demo_cancel_offer_not_open(alice_addr, foo_name, bar_name):
    # Create offer
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Cancel offer first time
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": alice_addr,
        "offer_id": int(offer_id)
    })
    
    # Try to cancel again (should fail - already cancelled)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": alice_addr,
        "offer_id": int(offer_id)
    })
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
        "demo_cancel_offer_not_open",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for non-open offer: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    assert (
        "not open" in exception_msg
    ), f"Should mention 'not open', got: {exception_msg}"


def test_cancel_offer_unauthorized_third_party(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test CancelOffer fails when third party is not eligible (line 74-88)."""
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

def demo_cancel_offer_unauthorized(alice_addr, bob_addr, foo_name, bar_name):
    # Create offer as alice
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Try to cancel as bob (not eligible - maker has balance)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": bob_addr,
        "offer_id": int(offer_id)
    })
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
        "demo_cancel_offer_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Should fail for unauthorized third party: {query_result}"
    exception_msg = str(query_result["exception"]).lower()
    has_not_eligible = "not eligible" in exception_msg
    has_unauthorized = "unauthorized" in exception_msg
    assert (
        has_not_eligible == True
    ), f"Should mention 'not eligible'. Got: {exception_msg}"


def test_cancel_offer_third_party_eligible_low_balance(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test third-party cancellation succeeds when PFAND locked and maker balance < unit_have (lines 62-72)."""
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

def demo_cancel_third_party_eligible(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
    # Enable PFAND
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "pfand_per_offer": {"denom": "udys", "amount": "100"},
            "valuation_fee_pct": "0",
            "valuation_period": "3600s",
            "bid_timeout": "5s",
            "minimum_bid_percent_increase": "0",
            "max_note_length": 128,
            "block_delay_before_close": "1",
            "block_delay_before_liquidation": "1"
        }
    })
    
    # Make liquid-mode offer (locks PFAND)
    # Use have=10000, want=5000 so unit_have = 5000 (gcd(10000, 5000) = 5000)
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "10000"},
        "want": {"denom": bar_name, "amount": "5000"},
        "settlement_mode": "SETTLEMENT_LIQUID"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Drain alice's balance below unit_have (send to bob)
    # For have=10000, want=5000: gcd=5000, unit_have = 10000/5000 = 2
    # Need balance < 2, so drain to leave 1
    # alice has ~400000 after distribution, drain 399999 to leave 1
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": bob_addr,
        "amount": [{"denom": foo_name, "amount": "399999"}]
    })
    
    # Cancel as third party (bob) - should succeed because maker balance < unit_have
    cancel_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": bob_addr,
        "offer_id": int(offer_id)
    })
    
    # Query offer to verify status
    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": int(offer_id)
    })
    
    return {
        "offer_id": offer_id,
        "cancel_result": cancel_result["results"][0],
        "offer_query": offer_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "gov_addr": gov_addr,
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
        "demo_cancel_third_party_eligible",
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
    assert (
        offer["status"] == "cancelled"
    ), f"Offer should be cancelled, got: {offer['status']}"


def test_cancel_offer_escrow_refund(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test escrow refund execution when cancelling escrow-mode offer (lines 108-111)."""
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

def demo_cancel_escrow_refund(alice_addr, foo_name, bar_name):
    # Create escrow-mode offer
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Get balance before cancel
    balance_before = _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": alice_addr,
        "denom": foo_name
    })
    
    # Cancel offer (should refund escrowed have)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": alice_addr,
        "offer_id": int(offer_id)
    })
    
    # Get balance after cancel
    balance_after = _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": alice_addr,
        "denom": foo_name
    })
    
    # Query offer to verify status
    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": int(offer_id)
    })
    
    return {
        "offer_id": offer_id,
        "balance_before": balance_before,
        "balance_after": balance_after,
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
        "demo_cancel_escrow_refund",
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
    balance_before = demo_result["balance_before"]
    balance_after = demo_result["balance_after"]

    assert "offer" in offer_query, f"Missing offer: {offer_query}"
    offer = offer_query["offer"]
    assert (
        offer["status"] == "cancelled"
    ), f"Offer should be cancelled, got: {offer['status']}"

    # Verify escrow refund: balance should increase by remaining_have (1000)
    before_amt = int(balance_before["balance"]["amount"])
    after_amt = int(balance_after["balance"]["amount"])
    refunded = after_amt - before_amt
    assert (
        refunded == 1000
    ), f"Should refund 1000, got refunded: {refunded}, before: {before_amt}, after: {after_amt}"


def test_cancel_offer_pfand_release(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test PFAND release execution when cancelling offer with PFAND locked (lines 113-116)."""
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

def demo_cancel_pfand_release(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
    # Enable PFAND
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "pfand_per_offer": {"denom": "udys", "amount": "100"},
            "valuation_fee_pct": "0",
            "valuation_period": "3600s",
            "bid_timeout": "5s",
            "minimum_bid_percent_increase": "0",
            "max_note_length": 128,
            "block_delay_before_close": "1",
            "block_delay_before_liquidation": "1"
        }
    })
    
    # Make liquid-mode offer (locks PFAND)
    # Use have=10000, want=5000 so unit_have = 5000
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "10000"},
        "want": {"denom": bar_name, "amount": "5000"},
        "settlement_mode": "SETTLEMENT_LIQUID"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Get bob's udys balance before cancel (PFAND goes to closer)
    balance_before = _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": bob_addr,
        "denom": "udys"
    })
    
    # Cancel as bob (third party, but eligible because we'll drain alice's balance)
    # For have=10000, want=5000: gcd=5000, unit_have = 10000/5000 = 2
    # Need balance < 2, so drain to leave 1
    # Drain 399999 to leave 1
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": bob_addr,
        "amount": [{"denom": foo_name, "amount": "399999"}]
    })
    
    # Cancel offer (should release PFAND to bob)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": bob_addr,
        "offer_id": int(offer_id)
    })
    
    # Get bob's udys balance after cancel
    balance_after = _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": bob_addr,
        "denom": "udys"
    })
    
    # Query offer to verify status
    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": int(offer_id)
    })
    
    return {
        "offer_id": offer_id,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "offer_query": offer_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "gov_addr": gov_addr,
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
        "demo_cancel_pfand_release",
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
    balance_before = demo_result["balance_before"]
    balance_after = demo_result["balance_after"]

    assert "offer" in offer_query, f"Missing offer: {offer_query}"
    offer = offer_query["offer"]
    assert (
        offer["status"] == "cancelled"
    ), f"Offer should be cancelled, got: {offer['status']}"

    # Verify PFAND release: bob's udys balance should increase by PFAND amount (100)
    before_amt = int(balance_before["balance"]["amount"])
    after_amt = int(balance_after["balance"]["amount"])
    pfand_released = after_amt - before_amt
    assert (
        pfand_released == 100
    ), f"Should release 100 udys PFAND, got: {pfand_released}, before: {before_amt}, after: {after_amt}"
