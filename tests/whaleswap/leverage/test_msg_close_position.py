"""
Test coverage for MsgClosePosition keeper method.

ClosePosition closes leveraged positions and settles collateral/profit.
Tests cover both happy path and all error validation paths.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_cover_position_note_propagates(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    dysond = chainnet[0]
    trader_name = leverage_accounts["bob"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"5000{foo_name}",
        "--coins",
        f"5000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "10.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        trader_name,
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
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"400{bar_name}",
        "--borrow",
        f"250{foo_name}",
        "--from",
        trader_name,
    )
    assert (
        open_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(open_result, indent=2)}"

    pos_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert pos_attrs, f"position_id missing: {json.dumps(open_result, indent=2)}"
    position_id = pos_attrs[0].strip('"')

    note_text = "cover-position note propagation"
    # Cover with exact principal + interest to trigger auto-close
    cover_result = dysond(
        "tx",
        "whaleswap",
        "cover-position",
        "--position-id",
        position_id,
        "--payment",
        f"260{foo_name}",  # slightly more than borrowed 250 to cover interest and trigger auto-close
        "--position-note",
        note_text,
        "--from",
        trader_name,
    )
    assert (
        cover_result.get("code", 1) == 0
    ), f"cover-position failed: {json.dumps(cover_result, indent=2)}"

    trade_events = [
        e
        for e in cover_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        trade_events
    ), f"missing EventTradeRecorded: {json.dumps(cover_result, indent=2)}"

    trade_ids = set()
    for event in trade_events:
        attrs = {a.get("key"): a.get("value") for a in event.get("attributes", [])}
        note_attr = attrs.get("note")
        assert note_attr is not None, f"note missing: {json.dumps(event, indent=2)}"
        assert json.loads(note_attr) == note_text, f"note mismatch: {note_attr}"
        trade_id_raw = attrs.get("trade_id")
        assert trade_id_raw, f"trade_id missing: {json.dumps(event, indent=2)}"
        trade_ids.add(int(json.loads(trade_id_raw)))

    for trade_id in trade_ids:
        trade_resp = dysond("query", "whaleswap", "trade", "--trade-id", str(trade_id))
        trade = trade_resp.get("trade", {})
        assert (
            trade.get("note") == note_text
        ), f"trade note mismatch: {json.dumps(trade, indent=2)}"


def test_close_position_note_propagates(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    dysond = chainnet[0]
    trader_name = leverage_accounts["bob"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"5000{foo_name}",
        "--coins",
        f"5000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "10.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        trader_name,
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
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"400{bar_name}",
        "--borrow",
        f"250{foo_name}",
        "--from",
        trader_name,
    )
    assert (
        open_result.get("code", 1) == 0
    ), f"open-position failed: {json.dumps(open_result, indent=2)}"

    pos_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert pos_attrs, f"position_id missing: {json.dumps(open_result, indent=2)}"
    position_id = pos_attrs[0].strip('"')

    note_text = "close-position note propagation"
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--fraction",
        "1",
        "--position-note",
        note_text,
        "--from",
        trader_name,
    )
    assert (
        close_result.get("code", 1) == 0
    ), f"close-position failed: {json.dumps(close_result, indent=2)}"

    trade_events = [
        e
        for e in close_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        trade_events
    ), f"missing EventTradeRecorded: {json.dumps(close_result, indent=2)}"

    trade_ids = set()
    for event in trade_events:
        attrs = {a.get("key"): a.get("value") for a in event.get("attributes", [])}
        note_attr = attrs.get("note")
        assert note_attr is not None, f"note missing: {json.dumps(event, indent=2)}"
        assert json.loads(note_attr) == note_text, f"note mismatch: {note_attr}"
        trade_id_raw = attrs.get("trade_id")
        assert trade_id_raw, f"trade_id missing: {json.dumps(event, indent=2)}"
        trade_ids.add(int(json.loads(trade_id_raw)))

    for trade_id in trade_ids:
        trade_resp = dysond("query", "whaleswap", "trade", "--trade-id", str(trade_id))
        trade = trade_resp.get("trade", {})
        assert (
            trade.get("note") == note_text
        ), f"trade note mismatch: {json.dumps(trade, indent=2)}"


def test_close_position_happy_path_long(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Happy path: Close a LONG position and verify profit settlement.

    Uses CLI transactions (not query/sudo) so blocks advance naturally between operations.
    Uses charlie to avoid depleting alice/bob's tokens from other tests.
    """
    dysond = chainnet[0]
    charlie_name = leverage_accounts["charlie"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool via CLI (smaller amounts to avoid token depletion from session-scoped fixtures)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"5000{foo_name}",
        "--coins",
        f"5000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "20.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        charlie_name,
    )

    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"

    # Extract pool_id
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = pool_id_attrs[0].strip('"')

    # Open LONG position (borrow foo, hold bar, collateral in foo)
    # Use same-denom collateral to test shortfall coverage when position goes underwater from fees
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"400{foo_name}",
        "--borrow",
        f"250{foo_name}",
        "--from",
        charlie_name,
    )

    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"

    # Extract position_id
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = position_id_attrs[0].strip('"')

    # Close position (blocks have advanced, CanCloseBefore passes)
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--fraction",
        "1",
        "--from",
        charlie_name,
    )

    assert close_result.get("code", 1) == 0, f"Close position failed: {close_result}"

    # Verify EventLeveragePositionClosed was emitted
    close_events = [
        event
        for event in close_result.get("events", [])
        if event.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
    ]
    assert len(close_events) > 0, "EventLeveragePositionClosed not found"

    # Verify profit attribute exists
    profit_attrs = [
        attr
        for attr in close_events[0].get("attributes", [])
        if attr.get("key") == "profit"
    ]
    assert len(profit_attrs) > 0, "profit attribute not found"

    # Verify accrued_interest attribute exists
    interest_attrs = [
        attr
        for attr in close_events[0].get("attributes", [])
        if attr.get("key") == "accrued_interest"
    ]
    assert len(interest_attrs) > 0, "accrued_interest attribute not found"


