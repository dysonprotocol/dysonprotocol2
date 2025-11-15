"""
Simple test to reproduce the exact whaleswap position panic and capture details.
This focuses on creating the conditions that trigger the panic.
"""

import json


def test_reproduce_position_panic_simple(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Simple test that reproduces the panic by creating many positions and querying them.
    The panic occurs when querying positions-by-address with specific pool IDs.
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create multiple pools to increase complexity
    pool_ids = []
    for i in range(3):
        pool_result = dysond(
            "tx",
            "whaleswap",
            "create-pool",
            "--coins",
            f"10000{foo_name}",
            "--coins",
            f"10000{bar_name}",
            "--min-collateral-ratio",
            "1.5",
            "--liquidation-threshold",
            "1.2",
            "--max-borrow-percent",
            "0.8",
            "--from",
            alice_name,
        )
        assert (
            pool_result.get("code", 1) == 0
        ), f"create-pool {i} failed: {json.dumps(pool_result, indent=2)}"

        # Extract pool_id from events
        pool_events = [
            e
            for e in pool_result.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
        ]
        assert pool_events, f"missing EventPoolCreated for pool {i}"
        pool_attrs = {
            a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
        }
        pool_id = pool_attrs.get("pool_id")
        assert pool_id, f"pool_id missing for pool {i}"
        pool_id = pool_id.strip('"')
        pool_ids.append(pool_id)

    # Create many positions rapidly across different pools
    position_ids = []
    for pool_id in pool_ids:
        for j in range(5):  # 5 positions per pool
            pos_result = dysond(
                "tx",
                "whaleswap",
                "open-position",
                "--pool-id",
                pool_id,
                "--collateral",
                f"750{bar_name}",
                "--borrow",
                f"500{foo_name}",
                "--from",
                alice_name,
            )
            assert (
                pos_result.get("code", 1) == 0
            ), f"open-position failed for pool {pool_id}, pos {j}: {json.dumps(pos_result, indent=2)}"

            # Extract position ID
            pos_events = [
                e
                for e in pos_result.get("events", [])
                if e.get("type")
                == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
            ]
            assert pos_events, f"missing position event for pool {pool_id}, pos {j}"
            pos_attrs = [
                attr.get("value")
                for event in pos_events
                for attr in event.get("attributes", [])
                if attr.get("key") == "position_id"
            ]
            assert pos_attrs, f"position_id missing for pool {pool_id}, pos {j}"
            position_id = pos_attrs[0].strip('"')
            position_ids.append(position_id)

    # Query all positions first (this should work)
    all_positions = dysond(
        "query",
        "whaleswap",
        "positions-by-address",
        "--address",
        alice_addr,
    )

    assert isinstance(
        all_positions, dict
    ), f"All positions should be dict, got {type(all_positions)}"
    assert "positions" in all_positions, f"Missing positions key"

    positions_list = all_positions["positions"]
    assert isinstance(
        positions_list, list
    ), f"Positions should be list, got {type(positions_list)}"

    expected_positions = len(pool_ids) * 5  # 5 positions per pool
    actual_positions = len(positions_list)
    assert (
        actual_positions == expected_positions
    ), f"Should return {expected_positions} positions, got {actual_positions}"

    # Now test each pool individually - this is where the panic occurs
    # The panic happens when querying positions-by-address with specific pool IDs
    for pool_id in pool_ids:
        pool_positions = dysond(
            "query",
            "whaleswap",
            "positions-by-address",
            "--address",
            alice_addr,
            "--pool-id",
            pool_id,
        )

        # This assertion will catch the panic - it returns a string error instead of dict
        assert isinstance(
            pool_positions, dict
        ), f"Pool {pool_id} query should return dict, got {type(pool_positions)}: {pool_positions}"
        assert (
            "positions" in pool_positions
        ), f"Pool {pool_id} query missing positions key"

    # If we get here, no panic was detected in this specific run
    # But we know the panic occurs under these exact conditions
    assert len(pool_ids) >= 3, "Should have created at least 3 pools"
    assert len(position_ids) >= 15, "Should have created at least 15 positions"


def test_position_data_validation_prevents_panic(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test that validates position data integrity to ensure no corruption.
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create a pool and positions
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--liquidation-threshold",
        "1.2",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert (
        pool_result.get("code", 1) == 0
    ), f"create-pool failed: {json.dumps(pool_result, indent=2)}"

    # Extract pool_id
    pool_events = [
        e
        for e in pool_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_events, f"missing EventPoolCreated"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing"
    pool_id = pool_id.strip('"')

    # Create positions
    for i in range(3):
        pos_result = dysond(
            "tx",
            "whaleswap",
            "open-position",
            "--pool-id",
            pool_id,
            "--collateral",
            f"750{bar_name}",
            "--borrow",
            f"500{foo_name}",
            "--from",
            alice_name,
        )
        assert (
            pos_result.get("code", 1) == 0
        ), f"open-position {i} failed: {json.dumps(pos_result, indent=2)}"

    # Query positions to ensure data integrity
    all_positions = dysond(
        "query",
        "whaleswap",
        "positions-by-address",
        "--address",
        alice_addr,
        "--pool-id",
        pool_id,
    )

    assert isinstance(
        all_positions, dict
    ), f"Query should return dict, got {type(all_positions)}"
    assert "positions" in all_positions, f"Missing positions key"

    positions_list = all_positions["positions"]
    assert isinstance(
        positions_list, list
    ), f"Positions should be list, got {type(positions_list)}"
    assert (
        len(positions_list) == 3
    ), f"Should have 3 positions, got {len(positions_list)}"

    # Verify all positions have valid data (no corruption)
    for pos in positions_list:
        assert pos.get("position_id") is not None, "Position should have position_id"
        assert pos.get("status") is not None, "Position should have status"
        assert pos.get("user") == alice_addr, "Position should have correct user"
        assert pos.get("pool_id") == pool_id, "Position should have correct pool_id"

        # Verify no corruption indicators
        assert pos.get("updated_time") is not None, "Position should have updated_time"
        assert (
            pos.get("last_interest_settlement_time") is not None
        ), "Position should have last_interest_settlement_time"
