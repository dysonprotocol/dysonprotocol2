"""
AddressMetrics tracking integration tests.

Tests that metrics are correctly incremented as transactions occur.
Uses multi-block testing to verify real transaction flow.
"""

import json
import pytest


@pytest.mark.usefixtures("faucet")
def test_metrics_pool_and_liquidity_ops(chainnet, generate_account, register_name):
    """Test pool creation and liquidity operation metrics."""
    dysond = chainnet[0]

    alice_name, alice_addr = generate_account("metrics_alice", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    # Mint coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * fee_per + 0.99999)

    for denom in [foo_name, bar_name]:
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{mint_amount}{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            alice_name,
        )

    # Create pool
    base, quote = sorted([foo_name, bar_name])
    tx_pool = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--fee-rate",
        f"0.003{base}",
        "--fee-rate",
        f"0.003{quote}",
        "--min-collateral-ratio",
        f"1.5{base}",
        "--min-collateral-ratio",
        f"1.5{quote}",
        "--max-leverage-ratio",
        f"20.0{base}",
        "--max-leverage-ratio",
        f"20.0{quote}",
        "--liquidation-threshold",
        f"1.2{base}",
        "--liquidation-threshold",
        f"1.2{quote}",
        "--max-borrow-percent",
        f"0.8{base}",
        "--max-borrow-percent",
        f"0.8{quote}",
        "--from",
        alice_name,
    )
    assert tx_pool.get("code", 1) == 0, f"Pool creation failed: {tx_pool}"

    # Extract pool_id
    pool_events = [
        e
        for e in tx_pool.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_events, f"Missing EventPoolCreated: {json.dumps(tx_pool, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id", "").strip('"')
    assert pool_id, f"pool_id missing: {pool_attrs}"

    # Query metrics after pool creation
    metrics_1 = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    assert (
        int(metrics_1["metrics"].get("pools_created", 0)) == 1
    ), f"Should have 1 pool: {metrics_1}"

    # Add liquidity
    tx_add = dysond(
        "tx",
        "whaleswap",
        "add-liquidity",
        "--pool-id",
        pool_id,
        "--amounts",
        f"5000{foo_name}",
        "--amounts",
        f"5000{bar_name}",
        "--from",
        alice_name,
    )
    assert tx_add.get("code", 1) == 0, f"Add liquidity failed: {tx_add}"

    # Query metrics after add
    metrics_2 = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    assert (
        int(metrics_2["metrics"].get("liquidity_adds", 0)) == 2
    ), f"Should have 2 adds (pool creation + explicit add): {metrics_2}"

    # Remove liquidity
    tx_remove = dysond(
        "tx",
        "whaleswap",
        "remove-liquidity",
        "--pool-id",
        pool_id,
        "--shares",
        "1000",
        "--from",
        alice_name,
    )
    assert tx_remove.get("code", 1) == 0, f"Remove liquidity failed: {tx_remove}"

    # Query metrics after remove
    metrics_3 = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    assert (
        int(metrics_3["metrics"].get("liquidity_adds", 0)) == 2
    ), f"Should still have 2 adds: {metrics_3}"
    assert (
        int(metrics_3["metrics"].get("liquidity_removes", 0)) == 1
    ), f"Should have 1 remove: {metrics_3}"


