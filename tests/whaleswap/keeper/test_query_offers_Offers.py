"""
Test Offers query for whaleswap offers.

Tests the QueryOffers endpoint which provides unified offer listing with
optional denom filters and pagination. Supports multiple query patterns:
- Both have_denom and want_denom: uses OffersByPairPrice index
- Only have_denom: uses OffersByHave index
- Only want_denom: uses OffersByWant index
- No filters: direct pagination over OffersMap
Covers happy paths for all query patterns.
"""

import json
import pytest
from deep_parse import deep_parse


def test_offers_with_both_denoms(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Offers query with both have_denom and want_denom."""
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

def demo_offers_both_denoms(alice_addr, foo_name, bar_name):
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

    # Query offers with both have_denom and want_denom
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersRequest",
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
        "demo_offers_both_denoms",
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


def test_offers_with_only_have_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Offers query with only have_denom."""
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

def demo_offers_only_have(alice_addr, foo_name, bar_name):
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

    # Query offers with only have_denom
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersRequest",
        "have_denom": foo_name
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
        "demo_offers_only_have",
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
    ), f"Should have at least 1 offer with have_denom, got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"

    # Verify all offers have the correct have_denom
    for offer in offers:
        assert (
            "remaining_have" in offer
        ), f"Offer missing 'remaining_have' key. Keys: {list(offer.keys())}"
        assert (
            offer["remaining_have"]["denom"] == foo_name
        ), f"All offers should have have_denom {foo_name}, got {offer['remaining_have']['denom']}"


def test_offers_with_only_want_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Offers query with only want_denom."""
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

def demo_offers_only_want(alice_addr, foo_name, bar_name):
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

    # Query offers with only want_denom
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersRequest",
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
        "demo_offers_only_want",
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
    ), f"Should have at least 1 offer with want_denom, got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"

    # Verify all offers have the correct want_denom
    for offer in offers:
        assert (
            "remaining_want" in offer
        ), f"Offer missing 'remaining_want' key. Keys: {list(offer.keys())}"
        assert (
            offer["remaining_want"]["denom"] == bar_name
        ), f"All offers should have want_denom {bar_name}, got {offer['remaining_want']['denom']}"


def test_offers_with_no_filters(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Offers query with no filters."""
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

def demo_offers_no_filters(alice_addr, foo_name, bar_name):
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

    # Query offers with no filters
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersRequest"
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
        "demo_offers_no_filters",
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
    assert (
        "pagination" in offers_query
    ), f"Offers query missing 'pagination' key. Keys: {list(offers_query.keys())}"

    offers = offers_query["offers"]
    assert isinstance(offers, list), f"Offers should be list, got {type(offers)}"
    assert (
        len(offers) >= 1
    ), f"Should have at least 1 offer (no filters), got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"


def test_offers_with_both_denoms_reversed_order(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Offers query with both denoms where have > want lexicographically (triggers swap).

    Uses bar_name as have and foo_name as want. If bar_name > foo_name lexicographically,
    this will trigger the canonicalization swap branch (lines 120-121).
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Use bar_name as have and foo_name as want
    # This will trigger swap if bar_name > foo_name lexicographically
    have_denom = bar_name
    want_denom = foo_name

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

def demo_offers_reversed_order(alice_addr, have_denom, want_denom):
    # Create offer with have > want lexicographically
    sudo_offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": have_denom, "amount": "1000"},
        "want": {"denom": want_denom, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })

    offer_result = sudo_offer_result["results"][0]
    offer_id = offer_result["offer_id"]

    # Query with have > want (should trigger canonicalization swap)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersRequest",
        "have_denom": have_denom,
        "want_denom": want_denom
    })

    return {
        "offer_id": offer_id,
        "offers_query": offers_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "have_denom": have_denom,
            "want_denom": want_denom,
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
        "demo_offers_reversed_order",
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
    ), f"Should have at least 1 offer for pair (with canonicalization), got {len(offers)}"

    # Verify the created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"


