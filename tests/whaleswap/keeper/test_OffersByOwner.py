"""
Test OffersByOwner query for whaleswap offers.

Tests the QueryOffersByOwner endpoint which retrieves offers owned by
a specific address, optionally filtered by status.
Covers happy paths and error cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_offers_by_owner_no_status(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByOwner query without status filter."""
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

def demo_offers_by_owner_no_status(alice_addr, foo_name, bar_name):
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

    # Query offers by owner without status filter
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByOwnerRequest",
        "owner": alice_addr
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
        "demo_offers_by_owner_no_status",
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
    ), f"Should have at least 1 offer for owner, got {len(offers)}"

    # Verify the created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"

    # Verify offer structure and owner
    offer_index = offer_ids.index(str(demo_result["offer_id"]))
    found_offer = offers[offer_index]
    assert (
        "maker" in found_offer
    ), f"Offer missing 'maker' key. Keys: {list(found_offer.keys())}"
    assert (
        found_offer["maker"] == alice_addr
    ), f"Offer maker should be {alice_addr}, got {found_offer['maker']}"


def test_offers_by_owner_with_status_open(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test OffersByOwner query with status='open'."""
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

def demo_offers_by_owner_status_open(alice_addr, foo_name, bar_name):
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

    # Query offers by owner with status='open'
    offers_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByOwnerRequest",
        "owner": alice_addr,
        "status": "open"
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
        "demo_offers_by_owner_status_open",
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
    ), f"Should have at least 1 open offer for owner, got {len(offers)}"

    # Verify created offer is in results
    offer_ids = [str(offer["offer_id"]) for offer in offers]
    assert (
        str(demo_result["offer_id"]) in offer_ids
    ), f"Created offer {demo_result['offer_id']} should be in results. Offer IDs: {offer_ids}, Offers: {json.dumps(offers, indent=2)}"

    # Verify all offers are open and owned by alice
    for offer in offers:
        assert (
            offer["status"] == "open"
        ), f"All offers should have status 'open', got {offer['status']}"
        assert (
            offer["maker"] == alice_addr
        ), f"All offers should be owned by {alice_addr}, got {offer['maker']}"


def test_offers_by_owner_empty_owner(chainnet):
    """Test OffersByOwner query with empty owner."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_empty_owner():
    # Query with empty owner should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByOwnerRequest",
        "owner": ""
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
        "demo_empty_owner",
        "--extra-code",
        extra_code,
    )

    # Query with empty owner should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with empty owner should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "owner required" in exception_str.lower()
    ), f"Error should mention owner required. Exception: {exception_str}"


def test_offers_by_owner_invalid_status(chainnet, leverage_accounts):
    """Test OffersByOwner query with invalid status."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_invalid_status(alice_addr):
    # Query with invalid status should fail
    result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByOwnerRequest",
        "owner": alice_addr,
        "status": "invalid_status"
    })
    return {"result": result}
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
        "demo_invalid_status",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Query with invalid status should fail
    assert (
        query_result.get("exception") is not None
    ), f"Query with invalid status should fail with exception. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2)
    assert (
        "invalid status" in exception_str.lower()
    ), f"Error should mention invalid status. Exception: {exception_str}"
