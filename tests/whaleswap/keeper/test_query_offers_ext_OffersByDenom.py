"""
Test OffersByDenom query for whaleswap offers.

Tests the QueryOffersByDenom endpoint which retrieves offers that reference
a specific denom either as have or want side.
Covers happy paths and error cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_offers_by_denom_role_have(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByDenom query with role='have'."""
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

def demo_offers_by_denom_have(alice_addr, foo_name, bar_name):
    # Create offer with foo_name as have_denom
    sudo_offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })

    offer_result = sudo_offer_result["results"][0]
    offer_id = offer_result["offer_id"]
    
    # Query offers by denom with role='have' (should find offer with foo_name as have)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByDenomRequest",
        "denom": foo_name,
        "role": "have"
    })
    
    return {
        "offer_id": offer_id,
        "offers_query": offers_query
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
        "demo_offers_by_denom_have",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response structure
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

    # Extract nested result
    demo_result = result["result"]["result"]

    # Check for exceptions
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    # Validate script returned expected structure
    assert (
        demo_result.get("offer_id") is not None
    ), f"Script should return offer_id. Result: {json.dumps(demo_result, indent=2)}"
    assert (
        demo_result.get("offers_query") is not None
    ), f"Script should return offers_query. Result: {json.dumps(demo_result, indent=2)}"

    # Extract the offers query response
    offers_query = demo_result["offers_query"]

    # Verify the query response structure (Type + Shape)
    assert isinstance(
        offers_query, dict
    ), f"Offers query should return dict, got {type(offers_query)}"
    assert (
        "offers" in offers_query
    ), f"Offers query missing 'offers' key. Keys: {list(offers_query.keys())}"
    assert (
        "pagination" in offers_query
    ), f"Offers query missing 'pagination' key. Keys: {list(offers_query.keys())}"

    # Verify offers list
    offers = offers_query["offers"]
    assert isinstance(offers, list), f"Offers should be list, got {type(offers)}"
    assert (
        len(offers) >= 1
    ), f"Should have at least 1 offer with {foo_name} as have_denom, got {len(offers)}"

    # Verify the created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"

    # Verify offer structure
    offer_index = offer_ids.index(str(demo_result["offer_id"]))
    found_offer = offers[offer_index]
    assert (
        "remaining_have" in found_offer
    ), f"Offer missing 'remaining_have' key. Keys: {list(found_offer.keys())}"
    assert (
        found_offer["remaining_have"]["denom"] == foo_name
    ), f"Offer have_denom should be {foo_name}, got {found_offer['remaining_have']['denom']}"


def test_offers_by_denom_role_want(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByDenom query with role='want'."""
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

def demo_offers_by_denom_want(alice_addr, foo_name, bar_name):
    # Create offer with bar_name as want_denom
    sudo_offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })

    offer_result = sudo_offer_result["results"][0]
    offer_id = offer_result["offer_id"]
    
    # Query offers by denom with role='want' (should find offer with bar_name as want)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByDenomRequest",
        "denom": bar_name,
        "role": "want"
    })
    
    return {
        "offer_id": offer_id,
        "offers_query": offers_query
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
        "demo_offers_by_denom_want",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]

    # Check for exceptions
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    # Verify offers query response
    offers_query = demo_result["offers_query"]
    assert isinstance(
        offers_query, dict
    ), f"Offers query should return dict, got {type(offers_query)}"
    assert (
        "offers" in offers_query
    ), f"Offers query missing 'offers' key. Keys: {list(offers_query.keys())}"

    offers = offers_query["offers"]
    assert isinstance(offers, list), f"Offers should be list, got {type(offers)}"
    assert (
        len(offers) >= 1
    ), f"Should have at least 1 offer with {bar_name} as want_denom, got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"

    # Verify offer structure
    offer_index = offer_ids.index(str(demo_result["offer_id"]))
    found_offer = offers[offer_index]
    assert (
        "remaining_want" in found_offer
    ), f"Offer missing 'remaining_want' key. Keys: {list(found_offer.keys())}"
    assert (
        found_offer["remaining_want"]["denom"] == bar_name
    ), f"Offer want_denom should be {bar_name}, got {found_offer['remaining_want']['denom']}"


def test_offers_by_denom_role_empty(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByDenom query with role='' (empty, both sides)."""
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

def demo_offers_by_denom_empty_role(alice_addr, foo_name, bar_name):
    # Create offer with foo_name as have_denom
    sudo_offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })

    offer_result = sudo_offer_result["results"][0]
    offer_id = offer_result["offer_id"]
    
    # Query offers by denom with role='' (empty, should find offers with foo_name in either have or want)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByDenomRequest",
        "denom": foo_name
    })
    
    return {
        "offer_id": offer_id,
        "offers_query": offers_query
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
        "demo_offers_by_denom_empty_role",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]

    # Check for exceptions
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    # Verify offers query response
    offers_query = demo_result["offers_query"]
    assert isinstance(
        offers_query, dict
    ), f"Offers query should return dict, got {type(offers_query)}"
    assert (
        "offers" in offers_query
    ), f"Offers query missing 'offers' key. Keys: {list(offers_query.keys())}"

    offers = offers_query["offers"]
    assert isinstance(offers, list), f"Offers should be list, got {type(offers)}"
    assert (
        len(offers) >= 1
    ), f"Should have at least 1 offer with {foo_name} in have or want, got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"


def test_offers_by_denom_empty(chainnet):
    """Test OffersByDenom query with empty denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_denom():
    # Query with empty denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByDenomRequest",
        "denom": ""
    })
    return {"result": result}
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
        "demo_empty_denom",
        "--extra-code",
        extra_code,
    )

    # Query with empty denom should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with empty denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "denom required" in exception_str.lower()
    ), f"Error should mention denom required. Exception: {exception_str}"
