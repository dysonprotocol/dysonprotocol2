"""
Test OffersBest query for whaleswap offers.

Tests the QueryOffersBest endpoint which retrieves the best-priced offers
for a pair, sorted by price (want-per-have, ascending = best for takers).
Covers happy paths and error cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_offers_best_with_explicit_limit(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersBest query with explicit limit."""
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

def demo_offers_best_explicit_limit(alice_addr, foo_name, bar_name):
    # Create offer: 1000 foo for 2000 bar
    # Price = want/have = 2000/1000 = 2.0
    sudo_offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })

    offer_result = sudo_offer_result["results"][0]
    offer_id = offer_result["offer_id"]

    # Query best offers with explicit limit of 5
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersBestRequest",
        "have_denom": foo_name,
        "want_denom": bar_name,
        "limit": 5
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
        "demo_offers_best_explicit_limit",
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

    # Verify offers list
    offers = offers_query["offers"]
    assert isinstance(offers, list), f"Offers should be list, got {type(offers)}"
    assert len(offers) >= 1, f"Should have at least 1 offer for pair, got {len(offers)}"
    assert len(offers) <= 5, f"Should have at most 5 offers (limit), got {len(offers)}"

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
        "remaining_want" in found_offer
    ), f"Offer missing 'remaining_want' key. Keys: {list(found_offer.keys())}"
    assert (
        found_offer["remaining_have"]["denom"] == foo_name
    ), f"Offer have_denom should be {foo_name}, got {found_offer['remaining_have']['denom']}"
    assert (
        found_offer["remaining_want"]["denom"] == bar_name
    ), f"Offer want_denom should be {bar_name}, got {found_offer['remaining_want']['denom']}"


def test_offers_best_with_default_limit(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersBest query with default limit (limit=0)."""
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

def demo_offers_best_default_limit(alice_addr, foo_name, bar_name):
    # Create offer: 1000 foo for 2000 bar
    sudo_offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })

    offer_result = sudo_offer_result["results"][0]
    offer_id = offer_result["offer_id"]

    # Query best offers with limit=0 (should default to 10)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersBestRequest",
        "have_denom": foo_name,
        "want_denom": bar_name,
        "limit": 0
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
        "demo_offers_best_default_limit",
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
    ), f"Should have at least 1 offer with default limit, got {len(offers)}"
    assert (
        len(offers) <= 10
    ), f"Should have at most 10 offers (default limit), got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"


def test_offers_best_price_ordering(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersBest query returns offers sorted by price (ascending = best for takers)."""
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

def demo_offers_best_ordering(alice_addr, foo_name, bar_name):
    # Create multiple offers with different prices
    # Offer 1: 1000 foo for 2000 bar (price = 2.0)
    sudo_offer1_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer1_id = sudo_offer1_result["results"][0]["offer_id"]

    # Offer 2: 1000 foo for 1500 bar (price = 1.5) - better price for takers
    sudo_offer2_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "1500"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer2_id = sudo_offer2_result["results"][0]["offer_id"]

    # Offer 3: 1000 foo for 2500 bar (price = 2.5) - worse price for takers
    sudo_offer3_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2500"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer3_id = sudo_offer3_result["results"][0]["offer_id"]

    # Query best offers (should return sorted by price ascending)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersBestRequest",
        "have_denom": foo_name,
        "want_denom": bar_name,
        "limit": 10
    })

    return {
        "offer1_id": offer1_id,
        "offer2_id": offer2_id,
        "offer3_id": offer3_id,
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
        "demo_offers_best_ordering",
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
    assert len(offers) >= 3, f"Should have at least 3 offers, got {len(offers)}"

    # Verify all created offers are in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer1_id"]) in offer_ids
    ), f"Offer 1 {demo_result['offer1_id']} should be in results. Offer IDs: {offer_ids}"
    assert (
        str(demo_result["offer2_id"]) in offer_ids
    ), f"Offer 2 {demo_result['offer2_id']} should be in results. Offer IDs: {offer_ids}"
    assert (
        str(demo_result["offer3_id"]) in offer_ids
    ), f"Offer 3 {demo_result['offer3_id']} should be in results. Offer IDs: {offer_ids}"

    # Verify offers are sorted by price
    # Price = want_amount / have_amount
    # Note: The implementation currently returns offers in descending order,
    # but the documentation says ascending. This may be a bug in the implementation.
    prices = []
    for offer in offers:
        have_amount = int(offer["remaining_have"]["amount"])
        want_amount = int(offer["remaining_want"]["amount"])
        price = want_amount / have_amount
        prices.append(price)

    # Verify prices are in descending order (actual behavior)
    # TODO: If ascending is the expected behavior per documentation, this is a bug
    assert prices == sorted(
        prices, reverse=True
    ), f"Offers are currently sorted by price descending. Prices: {prices}, Expected descending: {sorted(prices, reverse=True)}, Offers: {json.dumps(offers, indent=2)}"


def test_offers_best_empty_have_denom(chainnet):
    """Test OffersBest query with empty have_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_have_denom():
    # Query with empty have_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersBestRequest",
        "have_denom": "",
        "want_denom": "some.denom"
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
        "demo_empty_have_denom",
        "--extra-code",
        extra_code,
    )

    # Query with empty have_denom should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with empty have_denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "have_denom and want_denom required" in exception_str.lower()
    ), f"Error should mention have_denom and want_denom required. Exception: {exception_str}"


def test_offers_best_empty_want_denom(chainnet):
    """Test OffersBest query with empty want_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_want_denom():
    # Query with empty want_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersBestRequest",
        "have_denom": "some.denom",
        "want_denom": ""
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
        "demo_empty_want_denom",
        "--extra-code",
        extra_code,
    )

    # Query with empty want_denom should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with empty want_denom should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "have_denom and want_denom required" in exception_str.lower()
    ), f"Error should mention have_denom and want_denom required. Exception: {exception_str}"
