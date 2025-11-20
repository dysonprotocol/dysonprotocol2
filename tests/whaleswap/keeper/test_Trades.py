"""
Trades query handler coverage tests.

Tests the Trades query endpoint which lists trades with optional
denom filters. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_trades_no_filters(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Trades query with no filters."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool using multi-block transaction
    tx_pool = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert (
        tx_pool.get("code", 1) == 0
    ), f"Create pool failed: {json.dumps(tx_pool, indent=2)}"

    # Extract pool_id from events
    pool_events = [
        e
        for e in tx_pool.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert (
        pool_events
    ), f"Missing EventPoolCreated: {json.dumps(tx_pool, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    # Create trade using multi-block transaction
    tx_trade = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"1000{foo_name}",
        "--op",
        json.dumps({"swap": {"pool_id": int(pool_id), "swap_in": {"denom": foo_name, "amount": "1000"}}}),
        "--from",
        alice_name,
    )
    assert (
        tx_trade.get("code", 1) == 0
    ), f"Make trade failed: {json.dumps(tx_trade, indent=2)}"

    # Extract trade_id from events
    trade_events = [
        e
        for e in tx_trade.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    ]
    assert (
        trade_events
    ), f"Missing EventTradeRecorded: {json.dumps(tx_trade, indent=2)}"
    trade_attrs = {
        a.get("key"): a.get("value") for a in trade_events[0].get("attributes", [])
    }
    trade_id = trade_attrs.get("trade_id")
    assert trade_id, f"trade_id missing: {json.dumps(trade_events[0], indent=2)}"
    trade_id = trade_id.strip('"')

    # Query trades with no filters using CLI
    trades_response = dysond("query", "whaleswap", "trades")

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"Trades response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"Trades response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_trades_sent_denom_filter(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Trades query with sent_denom filter."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool using multi-block transaction
    tx_pool = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert (
        tx_pool.get("code", 1) == 0
    ), f"Create pool failed: {json.dumps(tx_pool, indent=2)}"

    # Extract pool_id from events
    pool_events = [
        e
        for e in tx_pool.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert (
        pool_events
    ), f"Missing EventPoolCreated: {json.dumps(tx_pool, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    # Create trade using multi-block transaction
    tx_trade = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"1000{foo_name}",
        "--op",
        json.dumps({"swap": {"pool_id": int(pool_id), "swap_in": {"denom": foo_name, "amount": "1000"}}}),
        "--from",
        alice_name,
    )
    assert (
        tx_trade.get("code", 1) == 0
    ), f"Make trade failed: {json.dumps(tx_trade, indent=2)}"

    # Query trades with sent_denom filter using CLI
    trades_response = dysond(
        "query", "whaleswap", "trades", "--sent-denom", foo_name
    )

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"Trades response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"Trades response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_trades_received_denom_filter(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Trades query with received_denom filter."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool using multi-block transaction
    tx_pool = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert (
        tx_pool.get("code", 1) == 0
    ), f"Create pool failed: {json.dumps(tx_pool, indent=2)}"

    # Extract pool_id from events
    pool_events = [
        e
        for e in tx_pool.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert (
        pool_events
    ), f"Missing EventPoolCreated: {json.dumps(tx_pool, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    # Create trade using multi-block transaction
    tx_trade = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"1000{foo_name}",
        "--op",
        json.dumps({"swap": {"pool_id": int(pool_id), "swap_in": {"denom": foo_name, "amount": "1000"}}}),
        "--from",
        alice_name,
    )
    assert (
        tx_trade.get("code", 1) == 0
    ), f"Make trade failed: {json.dumps(tx_trade, indent=2)}"

    # Query trades with received_denom filter using CLI
    trades_response = dysond(
        "query", "whaleswap", "trades", "--received-denom", bar_name
    )

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"Trades response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"Trades response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_trades_both_filters(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Trades query with both sent_denom and received_denom filters."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    alice_name = leverage_accounts["alice"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]

    # Create pool using multi-block transaction
    tx_pool = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo_name}",
        "--coins",
        f"10000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert (
        tx_pool.get("code", 1) == 0
    ), f"Create pool failed: {json.dumps(tx_pool, indent=2)}"

    # Extract pool_id from events
    pool_events = [
        e
        for e in tx_pool.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert (
        pool_events
    ), f"Missing EventPoolCreated: {json.dumps(tx_pool, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    # Create trade using multi-block transaction
    tx_trade = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"1000{foo_name}",
        "--op",
        json.dumps({"swap": {"pool_id": int(pool_id), "swap_in": {"denom": foo_name, "amount": "1000"}}}),
        "--from",
        alice_name,
    )
    assert (
        tx_trade.get("code", 1) == 0
    ), f"Make trade failed: {json.dumps(tx_trade, indent=2)}"

    # Query trades with both filters using CLI
    trades_response = dysond(
        "query",
        "whaleswap",
        "trades",
        "--sent-denom",
        foo_name,
        "--received-denom",
        bar_name,
    )

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"Trades response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"Trades response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"

