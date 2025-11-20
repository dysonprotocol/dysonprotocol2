"""
Test MakeTrade keeper function for combined AMM swaps and orderbook takes.

Tests the MakeTrade message handler which combines pool swaps and offer takes
into a single transaction with end-of-tx settlement, netting, and coverage.

Covers validation paths and happy paths for MakeTrade function.
"""

import json
import pytest
from deep_parse import deep_parse


def test_make_trade_swap_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful trade with swap operation (happy path)."""
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

def demo_make_trade_swap(alice_addr, foo_name, bar_name):
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
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    return {
        "pool_id": pool_id,
        "trade_result": trade_result["results"][0]
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
        "demo_make_trade_swap",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    trade_result = demo_result["trade_result"]

    assert "trade_id" in trade_result, f"Missing trade_id: {trade_result}"
    assert trade_result["trade_id"] is not None, f"Trade ID should not be None"
    assert "trader_inputs" in trade_result, f"Missing trader_inputs"
    assert "trader_outputs" in trade_result, f"Missing trader_outputs"


def test_make_trade_take_escrow_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful trade with take operation in ESCROW mode."""
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

def demo_make_trade_take_escrow(alice_addr, foo_name, bar_name):
    # Create offer in ESCROW mode
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    # Make trade with take operation
    trade_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "operations": [
            {
                "take": {
                    "offer_id": int(offer_id),
                    "take_units": "1"
                }
            }
        ],
        "max_input": [{"denom": bar_name, "amount": "3000"}]
    })
    
    return {
        "offer_id": offer_id,
        "trade_result": trade_result["results"][0]
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
        "demo_make_trade_take_escrow",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    trade_result = demo_result["trade_result"]

    assert "trade_id" in trade_result, f"Missing trade_id: {trade_result}"
    assert trade_result["trade_id"] is not None, f"Trade ID should not be None"


def test_make_trade_empty_operations(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with empty operations."""
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

def demo_make_trade_empty_operations(alice_addr):
    try:
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": []
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_make_trade_empty_operations",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "non-empty" in demo_result["error"].lower()
    ), f"Error should mention non-empty: {demo_result['error']}"


def test_make_trade_invalid_trader(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with invalid trader address."""
    dysond = chainnet[0]
    foo_name = leverage_names_and_coins["foo_name"]
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

def demo_make_trade_invalid_trader(foo_name):
    try:
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": "invalid_address",
            "operations": [
                {
                    "swap": {
                        "pool_id": 1,
                        "swap_in": {"denom": foo_name, "amount": "1000"}
                    }
                }
            ]
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"foo_name": foo_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_make_trade_invalid_trader",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "invalid" in demo_result["error"].lower()
    ), f"Error should mention invalid: {demo_result['error']}"


def test_make_trade_note_too_long(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with note exceeding max length."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
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

def demo_make_trade_note_too_long(alice_addr, foo_name):
    # Create a note that's too long (default max is 128)
    long_note = "x" * 200
    
    try:
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": [
                {
                    "swap": {
                        "pool_id": 1,
                        "swap_in": {"denom": foo_name, "amount": "1000"}
                    }
                }
            ],
            "note": long_note
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"alice_addr": alice_addr, "foo_name": foo_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_make_trade_note_too_long",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "too long" in demo_result["error"].lower()
    ), f"Error should mention too long: {demo_result['error']}"