@pytest.mark.usefixtures("faucet")
def test_metrics_offers_lifecycle(chainnet, generate_account, register_name):
    """Test offer creation, close, and cancel metrics."""
    dysond = chainnet[0]

    alice_name, alice_addr = generate_account("metrics_offers", faucet_amount=5_000_000)
    bob_name, bob_addr = generate_account("metrics_bob", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    # Mint and distribute coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * fee_per + 0.99999)

    for denom in [foo_name, bar_name]:
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{mint_amount}{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            alice_name,
        )

    dysond(
        "tx",
        "bank",
        "send",
        alice_addr,
        bob_addr,
        f"300000{foo_name},300000{bar_name}",
        "--from",
        alice_name,
    )

    # Create offer
    tx_offer = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"100{foo_name}",
        "--want",
        f"50{bar_name}",
        "--settlement-mode",
        "settlement-escrow",
        "--from",
        alice_name,
    )
    assert tx_offer.get("code", 1) == 0, f"Make offer failed: {tx_offer}"

    # Extract offer_id
    offer_events = [
        e
        for e in tx_offer.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    assert offer_events, f"Missing EventOfferCreated: {json.dumps(tx_offer, indent=2)}"
    offer_attrs = {
        a.get("key"): a.get("value") for a in offer_events[0].get("attributes", [])
    }
    offer_id = offer_attrs.get("offer_id", "").strip('"')
    assert offer_id, f"offer_id missing: {offer_attrs}"

    # Query metrics after offer created
    metrics_1 = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    assert (
        int(metrics_1["metrics"].get("offers_created", 0)) == 1
    ), f"Should have 1 offer: {metrics_1}"

    # Take offer to close it
    tx_take = dysond(
        "tx",
        "whaleswap",
        "take-offer",
        "--trades",
        f"offer_id={int(offer_id)},take_units=",
        "--from",
        bob_name,
    )
    assert tx_take.get("code", 1) == 0, f"Take offer failed: {tx_take}"

    # Query metrics after offer closed
    metrics_2 = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    assert (
        int(metrics_2["metrics"].get("offers_created", 0)) == 1
    ), f"Should still show 1 created: {metrics_2}"
    assert (
        int(metrics_2["metrics"].get("offers_closed", 0)) == 1
    ), f"Should have 1 closed: {metrics_2}"

    # Create another offer and cancel it
    tx_offer_2 = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"200{bar_name}",
        "--want",
        f"100{foo_name}",
        "--settlement-mode",
        "settlement-escrow",
        "--from",
        alice_name,
    )
    assert tx_offer_2.get("code", 1) == 0, f"Make offer 2 failed: {tx_offer_2}"

    # Extract second offer_id
    offer_events_2 = [
        e
        for e in tx_offer_2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    offer_attrs_2 = {
        a.get("key"): a.get("value") for a in offer_events_2[0].get("attributes", [])
    }
    offer_id_2 = offer_attrs_2.get("offer_id", "").strip('"')

    # Cancel the second offer
    tx_cancel = dysond(
        "tx",
        "whaleswap",
        "cancel-offer",
        "--offer-id",
        offer_id_2,
        "--from",
        alice_name,
    )
    assert tx_cancel.get("code", 1) == 0, f"Cancel offer failed: {tx_cancel}"

    # Query final metrics
    metrics_3 = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    assert (
        int(metrics_3["metrics"].get("offers_created", 0)) == 2
    ), f"Should have 2 created: {metrics_3}"
    assert (
        int(metrics_3["metrics"].get("offers_closed", 0)) == 1
    ), f"Should have 1 closed: {metrics_3}"
    assert (
        int(metrics_3["metrics"].get("offers_cancelled", 0)) == 1
    ), f"Should have 1 cancelled: {metrics_3}"


@pytest.mark.usefixtures("faucet")
def test_metrics_auction_tracking(chainnet, generate_account, register_name):
    """Test auction metrics tracking."""
    dysond = chainnet[0]

    alice_name, alice_addr = generate_account(
        "metrics_auction", faucet_amount=5_000_000
    )
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    # Mint coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * fee_per + 0.99999)

    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{mint_amount}{foo_name}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        alice_name,
    )

    # Open auction
    tx_auction = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--bid-denom",
        "udys",
        "--sell",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert tx_auction.get("code", 1) == 0, f"Open auction failed: {tx_auction}"

    # Query metrics
    metrics = dysond("query", "whaleswap", "address-metrics", f"--address={alice_addr}")
    assert (
        int(metrics["metrics"].get("auctions_created", 0)) == 1
    ), f"Should have 1 auction: {metrics}"