def test_offers_both_denoms_with_other_pairs(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Offers query with both denoms when other pairs exist (covers pair key mismatch branch).

    This test triggers lines 130-131 where k1 != pairKey filters out offers from other pairs.
    Uses udys as a third denom to create a different pair.
    """
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

def demo_offers_other_pairs(alice_addr, foo_name, bar_name):
    # Create offer 1: foo for bar (target pair - will canonicalize to foo|bar or bar|foo)
    sudo_offer1_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer1_id = sudo_offer1_result["results"][0]["offer_id"]

    # Create offer 2: foo for udys (different pair - will canonicalize to foo|udys or udys|foo)
    # This creates a different pairKey in the OffersByPairPrice index
    # When querying for foo|bar, the iterator will encounter foo|udys keys
    # and the predicate at line 130-131 will filter them out (k1 != pairKey)
    sudo_offer2_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": "udys", "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer2_id = sudo_offer2_result["results"][0]["offer_id"]

    # Query for foo|bar pair
    # The iterator will encounter both foo|bar and foo|udys keys
    # Lines 130-131 will filter out foo|udys keys (k1 != pairKey)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersRequest",
        "have_denom": foo_name,
        "want_denom": bar_name
    })

    return {
        "offer1_id": offer1_id,
        "offer2_id": offer2_id,
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
        "demo_offers_other_pairs",
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
    assert len(offers) >= 1, f"Should have at least 1 offer for pair, got {len(offers)}"

    # Verify created offers are in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer1_id"]) in offer_ids
    ), f"Offer 1 {demo_result['offer1_id']} should be in results. Offer IDs: {offer_ids}"


def test_offers_only_have_with_other_have_denoms(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Offers query with only have_denom when other have denoms exist (covers have denom mismatch branch).

    This test triggers lines 163-164 where k1 != have filters out offers with different have denoms.
    """
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

def demo_offers_other_have_denoms(alice_addr, foo_name, bar_name):
    # Create offer 1: foo for bar (target have denom)
    sudo_offer1_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer1_id = sudo_offer1_result["results"][0]["offer_id"]

    # Create offer 2: bar for foo (different have denom)
    # This ensures the OffersByHave index contains keys for both denoms
    # When querying for foo_name, the iterator will encounter bar_name keys
    # and the predicate at line 163-164 will filter them out
    sudo_offer2_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": bar_name, "amount": "1000"},
        "want": {"denom": foo_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer2_id = sudo_offer2_result["results"][0]["offer_id"]

    # Query with only have_denom = foo_name
    # The iterator will encounter both foo_name and bar_name keys
    # Lines 163-164 will filter out bar_name keys (k1 != have)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersRequest",
        "have_denom": foo_name
    })

    return {
        "offer1_id": offer1_id,
        "offer2_id": offer2_id,
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
        "demo_offers_other_have_denoms",
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
    ), f"Should have at least 1 offer with have_denom={foo_name}, got {len(offers)}"

    # Verify offer1 (foo for bar) is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer1_id"]) in offer_ids
    ), f"Offer 1 {demo_result['offer1_id']} should be in results. Offer IDs: {offer_ids}"

    # Verify all offers have foo_name as have_denom (filtering worked)
    for offer in offers:
        assert (
            offer["remaining_have"]["denom"] == foo_name
        ), f"All offers should have have_denom={foo_name}, got {offer['remaining_have']['denom']}"


def test_offers_only_want_with_other_want_denoms(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Offers query with only want_denom when other want denoms exist (covers want denom mismatch branch).

    This test triggers lines 196-197 where k1 != want filters out offers with different want denoms.
    """
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

def demo_offers_other_want_denoms(alice_addr, foo_name, bar_name):
    # Create offer 1: foo for bar (target want denom)
    sudo_offer1_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer1_id = sudo_offer1_result["results"][0]["offer_id"]

    # Create offer 2: bar for foo (different want denom)
    # This ensures the OffersByWant index contains keys for both denoms
    # When querying for bar_name, the iterator will encounter foo_name keys
    # and the predicate at line 196-197 will filter them out
    sudo_offer2_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": bar_name, "amount": "1000"},
        "want": {"denom": foo_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer2_id = sudo_offer2_result["results"][0]["offer_id"]

    # Query with only want_denom = bar_name
    # The iterator will encounter both bar_name and foo_name keys
    # Lines 196-197 will filter out foo_name keys (k1 != want)
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersRequest",
        "want_denom": bar_name
    })

    return {
        "offer1_id": offer1_id,
        "offer2_id": offer2_id,
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
        "demo_offers_other_want_denoms",
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
    ), f"Should have at least 1 offer with want_denom={bar_name}, got {len(offers)}"

    # Verify offer1 (foo for bar) is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer1_id"]) in offer_ids
    ), f"Offer 1 {demo_result['offer1_id']} should be in results. Offer IDs: {offer_ids}"

    # Verify all offers have bar_name as want_denom (filtering worked)
    for offer in offers:
        assert (
            offer["remaining_want"]["denom"] == bar_name
        ), f"All offers should have want_denom={bar_name}, got {offer['remaining_want']['denom']}"