def test_make_trade_invalid_swap_leg(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with invalid swap leg (nil or zero pool_id)."""
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

def demo_make_trade_invalid_swap_leg(alice_addr):
    try:
        # Swap leg with zero pool_id
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": [
                {
                    "swap": {
                        "pool_id": 0,
                        "swap_in": {"denom": "test", "amount": "1000"}
                    }
                }
            ]
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_make_trade_invalid_swap_leg",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "invalid" in demo_result["error"].lower()
    ), f"Error should mention invalid: {demo_result['error']}"


def test_make_trade_duplicate_pool_id(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with duplicate pool_id in operations."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
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

def demo_make_trade_duplicate_pool(alice_addr, foo_name, bar_name):
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
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    try:
        # Use same pool_id twice
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": [
                {
                    "swap": {
                        "pool_id": int(pool_id),
                        "swap_in": {"denom": foo_name, "amount": "1000"}
                    }
                },
                {
                    "swap": {
                        "pool_id": int(pool_id),
                        "swap_in": {"denom": foo_name, "amount": "1000"}
                    }
                }
            ]
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_make_trade_duplicate_pool",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "duplicate" in demo_result["error"].lower()
    ), f"Error should mention duplicate: {demo_result['error']}"


def test_make_trade_duplicate_offer_id(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with duplicate offer_id in operations."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
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

def demo_make_trade_duplicate_offer(alice_addr, foo_name, bar_name):
    # Create offer
    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    
    offer_id = offer_result["results"][0]["offer_id"]
    
    try:
        # Use same offer_id twice
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": [
                {
                    "take": {
                        "offer_id": int(offer_id),
                        "take_units": "1"
                    }
                },
                {
                    "take": {
                        "offer_id": int(offer_id),
                        "take_units": "1"
                    }
                }
            ]
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_make_trade_duplicate_offer",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "duplicate" in demo_result["error"].lower()
    ), f"Error should mention duplicate: {demo_result['error']}"


def test_make_trade_auction_not_implemented(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with auction operation (not yet implemented)."""
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

def demo_make_trade_auction_not_implemented(alice_addr):
    try:
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": [
                {
                    "auction": {
                        "auction_id": 1
                    }
                }
            ]
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_make_trade_auction_not_implemented",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "not yet implemented" in demo_result["error"].lower()
    ), f"Error should mention not yet implemented: {demo_result['error']}"


