"""
Metrics query handler coverage tests.

Tests the Metrics query endpoint which computes comprehensive module metrics
including escrow balances and trade statistics. Covers empty state and populated state.
"""

import json
import pytest
from deep_parse import deep_parse


def test_metrics_structure(chainnet):
    """Test Metrics query response structure."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_metrics_structure():
    metrics_resp = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryMetricsRequest"
    })
    return metrics_resp["metrics"]
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_metrics_structure",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    metrics = demo_result

    # Validate response structure (Type)
    assert isinstance(
        metrics, dict
    ), f"Metrics should be dict, got {type(metrics)}. Full response: {json.dumps(metrics, indent=2)}"

    # Validate all metric fields are present (Type + Shape)
    assert (
        "num_trades" in metrics
    ), f"Metrics missing 'num_trades' key. Keys: {list(metrics.keys())}"
    assert (
        "escrowed_pool_coins" in metrics
    ), f"Metrics missing 'escrowed_pool_coins' key. Keys: {list(metrics.keys())}"
    assert (
        "escrowed_offer_coins" in metrics
    ), f"Metrics missing 'escrowed_offer_coins' key. Keys: {list(metrics.keys())}"
    assert (
        "escrowed_pfand" in metrics
    ), f"Metrics missing 'escrowed_pfand' key. Keys: {list(metrics.keys())}"
    assert (
        "escrowed_auction_coins" in metrics
    ), f"Metrics missing 'escrowed_auction_coins' key. Keys: {list(metrics.keys())}"
    assert (
        "fees_earned" in metrics
    ), f"Metrics missing 'fees_earned' key. Keys: {list(metrics.keys())}"

    # Validate field types (not values, as chain may have activity from other tests)
    assert isinstance(
        metrics.get("num_trades"), (int, str)
    ), f"num_trades should be int or str, got {type(metrics.get('num_trades'))}"
    assert isinstance(
        metrics.get("escrowed_pool_coins", []), list
    ), f"escrowed_pool_coins should be list, got {type(metrics.get('escrowed_pool_coins', []))}"
    assert isinstance(
        metrics.get("escrowed_offer_coins", []), list
    ), f"escrowed_offer_coins should be list, got {type(metrics.get('escrowed_offer_coins', []))}"
    assert isinstance(
        metrics.get("escrowed_pfand", []), list
    ), f"escrowed_pfand should be list, got {type(metrics.get('escrowed_pfand', []))}"
    assert isinstance(
        metrics.get("escrowed_auction_coins", []), list
    ), f"escrowed_auction_coins should be list, got {type(metrics.get('escrowed_auction_coins', []))}"
    assert isinstance(
        metrics.get("fees_earned", []), list
    ), f"fees_earned should be list, got {type(metrics.get('fees_earned', []))}"


def test_metrics_with_activity(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Metrics query with pools, offers, auctions, and trades."""
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

def _pool_config(foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    return {
        "coins": [
            {"denom": foo_name, "amount": "8000"},
            {"denom": bar_name, "amount": "8000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.0"},
            {"denom": quote, "amount": "0.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    }

def demo_metrics_with_activity(alice_addr, foo_name, bar_name):
    cfg = _pool_config(foo_name, bar_name)
    
    # Create pool (adds to escrowed_pool_coins)
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": cfg["coins"],
        "fee_rate": cfg["fee_rate"],
        "min_initial_collateral_ratio": cfg["min_initial_collateral_ratio"],
        "liquidation_threshold": cfg["liquidation_threshold"],
        "max_borrow_percent": cfg["max_borrow_percent"]
    })
    pool_id = int(sudo_pool_result["results"][0]["pool_id"])

    # Open position (adds to escrowed_pfand)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "900"},
        "borrow": {"denom": foo_name, "amount": "600"}
    })

    # Make offer in ESCROW mode (adds to escrowed_offer_coins)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "150"},
        "want": {"denom": bar_name, "amount": "70"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })

    # Make offer in LIQUID mode (no escrow)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": bar_name, "amount": "200"},
        "want": {"denom": foo_name, "amount": "80"},
        "settlement_mode": "SETTLEMENT_LIQUID"
    })

    # Open auction (adds to escrowed_auction_coins)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "sell": {"denom": foo_name, "amount": "500"},
        "bid_denom": bar_name
    })

    # Make trade (adds to num_trades and fees_earned)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": foo_name, "amount": "100"}],
        "operations": [{
            "swap": {
                "pool_id": pool_id,
                "swap_in": {"denom": foo_name, "amount": "100"}
            }
        }],
        "min_output": []
    })

    # Query metrics
    metrics_resp = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryMetricsRequest"
    })
    return metrics_resp["metrics"]
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
        "demo_metrics_with_activity",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    metrics = demo_result

    # Validate response structure (Type)
    assert isinstance(
        metrics, dict
    ), f"Metrics should be dict, got {type(metrics)}. Full response: {json.dumps(metrics, indent=2)}"

    # Validate all metric fields are present (Type + Shape)
    assert (
        "num_trades" in metrics
    ), f"Metrics missing 'num_trades' key. Keys: {list(metrics.keys())}"
    assert (
        "escrowed_pool_coins" in metrics
    ), f"Metrics missing 'escrowed_pool_coins' key. Keys: {list(metrics.keys())}"
    assert (
        "escrowed_offer_coins" in metrics
    ), f"Metrics missing 'escrowed_offer_coins' key. Keys: {list(metrics.keys())}"
    assert (
        "escrowed_pfand" in metrics
    ), f"Metrics missing 'escrowed_pfand' key. Keys: {list(metrics.keys())}"
    assert (
        "escrowed_auction_coins" in metrics
    ), f"Metrics missing 'escrowed_auction_coins' key. Keys: {list(metrics.keys())}"
    assert (
        "fees_earned" in metrics
    ), f"Metrics missing 'fees_earned' key. Keys: {list(metrics.keys())}"

    # Validate populated state values
    trade_count = int(metrics.get("num_trades", 0))
    assert (
        trade_count >= 1
    ), f"Expected at least 1 trade recorded. Got: {trade_count}. Full metrics: {json.dumps(metrics, indent=2)}"

    escrowed_pool_coins = metrics.get("escrowed_pool_coins", [])
    assert (
        len(escrowed_pool_coins) > 0
    ), f"Expected escrowed_pool_coins to be populated. Got: {escrowed_pool_coins}. Full metrics: {json.dumps(metrics, indent=2)}"

    escrowed_offer_coins = metrics.get("escrowed_offer_coins", [])
    assert (
        len(escrowed_offer_coins) > 0
    ), f"Expected escrowed_offer_coins to be populated. Got: {escrowed_offer_coins}. Full metrics: {json.dumps(metrics, indent=2)}"

    escrowed_pfand = metrics.get("escrowed_pfand", [])
    assert (
        len(escrowed_pfand) > 0
    ), f"Expected escrowed_pfand to be populated. Got: {escrowed_pfand}. Full metrics: {json.dumps(metrics, indent=2)}"

    escrowed_auction_coins = metrics.get("escrowed_auction_coins", [])
    assert (
        len(escrowed_auction_coins) > 0
    ), f"Expected escrowed_auction_coins to be populated. Got: {escrowed_auction_coins}. Full metrics: {json.dumps(metrics, indent=2)}"