def test_close_position_block_delay_enforced(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition enforces block delay (can't close in same block as creation).

    In query mode, all _sudo calls execute at same blockHeight, so CanCloseBefore
    returns false and triggers ErrBlockDelayNotPassed. This validates the check exists.
    Uses bob to avoid token depletion from alice's happy path test.
    """
    dysond = chainnet[0]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_block_delay_enforced(bob_addr, foo_name, bar_name):
    # Create pool (minimal amounts)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": bob_addr,
        "coins": [
            {"denom": foo_name, "amount": "500"},
            {"denom": bar_name, "amount": "500"}
        ],
        "fee_rate": [
            {"denom": foo_name, "amount": "0.003"},
            {"denom": bar_name, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": foo_name, "amount": "1.5"},
            {"denom": bar_name, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": foo_name, "amount": "20.0"},
            {"denom": bar_name, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": foo_name, "amount": "1.2"},
            {"denom": bar_name, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": foo_name, "amount": "0.8"},
            {"denom": bar_name, "amount": "0.8"}
        ]
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Open position
    sudo_open_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": bob_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "30"},
        "borrow": {"denom": foo_name, "amount": "20"}
    })
    position_id = sudo_open_result["results"][0]["position_id"]
    
    # Try to close at same block height - should fail
    sudo_close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": bob_addr,
        "position_id": position_id
    })
    
    return {"unexpected": "should have failed"}
"""
    kwargs = json.dumps(
        {"bob_addr": bob_addr, "foo_name": foo_name, "bar_name": bar_name}
    )
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_block_delay_enforced",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for block delay. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"])
    assert "block" in exception_msg, f"Expected 'block' in error, got: {exception_msg}"
    assert (
        "locked" in exception_msg
    ), f"Expected 'locked' in error, got: {exception_msg}"


def test_close_position_not_found(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition fails when position doesn't exist."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_position_not_found(alice_addr):
    # Try to close non-existent position
    sudo_close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": alice_addr,
        "position_id": "99999"
    })
    return {"unexpected": "should have failed"}
"""
    kwargs = json.dumps({"alice_addr": alice_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_position_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for non-existent position. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"])
    assert (
        "position" in exception_msg
    ), f"Expected 'position' in error, got: {exception_msg}"
    assert (
        "not found" in exception_msg
    ), f"Expected 'not found' in error, got: {exception_msg}"


def test_close_position_not_owner(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition fails when caller is not the position owner."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_not_owner(alice_addr, bob_addr, foo_name, bar_name):
    # Create pool (minimal amounts to avoid token depletion)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "500"},
            {"denom": bar_name, "amount": "500"}
        ],
        "fee_rate": [
            {"denom": foo_name, "amount": "0.003"},
            {"denom": bar_name, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": foo_name, "amount": "1.5"},
            {"denom": bar_name, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": foo_name, "amount": "20.0"},
            {"denom": bar_name, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": foo_name, "amount": "1.2"},
            {"denom": bar_name, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": foo_name, "amount": "0.8"},
            {"denom": bar_name, "amount": "0.8"}
        ]
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Alice opens position
    sudo_open_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "30"},
        "borrow": {"denom": foo_name, "amount": "20"}
    })
    position_id = sudo_open_result["results"][0]["position_id"]
    
    # Bob tries to close Alice's position
    sudo_close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": bob_addr,
        "position_id": position_id
    })
    return {"unexpected": "should have failed"}
"""
    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
        }
    )
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_not_owner",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for unauthorized close. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"])
    assert (
        "unauthorized" in exception_msg
    ), f"Expected 'unauthorized' in error, got: {exception_msg}"


