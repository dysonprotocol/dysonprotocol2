#!/usr/bin/env python3
"""
Clean deprecated fields from whaleswap genesis export.

This script removes deprecated protobuf fields that were removed in newer
versions of the whaleswap module, allowing the genesis to be imported
successfully.

Usage:
    python clean_whaleswap_genesis.py input.json output.json
    or
    python clean_whaleswap_genesis.py input.json  # overwrites input
"""

import json
import sys
from typing import Dict, Any, List


def clean_pool(pool: Dict[str, Any]) -> Dict[str, Any]:
    """Remove deprecated fields from a Pool object."""
    deprecated_fields = [
        "block_height",
        "created",
        "updated",
        "min_price",
        "max_price",
        "max_leverage_ratio",
    ]

    removed_fields = []
    for field in deprecated_fields:
        if field in pool:
            pool.pop(field)
            removed_fields.append(field)

    if removed_fields:
        print(f"  Removed deprecated fields from pool: {removed_fields}")

    return pool


def clean_trade(trade: Dict[str, Any]) -> Dict[str, Any]:
    """Remove deprecated fields from a Trade object."""
    deprecated_fields = [
        "offer_id",
        "taker",
        "height_deprecated",
        "timestamp_deprecated",
        "sent",
        "received",
        "pool_id",
        "auction_id",
        "note_deprecated",
    ]

    removed_fields = []
    for field in deprecated_fields:
        if field in trade:
            trade.pop(field)
            removed_fields.append(field)

    if removed_fields:
        print(f"  Removed deprecated fields from trade: {removed_fields}")

    return trade


def clean_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    """Remove deprecated fields from an OfferData object."""
    deprecated_fields = ["updated_timestamp"]

    removed_fields = []
    for field in deprecated_fields:
        if field in offer:
            offer.pop(field)
            removed_fields.append(field)

    if removed_fields:
        print(f"  Removed deprecated fields from offer: {removed_fields}")

    return offer


def clean_whaleswap_genesis(genesis: Dict[str, Any]) -> Dict[str, Any]:
    """Clean deprecated fields from whaleswap app_state."""
    if "app_state" not in genesis:
        return genesis

    app_state = genesis["app_state"]
    if "whaleswap" not in app_state:
        return genesis

    whaleswap = app_state["whaleswap"]

    # Handle nested whaleswap structure (export format)
    if "whaleswap" in whaleswap:
        whaleswap = whaleswap["whaleswap"]

    print("Found whaleswap state, cleaning deprecated fields...")

    # Clean pools
    if "pools" in whaleswap and isinstance(whaleswap["pools"], list):
        cleaned_pools = []
        for pool in whaleswap["pools"]:
            if isinstance(pool, dict):
                cleaned_pools.append(clean_pool(pool))
        whaleswap["pools"] = cleaned_pools
        print(f"Cleaned {len(cleaned_pools)} pools")

    # Clean offers
    if "offers" in whaleswap and isinstance(whaleswap["offers"], list):
        cleaned_offers = []
        for offer in whaleswap["offers"]:
            if isinstance(offer, dict):
                cleaned_offers.append(clean_offer(offer))
        whaleswap["offers"] = cleaned_offers
        print(f"Cleaned {len(cleaned_offers)} offers")

    # Clean trades
    if "trades" in whaleswap and isinstance(whaleswap["trades"], list):
        cleaned_trades = []
        for trade in whaleswap["trades"]:
            if isinstance(trade, dict):
                cleaned_trades.append(clean_trade(trade))
        whaleswap["trades"] = cleaned_trades
        print(f"Cleaned {len(cleaned_trades)} trades")

    return genesis


def main():
    if len(sys.argv) < 2:
        print("Usage: python clean_whaleswap_genesis.py input.json [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file

    print(f"Loading genesis from {input_file}...")

    try:
        with open(input_file, "r") as f:
            genesis = json.load(f)
    except FileNotFoundError:
        print(f"Error: File {input_file} not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {input_file}: {e}")
        sys.exit(1)

    # Clean the genesis
    cleaned_genesis = clean_whaleswap_genesis(genesis)

    # Save the cleaned genesis
    print(f"Saving cleaned genesis to {output_file}...")
    with open(output_file, "w") as f:
        json.dump(cleaned_genesis, f, indent=2, separators=(",", ": "))

    print("Done! Genesis export has been cleaned of deprecated fields.")


if __name__ == "__main__":
    main()
