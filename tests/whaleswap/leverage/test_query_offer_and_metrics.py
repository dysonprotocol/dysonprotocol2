"""
Script-mode tests for query_server Offer + Metrics handlers.

State setup happens via MsgSudo calls inside a single dyslang execution so
no chain mutation persists beyond each test, keeping the leverage suite
deterministic while still exercising keeper logic.
"""

import json
from deep_parse import deep_parse


def test_query_offer_single_block(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Ensure QueryOffer returns newly created offer data."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_offer_query(alice_addr, foo_name, bar_name):
    make_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "120"},
        "want": {"denom": bar_name, "amount": "60"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })
    offer_id = int(make_resp["results"][0]["offer_id"])
    offer_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": offer_id
    })
    return {"offer_id": offer_id, "offer": offer_query["offer"]}
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
        "demo_offer_query",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert isinstance(
        parsed, dict
    ), f"deep_parse should return dict: {json.dumps(query_result, indent=2)}"
    assert query_result.get("exception") is None, json.dumps(query_result, indent=2)
    payload = parsed["result"]["result"]
    assert payload["offer_id"] > 0, f"offer_id missing: {json.dumps(payload, indent=2)}"
    offer = payload["offer"]
    assert (
        offer["maker"] == alice_addr
    ), f"maker mismatch: {json.dumps(offer, indent=2)}"
    assert (
        offer["initial_have"]["denom"] == foo_name
    ), f"initial_have denom mismatch: {json.dumps(offer, indent=2)}"
    assert (
        offer["initial_want"]["denom"] == bar_name
    ), f"initial_want denom mismatch: {json.dumps(offer, indent=2)}"
    assert offer["status"] == "open", (
        "QueryOffer returns string literals (not enum names); "
        f"unexpected status payload: {json.dumps(offer, indent=2)}"
    )


def test_query_offer_requires_positive_id(chainnet):
    """Offer query should reject non-positive identifiers."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _query

def demo_offer_invalid_id():
    return _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
        "offer_id": 0
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
        "demo_offer_invalid_id",
        "--extra-code",
        extra_code,
    )
    assert (
        query_result.get("exception") is not None
    ), f"expected invalid request: {json.dumps(query_result, indent=2)}"
    assert (
        "offer_id required" in str(query_result["exception"]).lower()
    ), f"missing offer_id validation detail: {json.dumps(query_result, indent=2)}"


def test_query_metrics_single_block(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """QueryMetrics aggregates pools, offers, pfand, auctions, and trades."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

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
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    }

def demo_metrics(alice_addr, foo_name, bar_name):
    cfg = _pool_config(foo_name, bar_name)
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

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "900"},
        "borrow": {"denom": foo_name, "amount": "600"}
    })

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": foo_name, "amount": "150"},
        "want": {"denom": bar_name, "amount": "70"},
        "settlement_mode": "SETTLEMENT_ESCROW"
    })

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": alice_addr,
        "have": {"denom": bar_name, "amount": "200"},
        "want": {"denom": foo_name, "amount": "80"},
        "settlement_mode": "SETTLEMENT_LIQUID"
    })

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
        "seller": alice_addr,
        "sell": {"denom": foo_name, "amount": "500"},
        "bid_denom": bar_name
    })

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
        "demo_metrics",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert isinstance(
        parsed, dict
    ), f"deep_parse should return dict: {json.dumps(query_result, indent=2)}"
    assert query_result.get("exception") is None, json.dumps(query_result, indent=2)
    metrics = parsed["result"]["result"]

    trade_count = int(metrics.get("num_trades", "0"))
    assert (
        trade_count >= 1
    ), f"expected at least one trade recorded: {json.dumps(metrics, indent=2)}"
    assert metrics[
        "escrowed_pool_coins"
    ], f"pool coins empty: {json.dumps(metrics, indent=2)}"
    assert metrics[
        "escrowed_offer_coins"
    ], f"offer coins empty: {json.dumps(metrics, indent=2)}"
    assert metrics[
        "escrowed_pfand"
    ], f"pfand coins empty: {json.dumps(metrics, indent=2)}"
    assert metrics[
        "escrowed_auction_coins"
    ], f"auction coins empty: {json.dumps(metrics, indent=2)}"