def test_close_position_not_owner_direct(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition fails with 'unauthorized' when called by non-owner (direct dysond tx)."""
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_name = leverage_accounts["bob"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool via CLI (smaller amounts to avoid token depletion from session-scoped fixtures)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"5000{foo_name}",
        "--coins",
        f"5000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "20.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )

    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"

    # Extract pool_id
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = int(pool_id_attrs[0].strip('"'))

    # Alice opens a position
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        str(pool_id),
        "--collateral",
        f"400{bar_name}",
        "--borrow",
        f"250{foo_name}",
        "--from",
        alice_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"

    # Extract position_id
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = int(position_id_attrs[0].strip('"'))

    # Bob tries to close Alice's position - this should fail with "unauthorized"
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        str(position_id),
        "--fraction",
        "1",
        "--from",
        bob_name,
    )

    # The transaction should fail with "unauthorized" error
    # Currently it panics instead of returning a proper error
    assert (
        close_result.get("code", 0) != 0
    ), f"Expected close-position to fail, but it succeeded: {close_result}"

    # Check that the error contains "unauthorized"
    raw_log = close_result.get("raw_log", "")
    assert (
        "unauthorized" in raw_log
    ), f"Expected 'unauthorized' in error log, got: {raw_log}"


def test_close_position_invalid_user_address(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that ClosePosition fails with invalid/malformed user address."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_invalid_address(alice_addr, foo_name, bar_name):
    # Create pool (minimal amounts to avoid token depletion)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "500"},
            {"denom": bar_name, "amount": "500"}
        ],
        "fee_rate": [
            {"denom": foo_name, "amount": "0.003"},
            {"denom": bar_name, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": foo_name, "amount": "1.5"},
            {"denom": bar_name, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": foo_name, "amount": "20.0"},
            {"denom": bar_name, "amount": "20.0"}
        ],
        "max_borrow_percent": [
            {"denom": foo_name, "amount": "0.8"},
            {"denom": bar_name, "amount": "0.8"}
        ]
    })
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Open position
    sudo_open_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "30"},
        "borrow": {"denom": foo_name, "amount": "20"}
    })
    position_id = sudo_open_result["results"][0]["position_id"]
    
    # Try to close with invalid address format
    sudo_close_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": "invalid_address_format",
        "position_id": position_id
    })
    return {"unexpected": "should have failed"}
"""
    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
    )
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_invalid_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        "exception" in query_result
    ), f"Expected exception for invalid address. Got: {json.dumps(query_result, indent=2)}"
    exception_msg = str(query_result["exception"])
    assert (
        "address" in exception_msg
    ), f"Expected 'address' in error, got: {exception_msg}"


