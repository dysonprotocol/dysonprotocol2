"""
Offer query handler coverage tests.

Tests the Offer query endpoint which retrieves a single offer by ID.
Covers all validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_offer_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Offer query with valid offer ID."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create offer using multi-block transaction
    tx_offer = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"1000{foo_name}",
        "--want",
        f"500{bar_name}",
        "--from",
        alice_name,
    )
    assert (
        tx_offer.get("code", 1) == 0
    ), f"Make offer failed: {json.dumps(tx_offer, indent=2)}"

    # Extract offer_id from events
    offer_events = [
        e
        for e in tx_offer.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    assert offer_events, f"Missing EventOfferCreated: {json.dumps(tx_offer, indent=2)}"
    offer_attrs = {
        a.get("key"): a.get("value") for a in offer_events[0].get("attributes", [])
    }
    offer_id = offer_attrs.get("offer_id")
    assert offer_id, f"offer_id missing: {json.dumps(offer_events[0], indent=2)}"
    offer_id = offer_id.strip('"')

    # Query offer using CLI
    offer_response = dysond("query", "whaleswap", "offer", "--offer-id", offer_id)

    # Validate response structure (Type)
    assert isinstance(
        offer_response, dict
    ), f"Offer response should be dict, got {type(offer_response)}. Full response: {json.dumps(offer_response, indent=2)}"
    assert (
        "offer" in offer_response
    ), f"Offer response missing 'offer' key. Keys: {list(offer_response.keys())}. Full response: {json.dumps(offer_response, indent=2)}"

    offer = offer_response["offer"]

    # Validate offer structure (Type + Shape)
    assert isinstance(offer, dict), f"Offer should be dict, got {type(offer)}"
    assert (
        "offer_id" in offer
    ), f"Offer missing 'offer_id' key. Keys: {list(offer.keys())}"
    assert "maker" in offer, f"Offer missing 'maker' key. Keys: {list(offer.keys())}"
    assert (
        "initial_have" in offer
    ), f"Offer missing 'initial_have' key. Keys: {list(offer.keys())}"
    assert (
        "initial_want" in offer
    ), f"Offer missing 'initial_want' key. Keys: {list(offer.keys())}"

    # Validate values
    assert int(offer["offer_id"]) == int(
        offer_id
    ), f"Offer ID mismatch: expected {offer_id}, got {offer['offer_id']}"
    assert (
        offer["maker"] == alice_addr
    ), f"Maker mismatch: expected {alice_addr}, got {offer['maker']}"


def test_offer_zero_id(chainnet):
    """Test Offer query with zero offer ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_offer_zero_id():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": 0
    })
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
        "demo_offer_zero_id",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for zero offer_id. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "offer_id required" in exception_str
    ), f"Expected 'offer_id required' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"


def test_offer_not_found(chainnet):
    """Test Offer query with non-existent offer ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_offer_not_found():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": 999999
    })
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
        "demo_offer_not_found",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for non-existent offer. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "offer not found" in exception_str
    ), f"Expected 'offer not found' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"