def test_make_trade_take_liquid_pfand_release(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade releases PFAND when closing liquid offer."""
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


def demo_make_trade_liquid_pfand(alice_addr, bob_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, bar_name])

    # Ensure pfand_per_offer is positive so liquid offers lock PFAND
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "pfand_per_offer": {"denom": "udys", "amount": "5"},
            "valuation_fee_pct": "0",
            "valuation_period": "3600s",
            "bid_timeout": "5s",
            "minimum_bid_percent_increase": "0",
            "max_note_length": 128,
            "block_delay_before_close": 1,
            "block_delay_before_liquidation": 1
        }
    })

    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "1000"},
        "want": {"denom": bar_name, "amount": "2000"},
        "settlement_mode": "SETTLEMENT_LIQUID"
    })

    offer_id = int(offer_result["results"][0]["offer_id"])

    trade_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": bob_addr,
        "operations": [
            {"take": {"offer_id": offer_id}}
        ],
        "max_input": [{"denom": bar_name, "amount": "3000"}]
    })

    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": offer_id
    })

    return {
        "trade": trade_result["results"][0],
        "offer": offer_query["offer"]
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "gov_addr": gov_addr,
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
        "demo_make_trade_liquid_pfand",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    trade_result = demo_result["trade"]
    offer_result = demo_result["offer"]

    assert trade_result.get("trade_id") is not None, f"Missing trade_id: {trade_result}"
    assert offer_result["status"] == "closed", f"Offer should close: {offer_result}"

    trader_outputs = {
        coin["denom"]: coin["amount"] for coin in trade_result.get("trader_outputs", [])
    }
    assert "udys" in trader_outputs, f"PFAND release missing: {trader_outputs}"
    assert (
        trader_outputs["udys"] == "5"
    ), f"PFAND amount mismatch: {trader_outputs['udys']}"


def test_make_trade_self_net_swap_pfand(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade self-netting on PFAND vs swap debit (udys)."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    charlie_addr = leverage_accounts["charlie"]["addr"]
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


def demo_make_trade_self_net_swap_pfand(alice_addr, charlie_addr, foo_name, bar_name, gov_addr):
    base, quote = sorted([foo_name, "udys"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "pfand_per_offer": {"denom": "udys", "amount": "5"},
            "valuation_fee_pct": "0",
            "valuation_period": "3600s",
            "bid_timeout": "5s",
            "minimum_bid_percent_increase": "0",
            "max_note_length": 128,
            "block_delay_before_close": 1,
            "block_delay_before_liquidation": 1
        }
    })

    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "1000"},
            {"denom": "udys", "amount": "1000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.05"},
            {"denom": quote, "amount": "1.05"}
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

    offer_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "100"},
        "want": {"denom": bar_name, "amount": "50"},
        "settlement_mode": "SETTLEMENT_LIQUID"
    })

    offer_id = int(offer_result["results"][0]["offer_id"])

    trade_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": charlie_addr,
        "operations": [
            {
                "swap": {
                    "pool_id": pool_id,
                    "swap_in": {"denom": "udys", "amount": "5"}
                }
            },
            {"take": {"offer_id": offer_id}}
        ],
        "max_input": [
            {"denom": "udys", "amount": "10"},
            {"denom": bar_name, "amount": "100"}
        ]
    })

    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": offer_id
    })

    return {
        "trade": trade_result["results"][0],
        "offer": offer_query["offer"]
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "charlie_addr": charlie_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "gov_addr": gov_addr,
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
        "demo_make_trade_self_net_swap_pfand",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    trade_result = demo_result["trade"]
    inputs = trade_result.get("trader_inputs", [])
    outputs = {
        coin["denom"]: coin["amount"] for coin in trade_result.get("trader_outputs", [])
    }

    input_map = {coin["denom"]: coin["amount"] for coin in inputs}
    assert "udys" not in input_map, f"udys debits should self-net: {inputs}"
    assert "udys" not in outputs, f"udys credits should self-net: {outputs}"
    assert demo_result["offer"]["status"] == "closed", "Offer should close and release PFAND"


def test_make_trade_self_net_dual_swaps(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade self-netting for two swap legs (same denoms)."""
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


def demo_make_trade_self_net_swaps(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])

    # Create two pools with the same pair (unique pool IDs)
    pool1 = _sudo({
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
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.05"},
            {"denom": quote, "amount": "1.05"}
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
    pool2 = _sudo({
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
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.05"},
            {"denom": quote, "amount": "1.05"}
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

    pool1_id = int(pool1["results"][0]["pool_id"])
    pool2_id = int(pool2["results"][0]["pool_id"])

    trade_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "operations": [
            {"swap": {"pool_id": pool1_id, "swap_in": {"denom": foo_name, "amount": "100"}}},
            {"swap": {"pool_id": pool2_id, "swap_in": {"denom": bar_name, "amount": "100"}}}
        ],
        "max_input": [
            {"denom": foo_name, "amount": "500"},
            {"denom": bar_name, "amount": "500"}
        ]
    })

    return trade_result["results"][0]
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
        "demo_make_trade_self_net_swaps",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    trade_result = result["result"]["result"]
    assert (
        trade_result.get("trade_id") is not None
    ), f"Trade ID missing: {trade_result}"


def test_make_trade_debit_exceeds_cap(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with debit exceeding max_input cap."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
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

def demo_make_trade_debit_exceeds_cap(alice_addr, foo_name, bar_name):
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
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    try:
        # Try to swap with amount exceeding max_input cap
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": [
                {
                    "swap": {
                        "pool_id": int(pool_id),
                        "swap_in": {"denom": foo_name, "amount": "5000"}
                    }
                }
            ],
            "max_input": [{"denom": foo_name, "amount": "1000"}]
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_make_trade_debit_exceeds_cap",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "exceeds cap" in demo_result["error"].lower()
    ), f"Error should mention exceeds cap: {demo_result['error']}"


def test_make_trade_min_output_not_met(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test MakeTrade with min_output not met."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
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

def demo_make_trade_min_output_not_met(alice_addr, foo_name, bar_name):
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
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    try:
        # Try to swap with min_output that's too high
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": [
                {
                    "swap": {
                        "pool_id": int(pool_id),
                        "swap_in": {"denom": foo_name, "amount": "100"}
                    }
                }
            ],
            "max_input": [{"denom": foo_name, "amount": "200"}],
            "min_output": [{"denom": bar_name, "amount": "999999"}]
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
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
        "demo_make_trade_min_output_not_met",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    demo_result = result["result"]["result"]
    assert "expected" in demo_result, f"Should have failed: {demo_result}"
    assert (
        "min_output" in demo_result["error"].lower()
    ), f"Error should mention min_output: {demo_result['error']}"