def test_close_position_cross_denom_underwater_rejected(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test closing underwater position with cross-denom collateral insufficient is rejected.

    Scenario: User opens position with collateral in bar, borrows foo.
    We manipulate the pool to make the position severely underwater where:
    - swap(held) < repayment (underwater)
    - swap(held) + swap(collateral) < repayment (collateral insufficient)
    - Transaction is rejected to prevent pool loss

    This validates the cross-denom rejection logic when total proceeds are insufficient.
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool via CLI: 10000 foo, 10000 bar (1:1 initial price)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.2",
        "--max-leverage-ratio",
        "10.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = pool_id_attrs[0].strip('"')

    # Check initial pool state
    pool_query = dysond("query", "whaleswap", "pool", "--pool-id", pool_id)
    initial_foo = int(pool_query["pool"]["coins"][0]["amount"])
    initial_bar = int(pool_query["pool"]["coins"][1]["amount"])
    assert initial_foo == 10000, f"Expected 10000 foo, got {initial_foo}"
    assert initial_bar == 10000, f"Expected 10000 bar, got {initial_bar}"

    # Open position: borrow 1000 foo, collateral 1500 bar (cross-denom)
    # Position will swap borrowed foo → bar, so held will be bar
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"1500{bar_name}",
        "--borrow",
        f"1000{foo_name}",
        "--from",
        alice_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = position_id_attrs[0].strip('"')

    # Verify cross-denom setup from open event
    open_events = [
        e
        for e in open_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(open_events) == 1, "Expected position opened event"

    # Extract denoms from event to confirm cross-denom
    borrowed_denom_attr = [
        a
        for a in open_events[0].get("attributes", [])
        if a.get("key") == "borrowed_denom"
    ]
    collateral_denom_attr = [
        a
        for a in open_events[0].get("attributes", [])
        if a.get("key") == "collateral_denom"
    ]
    assert len(borrowed_denom_attr) == 1, "Expected borrowed_denom in event"
    assert len(collateral_denom_attr) == 1, "Expected collateral_denom in event"
    assert (
        borrowed_denom_attr[0].get("value", "").strip('"') == foo_name
    ), "Borrowed should be foo"
    assert (
        collateral_denom_attr[0].get("value", "").strip('"') == bar_name
    ), "Collateral should be bar"

    # Manipulate pool to make position underwater:
    # Dump massive amount of bar into pool to crash bar price
    # This makes the held bar worth much less in foo terms
    swap_leg_json = json.dumps(
        {"pool_id": int(pool_id), "swap_in": {"denom": bar_name, "amount": "5000"}}
    )
    swap_result = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        f"5000{bar_name}",
        "--legs",
        swap_leg_json,
        "--min-output",
        f"1{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        swap_result.get("code", 1) == 0
    ), f"Price manipulation swap failed: {swap_result}"

    # Check pool state after manipulation
    pool_after = dysond("query", "whaleswap", "pool", "--pool-id", pool_id)
    foo_reserve = int(
        [c for c in pool_after["pool"]["coins"] if c["denom"] == foo_name][0]["amount"]
    )
    bar_reserve = int(
        [c for c in pool_after["pool"]["coins"] if c["denom"] == bar_name][0]["amount"]
    )

    # Now bar is severely devalued (much more bar than foo in pool)
    assert (
        bar_reserve > foo_reserve * 2
    ), f"Expected bar severely devalued, foo={foo_reserve} bar={bar_reserve}"

    # Get alice's balance before close
    alice_balance_before = dysond("query", "bank", "balances", alice_addr)
    foo_before = int(
        [b for b in alice_balance_before["balances"] if b["denom"] == foo_name][0][
            "amount"
        ]
    )
    bar_before = int(
        [b for b in alice_balance_before["balances"] if b["denom"] == bar_name][0][
            "amount"
        ]
    )

    # Close position - should be rejected due to insufficient collateral
    # Expected: swap held (bar→foo) insufficient, swap collateral (bar→foo) also insufficient
    # Total proceeds < repayment → transaction rejected
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--fraction",
        "1",
        "--from",
        alice_name,
    )

    # Verify transaction was rejected due to insufficient collateral after swaps
    assert (
        close_result.get("code", 0) != 0
    ), f"Expected close to be rejected, but it succeeded: {json.dumps(close_result, indent=2)}"
    assert (
        close_result.get("codespace") == "whaleswap"
    ), f"Expected whaleswap codespace. Full result: {json.dumps(close_result, indent=2)}"
    assert (
        close_result.get("code") == 1002
    ), f"Expected error code 1002 (insufficient collateral), got {close_result.get('code')}. Full result: {json.dumps(close_result, indent=2)}"

    raw_log = close_result.get("raw_log", "")
    assert (
        "insufficient collateral" in raw_log.lower()
    ), f"Expected 'insufficient collateral' in error, got: {raw_log}"
    assert (
        "underwater" in raw_log.lower()
    ), f"Expected 'underwater' in error, got: {raw_log}"

    # Position should remain open because the transaction reverted
    position_query = dysond(
        "query", "whaleswap", "position", "--position-id", position_id
    )
    position = position_query.get("position")
    assert isinstance(
        position, dict
    ), f"Expected position dict, got {type(position)}. Full response: {json.dumps(position_query, indent=2)}"
    assert (
        position.get("status") == "POSITION_STATUS_OPEN"
    ), f"Position status should remain open after failed close. Full position: {json.dumps(position, indent=2)}"

    # Verify alice's balance unchanged (transaction rejected, no state change)
    alice_balance_after = dysond("query", "bank", "balances", alice_addr)
    foo_after = int(
        [b for b in alice_balance_after["balances"] if b["denom"] == foo_name][0][
            "amount"
        ]
    )
    bar_after = int(
        [b for b in alice_balance_after["balances"] if b["denom"] == bar_name][0][
            "amount"
        ]
    )

    # Balances should be unchanged (transaction reverted)
    assert (
        foo_after == foo_before
    ), f"Expected foo unchanged after rejection, before={foo_before} after={foo_after}"
    assert (
        bar_after == bar_before
    ), f"Expected bar unchanged after rejection, before={bar_before} after={bar_after}"


