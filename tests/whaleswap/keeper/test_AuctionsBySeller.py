"""
AuctionsBySeller query handler coverage tests.

Tests the AuctionsBySeller query endpoint which retrieves auctions
created by a specific seller address. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_auctions_by_seller_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AuctionsBySeller query with valid seller address."""
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

    # Query auctions by seller using CLI
    auctions_response = dysond(
        "query", "whaleswap", "auctions-by-seller", "--seller", alice_addr
    )

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"AuctionsBySeller response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"AuctionsBySeller response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Verify auction is in results
    auction_ids_found = [int(a.get("auction_id")) for a in auctions_list]
    assert (
        int(auction_id) in auction_ids_found
    ), f"Auction ID {auction_id} not found in seller's auctions. Found IDs: {auction_ids_found}"

    # Verify all auctions belong to seller
    for auction in auctions_list:
        assert (
            auction.get("seller") == alice_addr
        ), f"Auction {auction.get('auction_id')} seller mismatch: expected {alice_addr}, got {auction.get('seller')}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_auctions_by_seller_empty_seller(chainnet):
    """Test AuctionsBySeller query with empty seller address."""
    dysond = chainnet[0]

    # Query auctions by seller with empty seller (should fail)
    # Note: CLI validates empty address before reaching Go code
    result = dysond("query", "whaleswap", "auctions-by-seller", "--seller", "")

    # Should return error (CLI validates before Go code)
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    # CLI validates empty address before reaching Go code, so we get CLI error
    assert (
        "empty address string is not allowed" in result.lower()
    ), f"Expected CLI validation error for empty address. Got: {result}"


def test_auctions_by_seller_no_auctions(chainnet, generate_account, faucet):
    """Test AuctionsBySeller query for seller with no auctions."""
    dysond = chainnet[0]
    seller_name, seller_addr = generate_account("no_auctions_seller", faucet_amount=1_000_000)

    # Query auctions by seller who has no auctions
    auctions_response = dysond(
        "query", "whaleswap", "auctions-by-seller", "--seller", seller_addr
    )

    # Validate response structure (Type)
    assert isinstance(
        auctions_response, dict
    ), f"AuctionsBySeller response should be dict, got {type(auctions_response)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        "pagination" in auctions_response
    ), f"AuctionsBySeller response missing 'pagination' key. Keys: {list(auctions_response.keys())}. Full response: {json.dumps(auctions_response, indent=2)}"

    # Validate auctions list is empty (Type + Shape)
    auctions_list = auctions_response.get("auctions", [])
    assert isinstance(
        auctions_list, list
    ), f"Auctions should be list, got {type(auctions_list)}. Full response: {json.dumps(auctions_response, indent=2)}"
    assert (
        len(auctions_list) == 0
    ), f"Seller with no auctions should return empty list. Got {len(auctions_list)}: {json.dumps(auctions_list, indent=2)}"

    # Validate pagination (Type)
    pagination = auctions_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"

