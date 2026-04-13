"""
Directional bound_percent integration tests.

These happy-path scenarios cover:
- Creating a pool with custom bound_percent and adding liquidity
- Updating bound_percent via MsgUpdatePoolConfig after pool creation
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
def test_add_liquidity_preserves_custom_bound_percent(
    chainnet, generate_account, register_name
):
    """Ensure bound_percent survives add-liquidity operations unchanged."""
    dysond = chainnet[0]
    creator_name, creator_addr = generate_account(
        "dir_bounds_add", faucet_amount=1_000_000
    )
    foo_name = register_name(dysond, creator_name, creator_addr, valuation="10udys")
    bar_name = register_name(dysond, creator_name, creator_addr, valuation="10udys")

    _mint_custom_denoms(dysond, creator_name, [foo_name, bar_name])

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


def demo_add_liquidity_preserves_bounds(alice_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "12000"},
            {"denom": bar_name, "amount": "12000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.001"},
            {"denom": denom_b, "amount": "0.001"}
        ],
        "bound_percent": [
            {"denom": denom_a, "amount": "0.400000000000000000"},
            {"denom": denom_b, "amount": "1.000000000000000000"}
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
            {"denom": denom_a, "amount": "0.6"},
            {"denom": denom_b, "amount": "0.6"}
        ]
    })
    pool_id = pool_resp["results"][0]["pool_id"]

    add_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "2000"},
            {"denom": bar_name, "amount": "2000"}
        ]
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {
        "pool_after": pool_after["pool"],
        "add_result": add_resp["results"][0],
        "denom_a": denom_a,
        "denom_b": denom_b,
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": creator_addr,
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
        "demo_add_liquidity_preserves_bounds",
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
    pool_after = demo_result["pool_after"]
    add_result = demo_result["add_result"]

    assert "shares" in add_result and int(add_result["shares"]) > 0

    bounds = {
        entry["denom"]: entry["amount"] for entry in pool_after.get("bound_percent", [])
    }
    assert bounds[demo_result["denom_a"]] == "0.400000000000000000"
    assert bounds[demo_result["denom_b"]] == "1.000000000000000000"


@pytest.mark.usefixtures("faucet")
def test_update_pool_config_updates_bound_percent(
    chainnet, generate_account, register_name
):
    """Happy path for MsgUpdatePoolConfig to change bound_percent."""
    dysond = chainnet[0]
    creator_name, creator_addr = generate_account(
        "dir_bounds_update", faucet_amount=1_000_000
    )
    foo_name = register_name(dysond, creator_name, creator_addr, valuation="10udys")
    bar_name = register_name(dysond, creator_name, creator_addr, valuation="10udys")

    _mint_custom_denoms(dysond, creator_name, [foo_name, bar_name])

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


def demo_update_bound_percent(alice_addr, foo_name, bar_name):
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
            {"denom": denom_a, "amount": "0.7"},
            {"denom": denom_b, "amount": "0.7"}
        ]
    })
    pool_id = pool_resp["results"][0]["pool_id"]

    update_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": alice_addr,
        "pool_id": pool_id,
        "bound_percent": [
            {"denom": denom_a, "amount": "0.300000000000000000"},
            {"denom": denom_b, "amount": "1.000000000000000000"}
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
        "fee_rate": [
            {"denom": denom_a, "amount": "0.002"},
            {"denom": denom_b, "amount": "0.002"}
        ],
        "max_borrow_percent": [
            {"denom": denom_a, "amount": "0.7"},
            {"denom": denom_b, "amount": "0.7"}
        ]
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {
        "pool_after": pool_after["pool"],
        "update_result": update_resp["results"][0],
        "denom_a": denom_a,
        "denom_b": denom_b,
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": creator_addr,
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
        "demo_update_bound_percent",
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
    pool_after = demo_result["pool_after"]
    update_result = demo_result["update_result"]

    assert isinstance(update_result, dict), "Update response should be dict"

    bounds = {
        entry["denom"]: entry["amount"] for entry in pool_after.get("bound_percent", [])
    }
    assert bounds[demo_result["denom_a"]] == "0.300000000000000000"
    assert bounds[demo_result["denom_b"]] == "1.000000000000000000"
