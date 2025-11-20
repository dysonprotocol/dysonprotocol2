"""
Trade query handler coverage tests.

Tests the Trade query endpoint which retrieves a single trade by ID.
Covers all validation paths and success cases.
"""

import json
import pytest
from deep_parse import deep_parse


def test_trade_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test Trade query with valid trade ID."""
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

def demo_trade_query(alice_addr, foo_name, bar_name):
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
    
    pool_id = pool_result["results"][0]["pool_id"]
    
    # Make trade with swap operation
    trade_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "operations": [
            {
                "swap": {
                    "pool_id": int(pool_id),
                    "swap_in": {"denom": foo_name, "amount": "1000"}
                }
            }
        ],
        "max_input": [{"denom": foo_name, "amount": "2000"}]
    })
    
    trade_id = trade_result["results"][0]["trade_id"]
    
    # Query trade
    trade_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradeRequest",
        "trade_id": trade_id
    })
    
    return {
        "trade_id": trade_id,
        "trade_query": trade_query
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
        "demo_trade_query",
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

    assert "trade_query" in demo_result, f"Script should return trade_query. Result: {json.dumps(demo_result, indent=2)}"

    trade_response = demo_result["trade_query"]

    # Validate response structure (Type)
    assert isinstance(
        trade_response, dict
    ), f"Trade response should be dict, got {type(trade_response)}"
    assert (
        "trade" in trade_response
    ), f"Trade response missing 'trade' key. Keys: {list(trade_response.keys())}"

    trade = trade_response["trade"]

    # Validate trade structure (Type + Shape)
    assert isinstance(trade, dict), f"Trade should be dict, got {type(trade)}"
    assert (
        "trade_id" in trade
    ), f"Trade missing 'trade_id' key. Keys: {list(trade.keys())}"
    assert (
        "trader" in trade
    ), f"Trade missing 'trader' key. Keys: {list(trade.keys())}"
    assert (
        "total_sent" in trade
    ), f"Trade missing 'total_sent' key. Keys: {list(trade.keys())}"
    assert (
        "total_received" in trade
    ), f"Trade missing 'total_received' key. Keys: {list(trade.keys())}"

    # Validate values
    assert (
        int(trade["trade_id"]) == int(demo_result["trade_id"])
    ), f"Trade ID mismatch: expected {demo_result['trade_id']}, got {trade['trade_id']}"
    assert (
        trade["trader"] == alice_addr
    ), f"Trader mismatch: expected {alice_addr}, got {trade['trader']}"


def test_trade_zero_id(chainnet):
    """Test Trade query with zero trade ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_trade_zero_id():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradeRequest",
        "trade_id": 0
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
        "demo_trade_zero_id",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for zero trade_id. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "trade_id required" in exception_str
    ), f"Expected 'trade_id required' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"


def test_trade_not_found(chainnet):
    """Test Trade query with non-existent trade ID."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_trade_not_found():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradeRequest",
        "trade_id": 999999
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
        "demo_trade_not_found",
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for non-existent trade. Full result: {json.dumps(query_result, indent=2)}"
    exception_str = str(query_result["exception"]).lower()
    assert (
        "trade not found" in exception_str
    ), f"Expected 'trade not found' error. Exception: {json.dumps(query_result.get('exception'), indent=2)}"

