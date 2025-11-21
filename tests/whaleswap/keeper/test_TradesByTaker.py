"""
TradesByTaker query handler coverage tests.

Tests the TradesByTaker query endpoint which retrieves all trades
executed by a specific taker address. Covers validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_trades_by_taker_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test TradesByTaker query with valid taker address."""
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

def demo_trades_by_taker(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
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
    })
    pool_id = int(pool_result["results"][0]["pool_id"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "max_input": [{"denom": foo_name, "amount": "1000"}],
        "operations": [
            {
                "swap": {
                    "pool_id": pool_id,
                    "swap_in": {"denom": foo_name, "amount": "1000"}
                }
            }
        ],
        "min_output": []
    })

    trades_response = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByTakerRequest",
        "taker": alice_addr
    })
    return {"trades_response": trades_response}
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
        "demo_trades_by_taker",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    trades_response = result["result"]["result"]["trades_response"]

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"TradesByTaker response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"TradesByTaker response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"

    # Verify trade is in results
    trade_ids_found = [int(t.get("trade_id")) for t in trades_list]
    assert (
        len(trade_ids_found) > 0
    ), f"No trades returned for taker. Response: {json.dumps(trades_response, indent=2)}"

    # Verify all trades belong to taker
    for trade in trades_list:
        assert (
            trade.get("trader") == alice_addr
        ), f"Trade {trade.get('trade_id')} trader mismatch: expected {alice_addr}, got {trade.get('trader')}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_trades_by_taker_empty_taker(chainnet):
    """Test TradesByTaker query with empty taker address."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_trades_by_taker_empty():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByTakerRequest",
        "taker": ""
    })
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
        "demo_trades_by_taker_empty",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for empty taker. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = json.dumps(query_result.get("exception"), indent=2).lower()
    assert (
        "taker required" in exception_str
    ), f"Expected 'taker required' error. Exception: {exception_str}"


def test_trades_by_taker_no_trades(chainnet, generate_account, faucet):
    """Test TradesByTaker query for taker with no trades."""
    dysond = chainnet[0]
    taker_name, taker_addr = generate_account(
        "no_trades_taker", faucet_amount=1_000_000
    )

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = f"""
from dys import _query

def demo_trades_by_taker_empty():
    trades_response = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByTakerRequest",
        "taker": "{taker_addr}"
    }})
    return trades_response
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
        "demo_trades_by_taker_empty",
        "--extra-code",
        extra_code,
    )

    trades_response = deep_parse(query_result)["result"]["result"]

    # Validate response structure (Type)
    assert isinstance(
        trades_response, dict
    ), f"TradesByTaker response should be dict, got {type(trades_response)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        "pagination" in trades_response
    ), f"TradesByTaker response missing 'pagination' key. Keys: {list(trades_response.keys())}. Full response: {json.dumps(trades_response, indent=2)}"

    # Validate trades list is empty (Type + Shape)
    trades_list = trades_response.get("trades", [])
    assert isinstance(
        trades_list, list
    ), f"Trades should be list, got {type(trades_list)}. Full response: {json.dumps(trades_response, indent=2)}"
    assert (
        len(trades_list) == 0
    ), f"Taker with no trades should return empty list. Got {len(trades_list)}: {json.dumps(trades_list, indent=2)}"

    # Validate pagination (Type)
    pagination = trades_response["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"