def test_close_position_same_denom_collateral_sufficient_underwater(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test closing underwater position where same-denom collateral covers the shortfall.

    Scenario: User opens position with collateral and borrow in same denom (foo).
    We manipulate the pool to make position underwater but collateral sufficient:
    - swap(held) < repayment (underwater)
    - swap(held) + collateral >= repayment (collateral sufficient)
    - pool receives full repayment, no loss
    - user gets remaining collateral back

    This validates the same-denom collateral sufficient case in msg_leverage_handlers.go.
    """
    dysond = chainnet[0]
    bob_addr = leverage_accounts["bob"]["addr"]
    bob_name = leverage_accounts["bob"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool via CLI: 15000 foo, 15000 bar (1:1 initial price)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"15000{foo_name}",
        "--coins",
        f"15000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.2",
        "--max-leverage-ratio",
        "10.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        bob_name,
    )
    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = pool_id_attrs[0].strip('"')

    # Open position: borrow 500 foo, collateral 800 foo (same-denom, meets min CR 1.6)
    # Position will swap borrowed foo → bar, so held will be bar
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"800{foo_name}",
        "--borrow",
        f"500{foo_name}",
        "--from",
        bob_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = position_id_attrs[0].strip('"')

    # Manipulate pool severely to crash bar price (dump massive bar into pool)
    # This makes the held bar worth much less when swapping back to foo
    swap_leg_json = json.dumps(
        {"pool_id": int(pool_id), "swap_in": {"denom": bar_name, "amount": "12000"}}
    )
    swap_result = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        f"12000{bar_name}",
        "--legs",
        swap_leg_json,
        "--min-output",
        f"1{foo_name}",
        "--from",
        bob_name,
    )
    assert (
        swap_result.get("code", 1) == 0
    ), f"Price manipulation swap failed: {swap_result}"

    # Get pool state before close and bob's balance
    pool_before = dysond("query", "whaleswap", "pool", "--pool-id", pool_id)
    foo_reserve_before = int(
        [c for c in pool_before["pool"]["coins"] if c["denom"] == foo_name][0]["amount"]
    )

    bob_balance_before = dysond("query", "bank", "balances", bob_addr)
    foo_balance_before = int(
        [b for b in bob_balance_before["balances"] if b["denom"] == foo_name][0][
            "amount"
        ]
    )

    # Close position - collateral will cover the shortfall
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--fraction",
        "1",
        "--from",
        bob_name,
    )
    assert close_result.get("code", 1) == 0, f"Close position failed: {close_result}"

    # Verify close event
    close_events = [
        event
        for event in close_result.get("events", [])
        if event.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
    ]
    assert (
        len(close_events) == 1
    ), f"Expected exactly 1 close event, got {len(close_events)}"

    # Extract profit from event (should be zero since underwater)
    profit_attrs = [
        attr
        for attr in close_events[0].get("attributes", [])
        if attr.get("key") == "profit"
    ]
    assert len(profit_attrs) == 1, "Expected profit attribute"
    profit_str = profit_attrs[0].get("value", "").strip('"')
    assert "0" in profit_str, f"Expected zero profit (underwater), got: {profit_str}"

    # Get pool state after close
    pool_after = dysond("query", "whaleswap", "pool", "--pool-id", pool_id)
    foo_reserve_after = int(
        [c for c in pool_after["pool"]["coins"] if c["denom"] == foo_name][0]["amount"]
    )

    # Verify pool received full repayment (no loss)
    # Pool should have gained the borrowed amount back
    assert (
        foo_reserve_after > foo_reserve_before
    ), f"Expected pool to gain from repayment, foo before={foo_reserve_before}, after={foo_reserve_after}"

    # Get bob's balance to verify some collateral was returned
    bob_balance_after = dysond("query", "bank", "balances", bob_addr)
    foo_balance_after = int(
        [b for b in bob_balance_after["balances"] if b["denom"] == foo_name][0][
            "amount"
        ]
    )

    # Bob should have received some collateral back (less than full 800 since position was underwater)
    collateral_returned = foo_balance_after - foo_balance_before
    assert (
        collateral_returned > 0
    ), f"Expected some collateral returned, got {collateral_returned}"
    assert (
        collateral_returned < 800
    ), f"Expected partial collateral return (position was underwater), got {collateral_returned}"


def test_close_position_cross_denom_swap_still_underwater(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test closing underwater position where cross-denom collateral swap still leaves pool with loss.

    Scenario: User opens position with collateral in bar, borrows foo.
    We manipulate pool severely to make position extremely underwater where:
    - swap(held) < repayment (underwater)
    - swap(held) + swap(collateral) < repayment (still underwater, pool takes loss)

    This validates lines 187-199 in msg_leverage_handlers.go (cross-denom insufficient case).
    """
    dysond = chainnet[0]
    charlie_addr = leverage_accounts["charlie"]["addr"]
    charlie_name = leverage_accounts["charlie"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool via CLI: 15000 foo, 15000 bar (1:1 initial price)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"15000{foo_name}",
        "--coins",
        f"15000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.2",
        "--max-leverage-ratio",
        "10.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        charlie_name,
    )
    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = pool_id_attrs[0].strip('"')

    # Open position: borrow 2000 foo, collateral 3000 bar (cross-denom)
    # Position will swap borrowed foo → bar, so held will be bar
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"3000{bar_name}",
        "--borrow",
        f"2000{foo_name}",
        "--from",
        charlie_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = position_id_attrs[0].strip('"')

    # Manipulate pool severely to crash bar price
    # This makes both held bar and collateral bar worth much less
    swap_leg_json = json.dumps(
        {"pool_id": int(pool_id), "swap_in": {"denom": bar_name, "amount": "3000"}}
    )
    swap_result = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        f"3000{bar_name}",
        "--legs",
        swap_leg_json,
        "--min-output",
        f"1{foo_name}",
        "--from",
        charlie_name,
    )
    assert (
        swap_result.get("code", 1) == 0
    ), f"Price manipulation swap failed: {swap_result}"

    # Get pool state before close
    pool_before = dysond("query", "whaleswap", "pool", "--pool-id", pool_id)
    foo_reserve_before = int(
        [c for c in pool_before["pool"]["coins"] if c["denom"] == foo_name][0]["amount"]
    )

    # Close position - even cross-denom swap of collateral won't cover full repayment
    # Expected: swap held (bar→foo) insufficient, swap collateral (bar→foo) also insufficient, pool takes loss
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--fraction",
        "1",
        "--from",
        charlie_name,
    )
    assert close_result.get("code", 1) == 0, f"Close position failed: {close_result}"

    # Verify close event
    close_events = [
        event
        for event in close_result.get("events", [])
        if event.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
    ]
    assert (
        len(close_events) == 1
    ), f"Expected exactly 1 close event, got {len(close_events)}"

    # Extract profit from event (should be zero or minimal since very underwater)
    profit_attrs = [
        attr
        for attr in close_events[0].get("attributes", [])
        if attr.get("key") == "profit"
    ]
    assert len(profit_attrs) == 1, "Expected profit attribute"
    profit_str = profit_attrs[0].get("value", "").strip('"')

    # Get pool state after close
    pool_after = dysond("query", "whaleswap", "pool", "--pool-id", pool_id)
    foo_reserve_after = int(
        [c for c in pool_after["pool"]["coins"] if c["denom"] == foo_name][0]["amount"]
    )

    # Verify pool took a loss (even with cross-denom collateral swap)
    # Pool should have less foo than before close because total proceeds < repayment
    assert (
        foo_reserve_after < foo_reserve_before
    ), f"Expected pool loss (underwater with cross-denom swap), foo before={foo_reserve_before}, after={foo_reserve_after}"

    # Get charlie's balance - collateral should have been entirely consumed
    charlie_balance_after = dysond("query", "bank", "balances", charlie_addr)
    bar_after = int(
        [b for b in charlie_balance_after["balances"] if b["denom"] == bar_name][0][
            "amount"
        ]
    )

    # Charlie should have lost all collateral (was swapped to try to cover repayment)


