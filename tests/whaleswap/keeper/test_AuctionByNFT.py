"""
AuctionByNFT query handler coverage tests.

Tests the AuctionByNFT query endpoint which retrieves an auction
by its NFT escrow markers (class_id and nft_id). Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_auction_by_nft_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AuctionByNFT query with valid NFT identifiers."""
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

    # Extract auction_id and NFT info from events
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

    # Query auction to get class_id and nft_id
    auction_query = dysond("query", "whaleswap", "auction", "--auction-id", auction_id)
    auction = auction_query.get("auction")
    assert auction, f"Auction not found: {json.dumps(auction_query, indent=2)}"
    class_id = auction.get("class_id")
    nft_id = auction.get("nft_id")
    assert class_id, f"class_id missing: {json.dumps(auction, indent=2)}"
    assert nft_id, f"nft_id missing: {json.dumps(auction, indent=2)}"

    # Query auction by NFT using CLI
    auction_by_nft_response = dysond(
        "query",
        "whaleswap",
        "auction-by-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
    )

    # Validate response structure (Type)
    assert isinstance(
        auction_by_nft_response, dict
    ), f"AuctionByNFT response should be dict, got {type(auction_by_nft_response)}. Full response: {json.dumps(auction_by_nft_response, indent=2)}"
    assert (
        "auction" in auction_by_nft_response
    ), f"AuctionByNFT response missing 'auction' key. Keys: {list(auction_by_nft_response.keys())}. Full response: {json.dumps(auction_by_nft_response, indent=2)}"

    # Validate auction structure (Type + Shape)
    found_auction = auction_by_nft_response["auction"]
    assert isinstance(
        found_auction, dict
    ), f"Auction should be dict, got {type(found_auction)}"

    # Validate values
    assert (
        int(found_auction.get("auction_id")) == int(auction_id)
    ), f"Auction ID mismatch: expected {auction_id}, got {found_auction.get('auction_id')}"
    assert (
        found_auction.get("class_id") == class_id
    ), f"Class ID mismatch: expected {class_id}, got {found_auction.get('class_id')}"
    assert (
        found_auction.get("nft_id") == nft_id
    ), f"NFT ID mismatch: expected {nft_id}, got {found_auction.get('nft_id')}"
    assert (
        found_auction.get("seller") == alice_addr
    ), f"Seller mismatch: expected {alice_addr}, got {found_auction.get('seller')}"


def test_auction_by_nft_empty_class_id(chainnet):
    """Test AuctionByNFT query with empty class_id."""
    dysond = chainnet[0]

    # Query auction by NFT with empty class_id (should fail)
    result = dysond(
        "query",
        "whaleswap",
        "auction-by-nft",
        "--class-id",
        "",
        "--nft-id",
        "0000000001",
    )

    # Should return error
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "class_id and nft_id required" in result.lower()
    ), f"Expected 'class_id and nft_id required' error. Got: {result}"


def test_auction_by_nft_empty_nft_id(chainnet):
    """Test AuctionByNFT query with empty nft_id."""
    dysond = chainnet[0]

    # Query auction by NFT with empty nft_id (should fail)
    result = dysond(
        "query",
        "whaleswap",
        "auction-by-nft",
        "--class-id",
        "whaleswap.dys/auction/udys",
        "--nft-id",
        "",
    )

    # Should return error
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "class_id and nft_id required" in result.lower()
    ), f"Expected 'class_id and nft_id required' error. Got: {result}"


def test_auction_by_nft_not_found(chainnet):
    """Test AuctionByNFT query with non-existent NFT."""
    dysond = chainnet[0]

    # Query auction by NFT that doesn't exist
    result = dysond(
        "query",
        "whaleswap",
        "auction-by-nft",
        "--class-id",
        "whaleswap.dys/auction/nonexistent",
        "--nft-id",
        "9999999999",
    )

    # Should return error
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "auction not found for nft" in result.lower()
    ), f"Expected 'auction not found for NFT' error. Got: {result}"

