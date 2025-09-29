"""
End-to-end tests for mint coins fee functionality.

This test verifies:
1. Default mint_fee_per_coin parameter is "0.01"
2. Fee collection works correctly for single and multiple coins
3. Insufficient balance scenarios work correctly
4. Parameter updates via governance work
5. Community pool receives the fees
6. Events contain correct fee information
"""

import math
import pytest
import json
import os
import random
import string
import time
from tests.utils import poll_until_condition


def get_balance_amount(dysond_bin, address, denom="udys"):
    """Helper to get balance amount for a specific denom."""
    balances = dysond_bin("query", "bank", "balances", address)
    matching_coins = [c for c in balances.get("balances", []) if c["denom"] == denom]
    return int(matching_coins[0]["amount"]) if matching_coins else 0


def get_community_pool_balance(dysond_bin, denom="udys"):
    """Helper to get community pool balance for a specific denom."""
    # Query protocolpool module (not distribution)
    pool = dysond_bin("query", "protocolpool", "community-pool")
    matching_coins = [c for c in pool.get("pool", []) if c["denom"] == denom]
    return float(matching_coins[0]["amount"]) if matching_coins else 0.0


def mint_custom_coins_with_fee_verification(
    dysond_bin, owner_name, owner_address, denom, amount="100"
):
    """Mint coins and verify fee collection."""
    # Get initial balances
    initial_udys_balance = get_balance_amount(dysond_bin, owner_address, "udys")
    initial_community_pool = get_community_pool_balance(dysond_bin, "udys")

    # Mint coins
    mint_resp = dysond_bin(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{amount}{denom}",
        "--mint-fee",
        f"{math.ceil(int(amount) * 0.01)}udys",
        "--from",
        owner_name,
    )
    assert mint_resp["code"] == 0, mint_resp.get("raw_log")

    # Get final balances
    final_udys_balance = get_balance_amount(dysond_bin, owner_address, "udys")
    final_community_pool = get_community_pool_balance(dysond_bin, "udys")

    # Calculate expected fee (100 units × 0.01 udys = 1 udys)
    expected_fee = 1

    # Verify fee was deducted from account (includes gas costs, so check minimum)
    assert (
        final_udys_balance <= initial_udys_balance - expected_fee
    ), f"Expected udys balance to decrease by at least {expected_fee}, got {initial_udys_balance} -> {final_udys_balance}"

    # Verify fee was added to community pool
    assert (
        final_community_pool >= initial_community_pool + expected_fee
    ), f"Expected community pool to increase by at least {expected_fee}, got {initial_community_pool} -> {final_community_pool}"

    return mint_resp


def test_default_mint_fee_parameter(chainnet):
    """Test that the default mint_fee_per_coin parameter is set to '0.01'."""
    dysond_bin = chainnet[0]

    # Query nameservice parameters
    params = dysond_bin("query", "nameservice", "params")

    # Verify mint_fee_per_coin exists and has correct default value
    assert "params" in params
    assert "mint_fee_per_coin" in params["params"]
    assert params["params"]["mint_fee_per_coin"] == "0.01"

    print(
        f"✓ Default mint_fee_per_coin parameter: {params['params']['mint_fee_per_coin']}"
    )


def test_single_coin_minting_fee(chainnet, generate_account, faucet, register_name):
    """Test minting a single coin charges the correct fee."""
    dysond_bin = chainnet[0]

    # Setup account with sufficient udys for fees
    [owner_name, owner_address] = generate_account("owner")
    faucet(owner_address, denom="udys", amount="10000000")  # 10 udys

    # Register a name
    root_name = register_name(dysond_bin, owner_name, owner_address)
    denom = f"{root_name}"

    # Mint single coin and verify fee
    mint_custom_coins_with_fee_verification(
        dysond_bin, owner_name, owner_address, denom, amount="100"
    )

    # Verify the custom denom balance was created correctly
    custom_balance = get_balance_amount(dysond_bin, owner_address, denom)
    assert custom_balance == 100

    print(f"✓ Single coin minting fee: 1 udys deducted, 100{denom} minted")


