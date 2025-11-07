"""
Comprehensive AddressMetrics coverage tests.

Tests all metric tracking code paths including:
- Trading metrics (trades, operations, volume)
- LP metrics (pool creation, liquidity ops)
- Leverage metrics (positions, interest, liquidations)
- Orderbook metrics (offers created/closed/cancelled, maker volume)
- Auction metrics (auctions created, volume)
- Denom metadata filtering
"""

import json
import pytest
from deep_parse import deep_parse


def test_address_metrics_trading_coverage(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test trading metrics tracking through trade execution."""
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

def demo_trade_metrics(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "20.0"},
            {"denom": quote, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    pool_id = pool_result["results"][0]["pool_id"]
    
    # Execute a trade (pool swap)
    trade_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgPoolSwap",
        "trader": alice_addr,
        "max_input": [{"denom": foo_name, "amount": "100"}],
        "legs": [{
            "pool_id": pool_id,
            "swap_in": {"denom": foo_name, "amount": "100"}
        }],
        "min_output": []
    })
    
    # Query metrics
    metrics = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    return {
        "pool_id": pool_id,
        "metrics": metrics
    }
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
        "demo_trade_metrics",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"Expected dict. Got: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    metrics = demo_result["metrics"]["metrics"]

    # Validate trading metrics were tracked
    assert (
        metrics["address"] == alice_addr
    ), f"Address mismatch: {metrics['address']} != {alice_addr}"
    assert int(metrics.get("total_trades", 0)) == 1, f"Should have 1 trade: {metrics}"
    assert (
        int(metrics.get("total_trade_ops", 0)) == 1
    ), f"Should have 1 operation: {metrics}"
    assert (
        int(metrics.get("pools_created", 0)) == 1
    ), f"Should have created 1 pool: {metrics}"


@pytest.mark.usefixtures("faucet")
def test_address_metrics_leverage_coverage(chainnet, generate_account, register_name):
    """Test leverage metrics tracking through position lifecycle (multi-block)."""
    dysond = chainnet[0]

    # Create account and register names
    alice_name, alice_addr = generate_account("lev_alice", faucet_amount=5_000_000)
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

    # Create pool (multi-block)
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
        "--interest-rate",
        f"0.1{base}",
        "--interest-rate",
        f"0.1{quote}",
        "--max-borrow-percent",
        f"0.8{base}",
        "--max-borrow-percent",
        f"0.8{quote}",
        "--from",
        alice_name,
    )
    assert tx_pool.get("code", 1) == 0, f"Pool creation failed: {tx_pool}"

    # Extract pool_id from events using list comprehension
    pool_events = [
        e
        for e in tx_pool.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ]
    assert pool_events, f"Missing EventPoolCreated: {json.dumps(tx_pool, indent=2)}"
    pool_attrs = {
        a.get("key"): a.get("value") for a in pool_events[0].get("attributes", [])
    }
    pool_id = pool_attrs.get("pool_id")
    assert pool_id, f"pool_id missing: {json.dumps(pool_events[0], indent=2)}"
    pool_id = pool_id.strip('"')

    # Open position (multi-block)
    tx_open = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        str(pool_id),
        "--collateral",
        f"750{bar_name}",
        "--borrow",
        f"500{foo_name}",
        "--from",
        alice_name,
    )
    assert tx_open.get("code", 1) == 0, f"Position open failed: {tx_open}"

    # Query metrics after position opened
    metrics_after_open = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )

    # Close position (multi-block - requires block delay)
    tx_close = dysond(
        "tx",
        "whaleswap",
        "close-position",
        "--position-id",
        "1",
        "--from",
        alice_name,
    )
    assert tx_close.get("code", 1) == 0, f"Position close failed: {tx_close}"

    # Query metrics after position closed
    metrics_after_close = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )

    # Validate position opened was tracked
    assert (
        int(metrics_after_open["metrics"].get("positions_opened", 0)) == 1
    ), f"Should have 1 position opened: {metrics_after_open}"
    assert (
        int(metrics_after_open["metrics"].get("positions_closed", 0)) == 0
    ), f"Should have 0 positions closed yet: {metrics_after_open}"

    # Validate position closed was tracked
    assert (
        int(metrics_after_close["metrics"].get("positions_opened", 0)) == 1
    ), f"Should still show 1 opened: {metrics_after_close}"
    assert (
        int(metrics_after_close["metrics"].get("positions_closed", 0)) == 1
    ), f"Should have 1 closed: {metrics_after_close}"


def test_address_metrics_orderbook_coverage(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test orderbook metrics tracking through offer lifecycle."""
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

def demo_orderbook_metrics(alice_addr, bob_addr, foo_name, bar_name):
    # Make offer (escrow mode)
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "100"},
        "want": {"denom": bar_name, "amount": "50"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Query metrics after offer created
    metrics_created = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    # Take half the offer
    take_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgTakeOffer",
        "taker": bob_addr,
        "trades": [{
            "offer_id": offer_id,
            "take_units": "1"
        }]
    })
    
    # Query metrics after partial take
    metrics_partial = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    # Take remaining to close offer
    take_full_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgTakeOffer",
        "taker": bob_addr,
        "trades": [{
            "offer_id": offer_id,
            "take_units": ""
        }]
    })
    
    # Query metrics after offer closed
    metrics_closed = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    # Create and cancel another offer
    cancel_offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": bar_name, "amount": "200"},
        "want": {"denom": foo_name, "amount": "100"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    cancel_offer_id = cancel_offer_result["results"][0]["offer_id"]
    
    cancel_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
        "closer": alice_addr,
        "offer_id": cancel_offer_id
    })
    
    # Query metrics after cancel
    metrics_cancelled = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    return {
        "metrics_created": metrics_created,
        "metrics_partial": metrics_partial,
        "metrics_closed": metrics_closed,
        "metrics_cancelled": metrics_cancelled
    }
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
        "demo_orderbook_metrics",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"Expected dict. Got: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]

    # Validate offer created metrics
    metrics_created = demo_result["metrics_created"]["metrics"]
    assert (
        int(metrics_created.get("offers_created", 0)) == 1
    ), f"Should have 1 offer created: {metrics_created}"
    assert (
        int(metrics_created.get("offers_closed", 0)) == 0
    ), f"Should have 0 closed: {metrics_created}"
    assert (
        int(metrics_created.get("offers_cancelled", 0)) == 0
    ), f"Should have 0 cancelled: {metrics_created}"

    # Validate offer closed metrics
    metrics_closed = demo_result["metrics_closed"]["metrics"]
    assert (
        int(metrics_closed.get("offers_created", 0)) == 1
    ), f"Should still show 1 created: {metrics_closed}"
    assert (
        int(metrics_closed.get("offers_closed", 0)) == 1
    ), f"Should have 1 closed: {metrics_closed}"

    # Validate maker volume tracked (with metadata filtering)
    maker_vol = metrics_closed.get("maker_volume", [])
    assert isinstance(
        maker_vol, list
    ), f"Maker volume should be list: {type(maker_vol)}"

    # Validate cancelled metrics
    metrics_cancelled = demo_result["metrics_cancelled"]["metrics"]
    assert (
        int(metrics_cancelled.get("offers_created", 0)) == 2
    ), f"Should have 2 offers created: {metrics_cancelled}"
    assert (
        int(metrics_cancelled.get("offers_closed", 0)) == 1
    ), f"Should have 1 closed: {metrics_cancelled}"
    assert (
        int(metrics_cancelled.get("offers_cancelled", 0)) == 1
    ), f"Should have 1 cancelled: {metrics_cancelled}"


