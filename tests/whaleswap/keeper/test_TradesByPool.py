"""
TradesByPool query handler coverage tests.

Tests the TradesByPool query endpoint which retrieves all trades
involving a specific AMM pool. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_trades_by_pool_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test TradesByPool query with valid pool ID."""
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

    # Query trades by pool using CLI
    trades_response = dysond(
        "query", "whaleswap", "trades-by-pool", "--pool-id", pool_id
    )

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"TradesByPool response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"TradesByPool response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"

    # Verify trade is in results
    trade_ids_found = [int(t.get("trade_id")) for t in trades_list]
    assert (
        int(trade_id) in trade_ids_found
    ), f"Trade ID {trade_id} not found in pool's trades. Found IDs: {trade_ids_found}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"


def test_trades_by_pool_zero_id(chainnet):
    """Test TradesByPool query with zero pool ID."""
    dysond = chainnet[0]

    # Query trades by pool with zero pool_id (should fail)
    result = dysond("query", "whaleswap", "trades-by-pool", "--pool-id", "0")

    # Should return error
    assert isinstance(result, str), f"Expected error string, got {type(result)}: {result}"
    assert (
        "pool_id required" in result.lower()
    ), f"Expected 'pool_id required' error. Got: {result}"


def test_trades_by_pool_no_trades(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test TradesByPool query for pool with no trades."""
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

    # Query trades by pool (no trades yet)
    trades_response = dysond(
        "query", "whaleswap", "trades-by-pool", "--pool-id", pool_id
    )

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"TradesByPool response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"TradesByPool response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list is empty (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        len(trades_list) == 0
    ), f"Pool with no trades should return empty list. Got {len(trades_list)}: {json.dumps(trades_list, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(pagination, dict), f"Pagination should be dict, got {type(pagination)}"

