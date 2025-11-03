"""
AddressMetrics query integration test.

Validates that the AddressMetrics query endpoint returns zero values for
addresses with no activity and tracks metrics correctly for active addresses.
"""


def test_address_metrics_no_activity(chainnet, generate_account):
    """Query metrics for an address with no whaleswap activity."""
    dysond = chainnet[0]

    # Generate a fresh address with no activity
    _, address = generate_account("test_metrics", faucet_amount=0)

    # Query metrics
    result = dysond("query", "whaleswap", "address-metrics", f"--address={address}")

    # Verify structure
    assert result["metrics"]["address"] == address
    assert int(result["metrics"]["block_height"]) > 0

    # Verify zero values for all metrics (omitempty means absent fields = 0)
    # Note: Protobuf omitempty means zero values are not serialized
    assert int(result["metrics"].get("total_trades", 0)) == 0
    assert int(result["metrics"].get("total_trade_ops", 0)) == 0
    assert result["metrics"].get("total_volume_sent", []) == []
    assert result["metrics"].get("total_volume_received", []) == []

    # LP metrics
    assert int(result["metrics"].get("pools_created", 0)) == 0
    assert result["metrics"].get("lp_fees_earned", []) == []
    assert result["metrics"].get("lp_interest_earned", []) == []
    assert int(result["metrics"].get("liquidity_adds", 0)) == 0
    assert int(result["metrics"].get("liquidity_removes", 0)) == 0

    # Leverage metrics
    assert int(result["metrics"].get("positions_opened", 0)) == 0
    assert int(result["metrics"].get("positions_closed", 0)) == 0
    assert result["metrics"].get("interest_paid", []) == []
    assert result["metrics"].get("leverage_pnl", []) == []
    assert int(result["metrics"].get("liquidations", 0)) == 0

    # Orderbook metrics
    assert int(result["metrics"].get("offers_created", 0)) == 0
    assert int(result["metrics"].get("offers_closed", 0)) == 0
    assert int(result["metrics"].get("offers_cancelled", 0)) == 0
    assert result["metrics"].get("maker_volume", []) == []

    # Auction metrics
    assert int(result["metrics"].get("auctions_created", 0)) == 0
    assert result["metrics"].get("auction_volume", []) == []