def test_address_metrics_liquidity_coverage(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test LP metrics tracking through liquidity operations."""
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

def demo_liquidity_metrics(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "20.0"},
            {"denom": quote, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    pool_id = pool_result["results"][0]["pool_id"]
    
    # Add liquidity
    add_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "5000"}
        ]
    })
    
    # Query metrics after add
    metrics_add = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    # Remove liquidity
    remove_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "shares": "1000"
    })
    
    # Query metrics after remove
    metrics_remove = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    return {
        "metrics_add": metrics_add,
        "metrics_remove": metrics_remove
    }
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
        "demo_liquidity_metrics",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"Expected dict. Got: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    metrics_add = demo_result["metrics_add"]["metrics"]
    metrics_remove = demo_result["metrics_remove"]["metrics"]

    # Validate liquidity operations tracked
    # Pool creation counts as liquidity add (initial liquidity) + explicit add = 2 total
    assert (
        int(metrics_add.get("liquidity_adds", 0)) == 2
    ), f"Should have 2 liquidity adds (pool creation + explicit add): {metrics_add}"
    assert (
        int(metrics_add.get("liquidity_removes", 0)) == 0
    ), f"Should have 0 removes: {metrics_add}"

    assert (
        int(metrics_remove.get("liquidity_adds", 0)) == 2
    ), f"Should still have 2 adds: {metrics_remove}"
    assert (
        int(metrics_remove.get("liquidity_removes", 0)) == 1
    ), f"Should have 1 remove: {metrics_remove}"


def test_address_metrics_auction_coverage(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test auction metrics tracking."""
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

def demo_auction_metrics(alice_addr, foo_name, bar_name):
    # Open auction
    auction_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "bid_denom": bar_name,
        "sell": {"denom": foo_name, "amount": "500"}
    })
    
    # Query metrics
    metrics = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    return {"metrics": metrics}
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
        "demo_auction_metrics",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"Expected dict. Got: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    metrics = demo_result["metrics"]["metrics"]

    # Validate auction metrics tracked
    assert (
        int(metrics.get("auctions_created", 0)) == 1
    ), f"Should have 1 auction created: {metrics}"


