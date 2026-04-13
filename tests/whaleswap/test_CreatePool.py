"""
Test MsgCreatePool for whaleswap pools.

These tests exercise the primary happy paths for pool creation after introducing
`bound_percent`, covering:
- Default (unbounded) directional price limits
- Custom directional bounds at pool creation
- Interaction with other configurable vectors (interest_rate)
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


@pytest.mark.usefixtures("faucet")
def test_create_pool_unbounded_basic_success(chainnet, generate_account, register_name):
    """Create an AMM pool without providing bound_percent and verify defaults."""
    dysond = chainnet[0]

    alice_name, alice_addr = generate_account("pool_alice", faucet_amount=1_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    params = dysond("query", "nameservice", "params")
    mint_fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * mint_fee_per + 0.99999)
    for denom in [foo_name, bar_name]:
        mint_tx = dysond(
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
        assert (
            mint_tx.get("code", 1) == 0
        ), f"mint-coins failed: {json.dumps(mint_tx, indent=2)}"

    extra_code = """
from dys import _msg, _query, get_executor_address


def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })


def demo_create_pool_unbounded(alice_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.003"},
            {"denom": denom_b, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "interest_rate": [
            {"denom": denom_a, "amount": "0.0"},
            {"denom": denom_b, "amount": "0.0"}
        ],
        "liquidation_threshold": [
            {"denom": denom_a, "amount": "1.2"},
            {"denom": denom_b, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": denom_a, "amount": "0.8"},
            {"denom": denom_b, "amount": "0.8"}
        ]
    })

    pool_id = sudo_pool_result["results"][0]["pool_id"]
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    return {"pool_id": pool_id, "pool": pool_query["pool"], "foo_name": foo_name, "bar_name": bar_name}
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_create_pool_unbounded",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Full: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result['exception'], indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Expected dict payload, got {type(demo_result)}"

    pool = demo_result["pool"]
    assert isinstance(pool, dict), f"Pool payload should be dict, got {type(pool)}"
    assert (
        pool["pool_id"] == demo_result["pool_id"]
    ), f"Pool ID mismatch: {demo_result['pool_id']} vs {pool['pool_id']}"

    bound_percent = pool.get("bound_percent", [])
    assert isinstance(
        bound_percent, list
    ), f"bound_percent should be list, got {type(bound_percent)}"
    assert (
        len(bound_percent) == 2
    ), f"Default bound_percent should contain two entries, got {len(bound_percent)}"

    bound_by_denom = {entry["denom"]: entry["amount"] for entry in bound_percent}
    denom_a, denom_b = sorted([demo_result["foo_name"], demo_result["bar_name"]])
    assert (
        bound_by_denom[denom_a] == "1.000000000000000000"
    ), f"Expected {denom_a} bound 1.0, got {bound_by_denom[denom_a]}"
    assert (
        bound_by_denom[denom_b] == "1.000000000000000000"
    ), f"Expected {denom_b} bound 1.0, got {bound_by_denom[denom_b]}"


@pytest.mark.usefixtures("faucet")
def test_create_pool_with_bound_percent(chainnet, generate_account, register_name):
    """Create an AMM pool supplying asymmetric bound_percent values."""
    dysond = chainnet[0]

    alice_name, alice_addr = generate_account("pool_bounds", faucet_amount=1_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    params = dysond("query", "nameservice", "params")
    mint_fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * mint_fee_per + 0.99999)
    for denom in [foo_name, bar_name]:
        mint_tx = dysond(
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
        assert (
            mint_tx.get("code", 1) == 0
        ), f"mint-coins failed: {json.dumps(mint_tx, indent=2)}"

    extra_code = """
from dys import _msg, _query, get_executor_address


def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })


def demo_create_pool_with_bounds(alice_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.002"},
            {"denom": denom_b, "amount": "0.004"}
        ],
        "interest_rate": [
            {"denom": denom_a, "amount": "0.0"},
            {"denom": denom_b, "amount": "0.0"}
        ],
        "bound_percent": [
            {"denom": denom_a, "amount": "0.250000000000000000"},
            {"denom": denom_b, "amount": "0.750000000000000000"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": denom_a, "amount": "1.2"},
            {"denom": denom_b, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": denom_a, "amount": "0.8"},
            {"denom": denom_b, "amount": "0.8"}
        ]
    })

    pool_id = sudo_pool_result["results"][0]["pool_id"]
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    return {"pool": pool_query["pool"], "pool_id": pool_id, "denom_a": denom_a, "denom_b": denom_b}
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_create_pool_with_bounds",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Full: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result['exception'], indent=2)}"

    demo_result = result["result"]["result"]
    pool = demo_result["pool"]

    bound_percent = pool.get("bound_percent", [])
    assert (
        len(bound_percent) == 2
    ), f"Custom bound_percent should contain two entries, got {len(bound_percent)}"

    denom_bound = {entry["denom"]: entry["amount"] for entry in bound_percent}
    denom_a, denom_b = sorted([foo_name, bar_name])
    assert (
        denom_bound[denom_a] == "0.250000000000000000"
    ), f"Expected {denom_a} bound 0.25, got {denom_bound[denom_a]}"
    assert (
        denom_bound[denom_b] == "0.750000000000000000"
    ), f"Expected {denom_b} bound 0.75, got {denom_bound[denom_b]}"


@pytest.mark.usefixtures("faucet")
def test_create_pool_with_custom_interest_rate(
    chainnet, generate_account, register_name
):
    """Ensure interest_rate configuration coexists with bound_percent defaults."""
    dysond = chainnet[0]

    alice_name, alice_addr = generate_account("pool_interest", faucet_amount=1_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    params = dysond("query", "nameservice", "params")
    mint_fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * mint_fee_per + 0.99999)
    for denom in [foo_name, bar_name]:
        mint_tx = dysond(
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
        assert (
            mint_tx.get("code", 1) == 0
        ), f"mint-coins failed: {json.dumps(mint_tx, indent=2)}"

    extra_code = """
from dys import _msg, _query, get_executor_address


def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })


def demo_create_pool_with_interest(alice_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.003"},
            {"denom": denom_b, "amount": "0.003"}
        ],
        "interest_rate": [
            {"denom": denom_a, "amount": "0.05"},
            {"denom": denom_b, "amount": "0.05"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": denom_a, "amount": "1.2"},
            {"denom": denom_b, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": denom_a, "amount": "0.7"},
            {"denom": denom_b, "amount": "0.7"}
        ]
    })

    pool_id = sudo_pool_result["results"][0]["pool_id"]
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    return {"pool": pool_query["pool"], "denom_a": denom_a, "denom_b": denom_b}
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
        "demo_create_pool_with_interest",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Full: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result['exception'], indent=2)}"

    demo_result = result["result"]["result"]
    pool = demo_result["pool"]

    interest_rate = pool.get("interest_rate", [])
    assert (
        len(interest_rate) == 2
    ), f"Interest rate should include both denoms, got {len(interest_rate)}"
    interest_by_denom = {entry["denom"]: entry["amount"] for entry in interest_rate}
    assert interest_by_denom[demo_result["denom_a"]] == "0.050000000000000000"
    assert interest_by_denom[demo_result["denom_b"]] == "0.050000000000000000"

    bound_percent = pool.get("bound_percent", [])
    assert (
        len(bound_percent) == 2
    ), f"Default bound_percent should still be populated, got {len(bound_percent)}"
