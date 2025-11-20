"""
Test OffersByPairPriceRange query for whaleswap offers.

Tests the QueryOffersByPairPriceRange endpoint which retrieves offers for a pair
whose price lies within optional bounds.
Covers happy paths and error cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_offers_by_pair_price_range_no_bounds(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByPairPriceRange query without price bounds."""
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

def demo_offers_by_pair_no_bounds(alice_addr, foo_name, bar_name):
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

    # Query offers by pair without price bounds
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByPairPriceRangeRequest",
        "have_denom": foo_name,
        "want_denom": bar_name
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
        "demo_offers_by_pair_no_bounds",
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
    assert len(offers) >= 1, f"Should have at least 1 offer for pair, got {len(offers)}"

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


def test_offers_by_pair_price_range_with_min_price(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByPairPriceRange query with min_price bound."""
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

def demo_offers_by_pair_min_price(alice_addr, foo_name, bar_name):
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

    # Query offers by pair with min_price = 1.5 (should include offer with price 2.0)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByPairPriceRangeRequest",
        "have_denom": foo_name,
        "want_denom": bar_name,
        "min_price": "1.5"
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
        "demo_offers_by_pair_min_price",
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
    ), f"Should have at least 1 offer matching min_price, got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results with min_price filter. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"


def test_offers_by_pair_price_range_with_max_price(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByPairPriceRange query with max_price bound."""
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

def demo_offers_by_pair_max_price(alice_addr, foo_name, bar_name):
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

    # Query offers by pair with max_price = 2.5 (should include offer with price 2.0)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByPairPriceRangeRequest",
        "have_denom": foo_name,
        "want_denom": bar_name,
        "max_price": "2.5"
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
        "demo_offers_by_pair_max_price",
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
    ), f"Should have at least 1 offer matching max_price, got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results with max_price filter. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"


def test_offers_by_pair_price_range_with_both_bounds(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByPairPriceRange query with both min_price and max_price bounds."""
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

def demo_offers_by_pair_both_bounds(alice_addr, foo_name, bar_name):
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

    # Query offers by pair with both bounds: min_price = 1.5, max_price = 2.5
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByPairPriceRangeRequest",
        "have_denom": foo_name,
        "want_denom": bar_name,
        "min_price": "1.5",
        "max_price": "2.5"
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
        "demo_offers_by_pair_both_bounds",
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
    ), f"Should have at least 1 offer matching both bounds, got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results with both bounds. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"


def test_offers_by_pair_price_range_empty_have_denom(chainnet):
    """Test OffersByPairPriceRange query with empty have_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_have_denom():
    # Query with empty have_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByPairPriceRangeRequest",
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


def test_offers_by_pair_price_range_empty_want_denom(chainnet):
    """Test OffersByPairPriceRange query with empty want_denom."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_want_denom():
    # Query with empty want_denom should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByPairPriceRangeRequest",
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


def test_offers_by_pair_price_range_invalid_min_price(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByPairPriceRange query with invalid min_price format."""
    dysond = chainnet[0]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_invalid_min_price(foo_name, bar_name):
    # Query with invalid min_price should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByPairPriceRangeRequest",
        "have_denom": foo_name,
        "want_denom": bar_name,
        "min_price": "not_a_number"
    })
    return {"result": result}
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
        "demo_invalid_min_price",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Query with invalid min_price should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with invalid min_price should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "invalid min_price" in exception_str.lower()
    ), f"Error should mention invalid min_price. Exception: {exception_str}"


def test_offers_by_pair_price_range_invalid_max_price(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByPairPriceRange query with invalid max_price format."""
    dysond = chainnet[0]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_invalid_max_price(foo_name, bar_name):
    # Query with invalid max_price should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByPairPriceRangeRequest",
        "have_denom": foo_name,
        "want_denom": bar_name,
        "max_price": "not_a_number"
    })
    return {"result": result}
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
        "demo_invalid_max_price",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Query with invalid max_price should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with invalid max_price should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "invalid max_price" in exception_str.lower()
    ), f"Error should mention invalid max_price. Exception: {exception_str}"