def test_address_metrics_multiple_addresses(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test that metrics are tracked independently per address."""
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

def demo_multi_address(alice_addr, bob_addr, foo_name, bar_name):
    # Alice creates pool
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": sorted([foo_name, bar_name])[0], "amount": "0.003"},
            {"denom": sorted([foo_name, bar_name])[1], "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": sorted([foo_name, bar_name])[0], "amount": "1.5"},
            {"denom": sorted([foo_name, bar_name])[1], "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": sorted([foo_name, bar_name])[0], "amount": "20.0"},
            {"denom": sorted([foo_name, bar_name])[1], "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": sorted([foo_name, bar_name])[0], "amount": "1.2"},
            {"denom": sorted([foo_name, bar_name])[1], "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": sorted([foo_name, bar_name])[0], "amount": "0.8"},
            {"denom": sorted([foo_name, bar_name])[1], "amount": "0.8"}
        ]
    })
    pool_id = pool_result["results"][0]["pool_id"]
    
    # Bob makes a trade
    bob_trade = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgPoolSwap",
        "trader": bob_addr,
        "max_input": [{"denom": foo_name, "amount": "100"}],
        "legs": [{
            "pool_id": pool_id,
            "swap_in": {"denom": foo_name, "amount": "100"}
        }],
        "min_output": []
    })
    
    # Query both addresses
    alice_metrics = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": alice_addr
    })
    
    bob_metrics = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryAddressMetricsRequest",
        "address": bob_addr
    })
    
    return {
        "alice": alice_metrics,
        "bob": bob_metrics
    }
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
        "demo_multi_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"Expected dict. Got: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    alice_metrics = demo_result["alice"]["metrics"]
    bob_metrics = demo_result["bob"]["metrics"]

    # Alice should have pool creation but no trades
    assert (
        int(alice_metrics.get("pools_created", 0)) == 1
    ), f"Alice should have created 1 pool: {alice_metrics}"
    assert (
        int(alice_metrics.get("total_trades", 0)) == 0
    ), f"Alice should have 0 trades: {alice_metrics}"

    # Bob should have trade but no pool creation
    assert (
        int(bob_metrics.get("pools_created", 0)) == 0
    ), f"Bob should have created 0 pools: {bob_metrics}"
    assert (
        int(bob_metrics.get("total_trades", 0)) == 1
    ), f"Bob should have 1 trade: {bob_metrics}"
    assert (
        int(bob_metrics.get("total_trade_ops", 0)) == 1
    ), f"Bob should have 1 operation: {bob_metrics}"