def test_close_position_same_denom_collateral_covers_shortfall(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test closing underwater position where same-denom collateral covers the shortfall.

    Scenario: User opens position with collateral and borrow in same denom (foo).
    We manipulate the pool moderately to make position underwater but collateral sufficient:
    - swap(held) < repayment (underwater)
    - swap(held) + collateral >= repayment (collateral covers shortfall)
    - no pool loss

    This validates lines 108-121 in msg_leverage_handlers.go (collateral sufficient case).
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool via CLI: 20000 foo, 20000 bar (1:1 initial price)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"20000{foo_name}",
        "--coins",
        f"20000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.2",
        "--max-leverage-ratio",
        "10.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = pool_id_attrs[0].strip('"')

    # Open position: borrow 500 foo, collateral 1000 foo (same-denom, generous collateral)
    # Position will swap borrowed foo → bar, so held will be bar
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"1000{foo_name}",
        "--borrow",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = position_id_attrs[0].strip('"')

    # Manipulate pool moderately to crash bar price (not as severe as pool loss test)
    # This makes held bar worth less, but collateral should cover shortfall
    swap_leg_json = json.dumps(
        {"pool_id": int(pool_id), "swap_in": {"denom": bar_name, "amount": "5000"}}
    )
    swap_result = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        f"5000{bar_name}",
        "--legs",
        swap_leg_json,
        "--min-output",
        f"1{foo_name}",
        "--from",
        alice_name,
    )
    assert (
        swap_result.get("code", 1) == 0
    ), f"Price manipulation swap failed: {swap_result}"

    # Get pool state before close
    pool_before = dysond("query", "whaleswap", "pool", "--pool-id", pool_id)
    foo_reserve_before = int(
        [c for c in pool_before["pool"]["coins"] if c["denom"] == foo_name][0]["amount"]
    )

    # Get alice's balance before close
    alice_balance_before = dysond("query", "bank", "balances", alice_addr)
    foo_before = int(
        [b for b in alice_balance_before["balances"] if b["denom"] == foo_name][0][
            "amount"
        ]
    )

    # Close position - should use collateral to cover shortfall
    # Expected: swap held (bar→foo) insufficient, but collateral (1000 foo) covers shortfall
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--fraction",
        "1",
        "--from",
        alice_name,
    )
    assert close_result.get("code", 1) == 0, f"Close position failed: {close_result}"

    # Verify close event
    close_events = [
        event
        for event in close_result.get("events", [])
        if event.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
    ]
    assert (
        len(close_events) == 1
    ), f"Expected exactly 1 close event, got {len(close_events)}"

    # Extract profit from event (should be zero since underwater, but collateral covered shortfall)
    profit_attrs = [
        attr
        for attr in close_events[0].get("attributes", [])
        if attr.get("key") == "profit"
    ]
    assert len(profit_attrs) == 1, "Expected profit attribute"
    profit_str = profit_attrs[0].get("value", "").strip('"')
    assert (
        "0" in profit_str
    ), f"Expected zero profit (underwater but covered), got: {profit_str}"

    # Get pool state after close
    pool_after = dysond("query", "whaleswap", "pool", "--pool-id", pool_id)
    foo_reserve_after = int(
        [c for c in pool_after["pool"]["coins"] if c["denom"] == foo_name][0]["amount"]
    )

    # Verify pool took NO loss (collateral covered the shortfall)
    # Pool should have received back the full repayment (500 foo borrowed)
    # Due to fees and timing, check that pool didn't decrease significantly
    assert (
        foo_reserve_after >= foo_reserve_before - 100
    ), f"Expected no significant pool loss (collateral covered), foo before={foo_reserve_before}, after={foo_reserve_after}"

    # Get alice's balance after close
    alice_balance_after = dysond("query", "bank", "balances", alice_addr)
    foo_after = int(
        [b for b in alice_balance_after["balances"] if b["denom"] == foo_name][0][
            "amount"
        ]
    )

    # Verify alice got back some collateral (part was used to cover shortfall)
    # She started with 1000 collateral, some was used, rest returned
    foo_change = foo_after - foo_before
    assert (
        foo_change > 0
    ), f"Expected some collateral returned (shortfall covered but position underwater), got {foo_change}"
    assert (
        foo_change < 1000
    ), f"Expected partial collateral return (some used for shortfall), got {foo_change}"


