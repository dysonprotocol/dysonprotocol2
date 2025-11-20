"""
TradesByOffer query handler coverage tests.

Tests the TradesByOffer query endpoint which retrieves all trades
involving a specific offer. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_trades_by_offer_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test TradesByOffer query with valid offer ID."""
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
    assert (
        offer_events
    ), f"Missing EventOfferCreated: {json.dumps(tx_offer, indent=2)}"
    offer_attrs = {
        a.get("key"): a.get("value") for a in offer_events[0].get("attributes", [])
    }
    offer_id = offer_attrs.get("offer_id")
    assert offer_id, f"offer_id missing: {json.dumps(offer_events[0], indent=2)}"
    offer_id = offer_id.strip('"')

    # Create trade taking the offer
    tx_trade = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"600{bar_name}",
        "--op",
        json.dumps({"take": {"offer_id": int(offer_id), "take_units": "1"}}),
        "--from",
        alice_name,
    )
    assert (
        tx_trade.get("code", 1) == 0
    ), f"Make trade failed: {json.dumps(tx_trade, indent=2)}"

    # Extract trade_id from events
    trade_events = [
        e
        for e in tx_trade.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        trade_events
    ), f"Missing EventTradeRecorded: {json.dumps(tx_trade, indent=2)}"
    trade_attrs = {
        a.get("key"): a.get("value") for a in trade_events[0].get("attributes", [])
    }
    trade_id = trade_attrs.get("trade_id")
    assert trade_id, f"trade_id missing: {json.dumps(trade_events[0], indent=2)}"
    trade_id = trade_id.strip('"')

    # Query trades by offer using CLI
    trades_response = dysond(
        "query", "whaleswap", "trades-by-offer", "--offer-id", offer_id
    )

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"TradesByOffer response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"TradesByOffer response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"

    # Verify trade is in results
    trade_ids_found = [int(t.get("trade_id")) for t in trades_list]
    assert (
        int(trade_id) in trade_ids_found
    ), f"Trade ID {trade_id} not found in offer's trades. Found IDs: {trade_ids_found}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_trades_by_offer_zero_id(chainnet):
    """Test TradesByOffer query with zero offer ID."""
    dysond = chainnet[0]

    # Query trades by offer with zero offer_id (should fail)
    result = dysond("query", "whaleswap", "trades-by-offer", "--offer-id", "0")

    # Should return error
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "offer_id required" in result.lower()
    ), f"Expected 'offer_id required' error. Got: {result}"


def test_trades_by_offer_no_trades(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test TradesByOffer query for offer with no trades."""
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
    assert (
        offer_events
    ), f"Missing EventOfferCreated: {json.dumps(tx_offer, indent=2)}"
    offer_attrs = {
        a.get("key"): a.get("value") for a in offer_events[0].get("attributes", [])
    }
    offer_id = offer_attrs.get("offer_id")
    assert offer_id, f"offer_id missing: {json.dumps(offer_events[0], indent=2)}"
    offer_id = offer_id.strip('"')

    # Query trades by offer (no trades yet)
    trades_response = dysond(
        "query", "whaleswap", "trades-by-offer", "--offer-id", offer_id
    )

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"TradesByOffer response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"TradesByOffer response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list is empty (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        len(trades_list) == 0
    ), f"Offer with no trades should return empty list. Got {len(trades_list)}: {json.dumps(trades_list, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"