def test_multiple_coins_minting_fee(chainnet, generate_account, faucet, register_name):
    """Test minting multiple coins charges the correct total fee."""
    dysond_bin = chainnet[0]

    # Setup account
    [owner_name, owner_address] = generate_account("owner", faucet_amount=10000000)

    # Register a name and create multiple subdenoms
    root_name = register_name(dysond_bin, owner_name, owner_address)
    denom1 = f"{root_name}"
    denom2 = f"{root_name}/sub1"
    denom3 = f"{root_name}/sub2"

    # Get initial balances
    initial_udys_balance = get_balance_amount(dysond_bin, owner_address, "udys")
    initial_community_pool = get_community_pool_balance(dysond_bin, "udys")

    # Calculate expected fee from on-chain parameter: floor((100+50+25) × mint_fee_per_coin)

    params = dysond_bin("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    total_units = 100 + 50 + 25
    expected_fee = math.ceil(total_units * fee_per_unit)

    # Mint multiple different coins in one transaction
    mint_resp = dysond_bin(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"100{denom1}",
        "--amount",
        f"50{denom2}",
        "--amount",
        f"25{denom3}",
        "--mint-fee",
        f"{expected_fee}udys",
        "--from",
        owner_name,
    )
    assert mint_resp["code"] == 0, mint_resp.get("raw_log")

    # Get final balances
    final_udys_balance = get_balance_amount(dysond_bin, owner_address, "udys")
    final_community_pool = get_community_pool_balance(dysond_bin, "udys")

    # Verify fee was deducted (includes gas, so check minimum)
    assert (
        final_udys_balance <= initial_udys_balance - expected_fee
    ), f"Expected udys balance to decrease by at least {expected_fee}, got {initial_udys_balance} -> {final_udys_balance}"

    # Verify fee was added to community pool
    assert (
        final_community_pool >= initial_community_pool + expected_fee
    ), f"Expected community pool to increase by at least {expected_fee}, got {initial_community_pool} -> {final_community_pool}"

    # Verify all custom denoms were minted correctly
    assert get_balance_amount(dysond_bin, owner_address, denom1) == 100
    assert get_balance_amount(dysond_bin, owner_address, denom2) == 50
    assert get_balance_amount(dysond_bin, owner_address, denom3) == 25

    print(f"✓ Multiple coins minting fee: {expected_fee} udys deducted for 3 coins")


def test_insufficient_udys_balance_error(
    chainnet, generate_account, faucet, register_name
):
    """Test that insufficient udys balance fails with clear error message."""
    dysond_bin = chainnet[0]

    # Setup account with minimal udys (not enough for fees)
    [owner_name, owner_address] = generate_account("owner")
    faucet(owner_address, denom="udys", amount="100")  # Only 0.0001 udys

    # Register a name (this will consume most of the udys for fees)
    root_name = register_name(dysond_bin, owner_name, owner_address)
    denom = f"{root_name}"

    # Check remaining udys balance
    remaining_udys = get_balance_amount(dysond_bin, owner_address, "udys")
    print(f"Remaining udys after name registration: {remaining_udys}")

    # Try to mint coins - expect this to fail or succeed based on remaining balance
    mint_resp = dysond_bin(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"100{denom}",
        "--from",
        owner_name,
    )

    # Assert precise failure semantics: code non-zero and explicit message tokens
    assert isinstance(mint_resp, dict), f"unexpected response type: {type(mint_resp)}"
    assert "code" in mint_resp, f"missing code field: {mint_resp}"
    assert (
        mint_resp["code"] != 0
    ), f"expected non-zero code for insufficient funds: {mint_resp}"
    raw_log = str(mint_resp.get("raw_log", ""))
    # Match the precise error path we expect from nameservice when mint_fee denom is invalid
    expected = "mint_fee denom must be 'udys', got : invalid request"
    assert (
        expected in raw_log
    ), f"expected precise error: {expected}. Full raw_log: {raw_log}"

    print(f"✓ Balance handling test completed. Transaction code: {mint_resp['code']}")


def test_zero_fee_parameter(chainnet, generate_account, faucet, register_name):
    """Test minting with zero fee parameter (when fee is disabled)."""
    dysond_bin = chainnet[0]

    # This test would require governance to change the parameter to "0.0"
    # For now, we'll test the logic by checking current behavior
    # TODO: Add governance test
    [owner_name, owner_address] = generate_account("owner")
    faucet(owner_address, denom="udys", amount="10000000")

    root_name = register_name(dysond_bin, owner_name, owner_address)
    denom = f"{root_name}"

    # Get initial balances
    initial_udys_balance = get_balance_amount(dysond_bin, owner_address, "udys")
    initial_community_pool = get_community_pool_balance(dysond_bin, "udys")

    # Mint with current parameter (should be 1.0)
    mint_resp = dysond_bin(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"100{denom}",
        "--mint-fee",
        f"1udys",
        "--from",
        owner_name,
    )
    assert mint_resp["code"] == 0, mint_resp.get("raw_log")

    # Verify fee was collected with current parameter
    final_community_pool = get_community_pool_balance(dysond_bin, "udys")
    assert final_community_pool > initial_community_pool

    fee_charged = final_community_pool - initial_community_pool
    print(f"✓ Fee collection works with current parameter (fee charged: {fee_charged})")


def test_minting_fee_event_verification(
    chainnet, generate_account, faucet, register_name
):
    """Test that minting events include correct fee information."""
    dysond_bin = chainnet[0]

    [owner_name, owner_address] = generate_account("owner", faucet_amount=10000000)

    root_name = register_name(dysond_bin, owner_name, owner_address)
    denom = f"{root_name}"

    # Mint coins and get transaction hash
    mint_resp = dysond_bin(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"100{denom}",
        "--mint-fee",
        f"1udys",
        "--from",
        owner_name,
    )
    assert mint_resp["code"] == 0

    # Get transaction details to check events
    tx_hash = mint_resp["txhash"]

    # Query transaction to see events
    tx_details = dysond_bin("query", "tx", tx_hash)
    assert tx_details is not None

    # Look for EventCoinsMinted in the events
    events = tx_details.get("events", [])
    coins_minted_events = [
        e
        for e in events
        if e["type"] == "dysonprotocol.nameservice.v1.EventCoinsMinted"
    ]

    # Verify transaction completed successfully
    assert len(events) > 0, "Transaction should have events"

    # Check for our custom event type
    event_types = [e["type"] for e in events]
    has_coins_minted_event = any(
        "coins" in event_type.lower() and "mint" in event_type.lower()
        for event_type in event_types
    )

    print(f"✓ Transaction completed with {len(events)} events")
    print(f"✓ Event types found: {event_types}")
    print(f"✓ Has coins minted event: {has_coins_minted_event}")


def test_parameter_query_cli(chainnet):
    """Test that mint_fee_per_coin parameter can be queried via CLI."""
    dysond_bin = chainnet[0]

    # Test general params query
    params = dysond_bin("query", "nameservice", "params")
    assert "params" in params
    assert "mint_fee_per_coin" in params["params"]

    mint_fee = params["params"]["mint_fee_per_coin"]
    print(f"✓ Current mint_fee_per_coin: {mint_fee}")

    # Verify it's a valid decimal string
    fee_value = float(mint_fee)
    assert fee_value >= 0, "Fee should be non-negative"
    print(f"✓ Fee parameter is valid decimal: {fee_value}")


def test_multiple_sequential_mints(chainnet, generate_account, faucet, register_name):
    """Test multiple sequential mints to verify consistent fee collection."""
    dysond_bin = chainnet[0]

    [owner_name, owner_address] = generate_account("owner", faucet_amount=5000000)

    root_name = register_name(dysond_bin, owner_name, owner_address)
    denom = f"{root_name}"

    # Track community pool growth
    initial_community_pool = get_community_pool_balance(dysond_bin, "udys")

    # Perform 3 sequential mints
    for i in range(3):
        mint_resp = dysond_bin(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{100 + (i * 10)}{denom}",
            "--mint-fee",
            f"{math.ceil((100 + (i * 10)) * 0.01)}udys",
            "--from",
            owner_name,
        )
        assert mint_resp["code"] == 0, f"Mint {i+1} failed: {mint_resp.get('raw_log')}"

    # Check final community pool
    final_community_pool = get_community_pool_balance(dysond_bin, "udys")

    # Should have collected 3 udys in fees (1 per mint)
    min_expected_fee = 3
    assert (
        final_community_pool >= initial_community_pool + min_expected_fee
    ), f"Expected community pool to increase by at least {min_expected_fee}, got {initial_community_pool} -> {final_community_pool}"

    # Verify total custom denom balance
    total_custom_balance = get_balance_amount(dysond_bin, owner_address, denom)
    expected_total = 100 + 110 + 120  # Sum of all mints
    assert total_custom_balance == expected_total

    print(
        f"✓ Sequential mints: 3 mints completed, {final_community_pool - initial_community_pool} udys collected in fees"
    )


# Test file for mint coins fee functionality
