"""
Auctions query handler coverage tests.

Tests the Auctions query endpoint which provides unified auction listing
with optional denom filters and pagination. Covers all filter combinations
and code paths.
"""

import json
import pytest
from deep_parse import deep_parse


def test_auctions_no_filters(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Auctions query with no filters (paginates primary map)."""
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

    # Query auctions with no filters (tests no filters path - lines 155-168)
    auctions_response = dysond("query", "whaleswap", "auctions")

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"Auctions response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"Auctions response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_sell_and_bid_filters(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Auctions query with both sell_denom and bid_denom filters."""
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

    # Query auctions with both filters (tests sell != "" && bid != "" path - lines 66-92)
    auctions_response = dysond(
        "query",
        "whaleswap",
        "auctions",
        "--sell-denom",
        foo_name,
        "--bid-denom",
        bar_name,
    )

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"Auctions response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"Auctions response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Verify auction is in results
    auction_ids_found = [int(a.get("auction_id")) for a in auctions_list]
    assert (
        int(auction_id) in auction_ids_found
    ), f"Auction ID {auction_id} not found in filtered results. Found IDs: {auction_ids_found}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_sell_filter_only(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Auctions query with only sell_denom filter."""
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

    # Query auctions with only sell filter (tests sell != "" path - lines 94-122)
    auctions_response = dysond(
        "query", "whaleswap", "auctions", "--sell-denom", foo_name
    )

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"Auctions response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"Auctions response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Verify auction is in results
    auction_ids_found = [int(a.get("auction_id")) for a in auctions_list]
    assert (
        int(auction_id) in auction_ids_found
    ), f"Auction ID {auction_id} not found in filtered results. Found IDs: {auction_ids_found}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_bid_filter_only(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test Auctions query with only bid_denom filter."""
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

    # Query auctions with only bid filter (tests bid != "" path - lines 124-152)
    auctions_response = dysond(
        "query", "whaleswap", "auctions", "--bid-denom", bar_name
    )

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"Auctions response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"Auctions response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Verify auction is in results
    auction_ids_found = [int(a.get("auction_id")) for a in auctions_list]
    assert (
        int(auction_id) in auction_ids_found
    ), f"Auction ID {auction_id} not found in filtered results. Found IDs: {auction_ids_found}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_nil_request(chainnet):
    """Test Auctions query with nil request (should default to empty request)."""
    dysond = chainnet[0]

    # Note: In Go, nil request is handled by defaulting to empty request
    # When calling via CLI without filters, it's equivalent to nil/empty request
    # This tests the req == nil path (line 58-60 in Go code)
    auctions_response = dysond("query", "whaleswap", "auctions")

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"Auctions response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"Auctions response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"