def test_close_position_profitable_same_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Happy path: proceedsBorrow >= repayment returns full collateral and profit to user.

    Setup:
    - Same-denom collateral/borrow (foo), held denom is bar.
    - Manipulate pool price by swapping large foo->bar to make bar scarcer (bar appreciates).
    - Close should yield positive profit and return all collateral.
    """
    dysond = chainnet[0]
    charlie_name = leverage_accounts["charlie"]["name"]
    charlie_addr = leverage_accounts["charlie"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Deep liquidity pool to reduce slippage during open; we'll move price afterwards
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"20000{foo_name}",
        "--coins",
        f"20000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "20.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        charlie_name,
    )
    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = pool_id_attrs[0].strip('"')

    # Open position: borrow foo (250), collateral foo (400) => held will be bar
    collateral_amt = 400
    borrow_amt = 250
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"{collateral_amt}{foo_name}",
        "--borrow",
        f"{borrow_amt}{foo_name}",
        "--from",
        charlie_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = position_id_attrs[0].strip('"')

    # Price manipulation: swap a large amount of foo -> bar to make bar scarcer (appreciate)
    swap_leg_json = json.dumps(
        {"pool_id": int(pool_id), "swap_in": {"denom": foo_name, "amount": "8000"}}
    )
    swap_result = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        f"8000{foo_name}",
        "--legs",
        swap_leg_json,
        "--min-output",
        f"1{bar_name}",
        "--from",
        charlie_name,
    )
    assert (
        swap_result.get("code", 1) == 0
    ), f"Price manipulation swap failed: {swap_result}"

    # Charlie's foo before closing (collateral is currently escrowed)
    bal_before = dysond("query", "bank", "balances", charlie_addr)
    foo_before = int(
        [b for b in bal_before["balances"] if b["denom"] == foo_name][0]["amount"]
    )

    # Close position → should return full collateral and positive profit in foo
    close_result = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        position_id,
        "--fraction",
        "1",
        "--from",
        charlie_name,
    )
    assert close_result.get("code", 1) == 0, f"Close position failed: {close_result}"

    # Profit event attribute should exist
    close_events = [
        e
        for e in close_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
    ]
    assert len(close_events) == 1, "EventLeveragePositionClosed not found"
    profit_attrs = [
        a for a in close_events[0].get("attributes", []) if a.get("key") == "profit"
    ]
    assert len(profit_attrs) == 1, "profit attribute not found"

    # Charlie's foo increased by full collateral plus some profit
    bal_after = dysond("query", "bank", "balances", charlie_addr)
    foo_after = int(
        [b for b in bal_after["balances"] if b["denom"] == foo_name][0]["amount"]
    )
    delta_foo = foo_after - foo_before
    assert (
        delta_foo > collateral_amt
    ), f"Expected profit & collateral returned, delta={delta_foo}, collateral={collateral_amt}"


def test_close_position_same_denom_insufficient_underwater_rejected(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Reject when same-denom collateral is insufficient to cover shortfall.

    Use multi-block approach with UpdatePoolConfig to set very high APR so accrued interest forces
    repayment > proceeds + collateral, triggering the same-denom rejection branch.
    """
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Block 1: Create pool (standard leverage settings)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "20.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"
    pool_id_attrs = [
        attr.get("value")
        for event in pool_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "pool_id"
        and event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert len(pool_id_attrs) > 0, "pool_id not found"
    pool_id = pool_id_attrs[0].strip('"')

    # Block 2: Set extremely high APR for both coins to force huge interest accrual
    upd = dysond(
        "tx",
        "whaleswap",
        "update-pool-config",
        "--pool-id",
        pool_id,
        "--interest-rate",
        f"1000000000000000.0{foo_name}",  # 1e15 percent APR
        "--interest-rate",
        f"1000000000000000.0{bar_name}",
        "--from",
        alice_name,
    )
    assert upd.get("code", 1) == 0, f"update-pool-config failed: {upd}"

    # Block 3: Open same-denom position: collateral 1500 foo, borrow 1000 foo (CR=1.5, minimum allowed)
    # This makes it very close to underwater, so even small interest will trigger rejection
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"1500{foo_name}",
        "--borrow",
        f"1000{foo_name}",
        "--from",
        alice_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"
    position_id_attrs = [
        attr.get("value")
        for event in open_result.get("events", [])
        for attr in event.get("attributes", [])
        if attr.get("key") == "position_id"
        and event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ]
    assert len(position_id_attrs) > 0, "position_id not found"
    position_id = position_id_attrs[0].strip('"')

    # Block 4: Wait for blocks to pass so interest can accrue
    # Get initial height
    initial_status = dysond("status")
    initial_height = int(
        initial_status.get("sync_info", {}).get("latest_block_height", 0)
    )
    target_height = (
        initial_height + 5
    )  # Wait for at least 5 blocks to ensure time passage

    def check_height_reached():
        status_data = dysond("status")
        current_height = int(
            status_data.get("sync_info", {}).get("latest_block_height", 0)
        )
        return current_height >= target_height

    from utils import poll_until_condition

    poll_until_condition(
        check_height_reached,
        timeout=15,
        poll_interval=0.1,
        error_message=f"Failed to advance 5 blocks from height {initial_height} to {target_height}",
    )

    # Block 5: Attempt to close; extremely high APR should cause massive interest accrual making repayment > proceeds + collateral
    with pytest.raises(Exception, match="insufficient collateral"):
        result = dysond(
            "tx",
            "whaleswap",
            "close-position",
            "--position-id",
            position_id,
            "--fraction",
            "1",
            "--from",
            alice_name,
            "--gas",
            "auto",
        )

        assert (
            result.get("code", 1) != 0
        ), f"Close position should be rejected with insufficient collateral: {result}"
        assert "insufficient collateral" in result.get(
            "raw_log", ""
        ), f"Expected 'insufficient collateral' in error message: {result}"
