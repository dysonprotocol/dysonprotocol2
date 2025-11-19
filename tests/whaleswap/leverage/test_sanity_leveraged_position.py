"""
Sanity test for whaleswap leveraged position lifecycle:
- Create pool
- Open leveraged position
- Close position fully
- Query position to verify profit/loss tracking
"""

import json
import pytest


def test_leveraged_position_lifecycle_sanity(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Sanity test: create pool, open position, close fully, verify P&L.
    """
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Step 1: Create pool with foo and bar
    # - Reserves: 100 of each denom
    # - Interest rate: 1000% APR (10.0 per-denom DecCoin)
    # - Fee rate: 0.3% per swap (0.003 per-denom DecCoin)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{foo_name}",
        "--coins",
        f"100{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--interest-rate",
        f"10{foo_name}",
        "--interest-rate",
        f"10{bar_name}",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert (
        pool_result.get("code", 1) == 0
    ), f"create-pool failed: {json.dumps(pool_result, indent=2)}"

    pool_events = [
        e
        for e in pool_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_events, f"missing EventPoolCreated: {json.dumps(pool_result, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id", "").strip('"')
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"

    # Step 2: Open leveraged position (single baseline position)
    # Collateral: 90 foo, Borrow: 60 foo (will be swapped to bar)
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"90{foo_name}",
        "--borrow",
        f"60{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        open_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(open_result, indent=2)}"

    # Baseline open trade details
    open_trade_events = [
        e
        for e in open_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        open_trade_events
    ), f"missing EventTradeRecorded on open: {json.dumps(open_result, indent=2)}"
    open_trade_attrs = {
        a.get("key"): a.get("value") for a in open_trade_events[0].get("attributes", [])
    }
    open_trade_id = open_trade_attrs.get("trade_id", "").strip('"')
    assert (
        open_trade_id
    ), f"trade_id missing on open: {json.dumps(open_trade_events[0], indent=2)}"
    open_trade = dysond("query", "whaleswap", "trade", "--trade-id", open_trade_id)

    open_events = [
        e
        for e in open_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert (
        open_events
    ), f"missing EventLeveragePositionOpened: {json.dumps(open_result, indent=2)}"
    open_attrs = {
        a.get("key"): a.get("value") for a in open_events[0].get("attributes", [])
    }
    position_id = open_attrs.get("position_id", "").strip('"')
    assert position_id, f"position_id missing: {json.dumps(open_events[0], indent=2)}"

    # Step 3: Query position before close
    pos_before = dysond("query", "whaleswap", "position", "--position-id", position_id)
    assert (
        "position" in pos_before
    ), f"position query failed: {json.dumps(pos_before, indent=2)}"
    position_data = pos_before["position"]
    assert (
        position_data.get("status") == "POSITION_STATUS_OPEN"
    ), f"position not open: {json.dumps(position_data, indent=2)}"

    borrowed_denom = position_data["borrowed"]["denom"]
    borrowed_amount = position_data["borrowed"]["amount"]
    held_denom = position_data["held"]["denom"]
    held_amount = position_data["held"]["amount"]
    collateral_denom = position_data["collateral"]["denom"]
    collateral_amount = position_data["collateral"]["amount"]

    assert borrowed_denom == foo_name, f"borrowed denom mismatch: {borrowed_denom}"
    assert held_denom == bar_name, f"held denom mismatch: {held_denom}"
    assert (
        collateral_denom == foo_name
    ), f"collateral denom mismatch: {collateral_denom}"

    # Step 4: Close position fully (fraction = 1.0)
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--fraction",
        "1.0",
        "--from",
        alice_name,
    )
    assert (
        close_result.get("code", 1) == 0
    ), f"close-position failed: {json.dumps(close_result, indent=2)}"

    close_events = [
        e
        for e in close_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
    ]
    assert (
        close_events
    ), f"missing EventLeveragePositionClosed: {json.dumps(close_result, indent=2)}"
    close_attrs = {
        a.get("key"): a.get("value") for a in close_events[0].get("attributes", [])
    }

    # Baseline close trade details
    close_trade_events = [
        e
        for e in close_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        close_trade_events
    ), f"missing EventTradeRecorded on close: {json.dumps(close_result, indent=2)}"
    close_trade_attrs = {
        a.get("key"): a.get("value")
        for a in close_trade_events[0].get("attributes", [])
    }
    close_trade_id = close_trade_attrs.get("trade_id", "").strip('"')
    assert (
        close_trade_id
    ), f"trade_id missing on close: {json.dumps(close_trade_events[0], indent=2)}"
    close_trade = dysond("query", "whaleswap", "trade", "--trade-id", close_trade_id)

    # Extract profit from event
    profit_attr = close_attrs.get("profit", "{}")
    profit_data = json.loads(profit_attr)
    profit_amount = profit_data.get("amount", "0")
    profit_denom = profit_data.get("denom", "")

    accrued_interest_attr = close_attrs.get("accrued_interest", "{}")
    accrued_interest_data = json.loads(accrued_interest_attr)
    accrued_interest_amount = accrued_interest_data.get("amount", "0")

    # Step 5: Query position after close to verify status and P&L
    pos_after = dysond("query", "whaleswap", "position", "--position-id", position_id)
    assert (
        "position" in pos_after
    ), f"position query after close failed: {json.dumps(pos_after, indent=2)}"
    closed_position = pos_after["position"]

    assert (
        closed_position.get("status") == "POSITION_STATUS_CLOSED"
    ), f"position not closed: {json.dumps(closed_position, indent=2)}"

    # Verify P&L fields exist
    total_realized_profit = closed_position.get("total_realized_profit", {})
    total_realized_loss = closed_position.get("total_realized_loss", {})
    total_interest_paid = closed_position.get("total_interest_paid", {})

    # Verify borrowed/held/collateral are zeroed out after full close
    assert (
        closed_position["borrowed"]["amount"] == "0"
    ), f"borrowed not zeroed: {closed_position['borrowed']}"
    assert (
        closed_position["held"]["amount"] == "0"
    ), f"held not zeroed: {closed_position['held']}"
    assert (
        closed_position["collateral"]["amount"] == "0"
    ), f"collateral not zeroed: {closed_position['collateral']}"

    # Verify profit or loss is tracked
    profit_amt = int(total_realized_profit.get("amount", "0"))
    loss_amt = int(total_realized_loss.get("amount", "0"))
    interest_amt = int(total_interest_paid.get("amount", "0"))

    # At least one of profit or loss should be tracked (or both zero if break-even)
    # Interest should be >= 0 (may be 0 if no time passed or 0% rate)
    assert interest_amt >= 0, f"interest_paid negative: {interest_amt}"

    # Sanity: profit and loss should not both be positive (mutually exclusive)
    both_positive = profit_amt > 0 and loss_amt > 0
    assert (
        not both_positive
    ), f"both profit and loss positive: profit={profit_amt}, loss={loss_amt}"

    # For an immediate open+close with no external price movement, we expect
    # realized profit to be zero in the borrowed denom (fees/slippage register
    # as loss), and any interest to be non-negative.
    assert (
        profit_amt == 0
    ), f"unexpected positive profit on baseline close: {profit_amt}"

    # Log baseline position results for inspection
    print(f"Baseline position {position_id} closed successfully")
    print(f"  Borrowed: {borrowed_amount} {borrowed_denom}")
    print(f"  Held: {held_amount} {held_denom}")
    print(f"  Collateral: {collateral_amount} {collateral_denom}")
    print(f"  Profit: {profit_amt} {profit_denom}")
    print(f"  Loss: {loss_amt}")
    print(f"  Interest Paid: {interest_amt}")
    print(f"  Total Realized Profit: {total_realized_profit}")
    print(f"  Total Realized Loss: {total_realized_loss}")
    print(f"  Total Interest Paid: {total_interest_paid}")
    print(f"  Open Trade {open_trade_id}: {json.dumps(open_trade, indent=2)}")
    print(f"  Close Trade {close_trade_id}: {json.dumps(close_trade, indent=2)}")

    # Step 6: Loop opening large positions in both directions (foo->bar, bar->foo)
    # and closing them fully to sanity check profit accounting over multiple
    # round-trips through the AMM with leverage.
    directions = [
        {
            "name": "long_bar_vs_foo",
            "collateral_denom": foo_name,
            "borrow_denom": foo_name,
        },
        {
            "name": "long_foo_vs_bar",
            "collateral_denom": bar_name,
            "borrow_denom": bar_name,
        },
    ]

    large_collateral = 90
    large_borrow = 60
    rounds = 2

    cumulative_profit = 0
    cumulative_loss = 0

    for r in range(rounds):
        for idx in range(len(directions)):
            cfg = directions[idx]
            collateral_str = f"{large_collateral}{cfg['collateral_denom']}"
            borrow_str = f"{large_borrow}{cfg['borrow_denom']}"

            loop_open = dysond(
                "tx",
                "whaleswap",
                "open-position",
                "--pool-id",
                pool_id,
                "--collateral",
                collateral_str,
                "--borrow",
                borrow_str,
                "--from",
                alice_name,
            )
            assert (
                loop_open.get("code", 1) == 0
            ), f"loop open-position failed: {json.dumps(loop_open, indent=2)}"

            loop_open_events = [
                e
                for e in loop_open.get("events", [])
                if e.get("type")
                == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
            ]
            assert (
                loop_open_events
            ), f"missing loop EventLeveragePositionOpened: {json.dumps(loop_open, indent=2)}"
            loop_open_attrs = {
                a.get("key"): a.get("value")
                for a in loop_open_events[0].get("attributes", [])
            }
            loop_position_id = loop_open_attrs.get("position_id", "").strip('"')
            assert (
                loop_position_id
            ), f"loop position_id missing: {json.dumps(loop_open_events[0], indent=2)}"

            loop_close = dysond(
                "tx",
                "whaleswap",
                "close-position",
                "--position-id",
                loop_position_id,
                "--fraction",
                "1.0",
                "--from",
                alice_name,
            )
            assert (
                loop_close.get("code", 1) == 0
            ), f"loop close-position failed: {json.dumps(loop_close, indent=2)}"

            loop_close_events = [
                e
                for e in loop_close.get("events", [])
                if e.get("type")
                == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
            ]
            assert (
                loop_close_events
            ), f"missing loop EventLeveragePositionClosed: {json.dumps(loop_close, indent=2)}"
            loop_close_attrs = {
                a.get("key"): a.get("value")
                for a in loop_close_events[0].get("attributes", [])
            }

            loop_pos_after = dysond(
                "query", "whaleswap", "position", "--position-id", loop_position_id
            )
            assert (
                "position" in loop_pos_after
            ), f"loop position query after close failed: {json.dumps(loop_pos_after, indent=2)}"
            loop_closed_position = loop_pos_after["position"]

            assert (
                loop_closed_position.get("status") == "POSITION_STATUS_CLOSED"
            ), f"loop position not closed: {json.dumps(loop_closed_position, indent=2)}"

            # Loop P&L fields
            loop_profit_attr = loop_close_attrs.get("profit", "{}")
            loop_profit_data = json.loads(loop_profit_attr)
            loop_profit_amt = int(loop_profit_data.get("amount", "0"))

            loop_total_profit = loop_closed_position.get("total_realized_profit", {})
            loop_total_loss = loop_closed_position.get("total_realized_loss", {})

            loop_total_profit_amt = int(loop_total_profit.get("amount", "0"))
            loop_total_loss_amt = int(loop_total_loss.get("amount", "0"))

            # Each immediate round-trip (open then full close) should never
            # realize a positive profit in borrowed denom; any slippage/fees
            # should register as loss.
            assert (
                loop_profit_amt == 0
            ), f"unexpected positive profit on loop close: {loop_profit_amt}"

            cumulative_profit += loop_total_profit_amt
            cumulative_loss += loop_total_loss_amt

    # Across all looped positions in both directions, cumulative realized profit
    # should not be positive (no free lunch from symmetric open/close),
    # while cumulative loss should be non-negative.
    assert (
        cumulative_profit == 0
    ), f"cumulative realized profit should not be positive: {cumulative_profit}"
    assert cumulative_loss >= 0, f"cumulative loss negative: {cumulative_loss}"

    print(f"Cumulative profit over loops: {cumulative_profit}")
    print(f"Cumulative loss over loops: {cumulative_loss}")
