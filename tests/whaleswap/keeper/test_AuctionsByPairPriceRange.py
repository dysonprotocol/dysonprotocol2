"""
AuctionsByPairPriceRange query handler coverage tests.

Tests the AuctionsByPairPriceRange query endpoint which retrieves auctions
for a denom pair with optional price bounds. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_auctions_by_pair_price_range_no_bounds(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AuctionsByPairPriceRange query without price bounds."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create auction using multi-block transaction
    tx_auction = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        bar_name,
        "--sell",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        tx_auction.get("code", 1) == 0
    ), f"Open auction failed: {json.dumps(tx_auction, indent=2)}"

    # Extract auction_id from events
    auction_events = [
        e
        for e in tx_auction.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    assert (
        auction_events
    ), f"Missing EventAuctionCreated: {json.dumps(tx_auction, indent=2)}"
    auction_attrs = {
        a.get("key"): a.get("value") for a in auction_events[0].get("attributes", [])
    }
    auction_id = auction_attrs.get("auction_id")
    assert auction_id, f"auction_id missing: {json.dumps(auction_events[0], indent=2)}"
    auction_id = auction_id.strip('"')

    # Query auctions by pair without price bounds using CLI
    auctions_response = dysond(
        "query",
        "whaleswap",
        "auctions-by-pair-price-range",
        "--sell-denom",
        foo_name,
        "--bid-denom",
        bar_name,
    )

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"AuctionsByPairPriceRange response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"AuctionsByPairPriceRange response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Verify auction is in results
    auction_ids_found = [int(a.get("auction_id")) for a in auctions_list]
    assert (
        int(auction_id) in auction_ids_found
    ), f"Auction ID {auction_id} not found in pair results. Found IDs: {auction_ids_found}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_by_pair_price_range_with_min_price(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AuctionsByPairPriceRange query with min_price bound."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create auction using multi-block transaction
    tx_auction = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        bar_name,
        "--sell",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        tx_auction.get("code", 1) == 0
    ), f"Open auction failed: {json.dumps(tx_auction, indent=2)}"

    # Extract auction_id from events
    auction_events = [
        e
        for e in tx_auction.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    assert (
        auction_events
    ), f"Missing EventAuctionCreated: {json.dumps(tx_auction, indent=2)}"
    auction_attrs = {
        a.get("key"): a.get("value") for a in auction_events[0].get("attributes", [])
    }
    auction_id = auction_attrs.get("auction_id")
    assert auction_id, f"auction_id missing: {json.dumps(auction_events[0], indent=2)}"
    auction_id = auction_id.strip('"')

    # Query auctions by pair with min_price using CLI
    auctions_response = dysond(
        "query",
        "whaleswap",
        "auctions-by-pair-price-range",
        "--sell-denom",
        foo_name,
        "--bid-denom",
        bar_name,
        "--min-price",
        "0.5",
    )

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"AuctionsByPairPriceRange response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"AuctionsByPairPriceRange response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_by_pair_price_range_with_max_price(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AuctionsByPairPriceRange query with max_price bound."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create auction using multi-block transaction
    tx_auction = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        bar_name,
        "--sell",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        tx_auction.get("code", 1) == 0
    ), f"Open auction failed: {json.dumps(tx_auction, indent=2)}"

    # Extract auction_id from events
    auction_events = [
        e
        for e in tx_auction.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventAuctionCreated"
    ]
    assert (
        auction_events
    ), f"Missing EventAuctionCreated: {json.dumps(tx_auction, indent=2)}"
    auction_attrs = {
        a.get("key"): a.get("value") for a in auction_events[0].get("attributes", [])
    }
    auction_id = auction_attrs.get("auction_id")
    assert auction_id, f"auction_id missing: {json.dumps(auction_events[0], indent=2)}"
    auction_id = auction_id.strip('"')

    # Query auctions by pair with max_price using CLI
    auctions_response = dysond(
        "query",
        "whaleswap",
        "auctions-by-pair-price-range",
        "--sell-denom",
        foo_name,
        "--bid-denom",
        bar_name,
        "--max-price",
        "10.0",
    )

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"AuctionsByPairPriceRange response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"AuctionsByPairPriceRange response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_by_pair_price_range_empty_sell_denom(chainnet):
    """Test AuctionsByPairPriceRange query with empty sell_denom."""
    dysond = chainnet[0]

    # Query auctions by pair with empty sell_denom (should fail)
    result = dysond(
        "query",
        "whaleswap",
        "auctions-by-pair-price-range",
        "--sell-denom",
        "",
        "--bid-denom",
        "udys",
    )

    # Should return error
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "sell_denom and bid_denom required" in result.lower()
    ), f"Expected 'sell_denom and bid_denom required' error. Got: {result}"


def test_auctions_by_pair_price_range_empty_bid_denom(chainnet):
    """Test AuctionsByPairPriceRange query with empty bid_denom."""
    dysond = chainnet[0]

    # Query auctions by pair with empty bid_denom (should fail)
    result = dysond(
        "query",
        "whaleswap",
        "auctions-by-pair-price-range",
        "--sell-denom",
        "udys",
        "--bid-denom",
        "",
    )

    # Should return error
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "sell_denom and bid_denom required" in result.lower()
    ), f"Expected 'sell_denom and bid_denom required' error. Got: {result}"


def test_auctions_by_pair_price_range_invalid_min_price(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AuctionsByPairPriceRange query with invalid min_price."""
    dysond = chainnet[0]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Query auctions by pair with invalid min_price (should fail)
    # Note: CLI validates decimal format before reaching Go code
    result = dysond(
        "query",
        "whaleswap",
        "auctions-by-pair-price-range",
        "--sell-denom",
        foo_name,
        "--bid-denom",
        bar_name,
        "--min-price",
        "invalid_price",
    )

    # Should return error (CLI validates before Go code)
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "failed to set decimal string" in result.lower()
    ), f"Expected CLI decimal validation error. Got: {result}"


def test_auctions_by_pair_price_range_invalid_max_price(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AuctionsByPairPriceRange query with invalid max_price."""
    dysond = chainnet[0]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Query auctions by pair with invalid max_price (should fail)
    # Note: CLI validates decimal format before reaching Go code
    result = dysond(
        "query",
        "whaleswap",
        "auctions-by-pair-price-range",
        "--sell-denom",
        foo_name,
        "--bid-denom",
        bar_name,
        "--max-price",
        "not_a_number",
    )

    # Should return error (CLI validates before Go code)
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "failed to set decimal string" in result.lower()
    ), f"Expected CLI decimal validation error. Got: {result}"

