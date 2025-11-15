"""
Test MsgRemoveLiquidity for whaleswap pools under the constant-product model.

Happy-path coverage:
- Full exit removing all shares from an unbounded pool
- Partial removal returning proportional reserves
"""

import json
import pytest
from deep_parse import deep_parse


def _mint_custom_denoms(dysond, key_name: str, denoms, amount: int = 1_000_000):
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    fee = int(amount * fee_per + 0.99999)
    for denom in denoms:
        tx = dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{amount}{denom}",
            "--mint-fee",
            f"{fee}udys",
            "--from",
            key_name,
        )
        assert tx.get("code", 1) == 0, f"mint-coins failed: {json.dumps(tx, indent=2)}"


@pytest.mark.usefixtures("faucet")
def test_remove_liquidity_full_exit(chainnet, generate_account, register_name):
    """Removing all shares should return the entire reserve balances."""
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("remliq_full", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    _mint_custom_denoms(dysond, alice_name, [foo_name, bar_name])

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


def demo_remove_liquidity_full(alice_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.002"},
            {"denom": denom_b, "amount": "0.002"}
        ],
        "interest_rate": [
            {"denom": denom_a, "amount": "0.0"},
            {"denom": denom_b, "amount": "0.0"}
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
    pool_id = pool_resp["results"][0]["pool_id"]

    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id,
    })
    shares_denom = pool_query["pool"]["shares_denom"]

    add_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "5000"}
        ]
    })
    _ = add_resp["results"][0]["shares"]

    balance_resp = _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": alice_addr,
        "denom": shares_denom,
    })
    shares = balance_resp["balance"]["amount"]

    remove_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "shares": shares
    })

    return {
        "remove_result": remove_resp["results"][0],
        "foo_name": foo_name,
        "bar_name": bar_name,
    }
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
        "demo_remove_liquidity_full",
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
    remove_result = demo_result["remove_result"]
    outputs = {
        coin["denom"]: int(coin["amount"]) for coin in remove_result.get("amount", [])
    }

    assert outputs[demo_result["foo_name"]] == 15000
    assert outputs[demo_result["bar_name"]] == 15000


@pytest.mark.usefixtures("faucet")
def test_remove_liquidity_partial(chainnet, generate_account, register_name):
    """Removing a portion of shares should return proportional reserves."""
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("remliq_partial", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    _mint_custom_denoms(dysond, alice_name, [foo_name, bar_name])

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


def demo_remove_liquidity_partial(alice_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "12000"},
            {"denom": bar_name, "amount": "12000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.003"},
            {"denom": denom_b, "amount": "0.003"}
        ],
        "interest_rate": [
            {"denom": denom_a, "amount": "0.0"},
            {"denom": denom_b, "amount": "0.0"}
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
    pool_id = pool_resp["results"][0]["pool_id"]

    add_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "10000"}
        ]
    })
    shares = int(add_resp["results"][0]["shares"])

    pool_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    before = {coin["denom"]: int(coin["amount"]) for coin in pool_before["pool"]["coins"]}

    shares_to_remove = str(shares // 2)
    remove_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "shares": shares_to_remove
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    after = {coin["denom"]: int(coin["amount"]) for coin in pool_after["pool"]["coins"]}

    return {
        "remove_result": remove_resp["results"][0],
        "before": before,
        "after": after,
        "foo_name": foo_name,
        "bar_name": bar_name,
        "shares_removed": shares_to_remove,
    }
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
        "demo_remove_liquidity_partial",
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
    remove_result = demo_result["remove_result"]
    before = demo_result["before"]
    after = demo_result["after"]

    outputs = {
        coin["denom"]: int(coin["amount"]) for coin in remove_result.get("amount", [])
    }

    expected_foo = before[demo_result["foo_name"]] - after[demo_result["foo_name"]]
    expected_bar = before[demo_result["bar_name"]] - after[demo_result["bar_name"]]

    assert outputs[demo_result["foo_name"]] == expected_foo
    assert outputs[demo_result["bar_name"]] == expected_bar
