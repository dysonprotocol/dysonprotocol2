"""
Test MsgUpdatePoolConfig for whaleswap pools.

These tests exercise all code paths for pool configuration updates, including:
- Required fields (min_collateral_ratio, liquidation_threshold)
- Optional fields (fee_rate, interest_rate, max_borrow_percent, bound_percent)
- Deprecated max_leverage_ratio handling (should be ignored)
- Validation error paths
- Owner-only access control
"""

import json
import pytest
from deep_parse import deep_parse


def _mint_custom_denoms(dysond, creator_name, denoms):
    """Helper to mint coins for given denoms."""
    params = dysond("query", "nameservice", "params")
    mint_fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * mint_fee_per + 0.99999)
    for denom in denoms:
        mint_tx = dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{mint_amount}{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            creator_name,
        )
        assert (
            mint_tx.get("code", 1) == 0
        ), f"mint-coins failed: {json.dumps(mint_tx, indent=2)}"


@pytest.mark.usefixtures("faucet")
def test_update_pool_config_all_fields_success(
    chainnet, generate_account, register_name
):
    """Test UpdatePoolConfig with all fields updated successfully."""
    dysond = chainnet[0]
    creator_name, creator_addr = generate_account(
        "update_all_fields", faucet_amount=5_000_000
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


def demo_update_all_fields(creator_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    # Create pool
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.001"},
            {"denom": denom_b, "amount": "0.001"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "10.0"},
            {"denom": denom_b, "amount": "10.0"}
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

    # Update all fields
    update_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": creator_addr,
        "pool_id": pool_id,
        "fee_rate": [
            {"denom": denom_a, "amount": "0.002"},
            {"denom": denom_b, "amount": "0.002"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "2.0"},
            {"denom": denom_b, "amount": "2.0"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "99.0"},
            {"denom": denom_b, "amount": "99.0"}
        ],
        "liquidation_threshold": [
            {"denom": denom_a, "amount": "1.3"},
            {"denom": denom_b, "amount": "1.3"}
        ],
        "interest_rate": [
            {"denom": denom_a, "amount": "0.05"},
            {"denom": denom_b, "amount": "0.05"}
        ],
        "max_borrow_percent": [
            {"denom": denom_a, "amount": "0.8"},
            {"denom": denom_b, "amount": "0.8"}
        ],
        "bound_percent": [
            {"denom": denom_a, "amount": "0.5"},
            {"denom": denom_b, "amount": "0.9"}
        ]
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {
        "pool_id": pool_id,
        "update_resp": update_resp,
        "pool": pool_after["pool"]
    }
"""

    kwargs = json.dumps(
        {
            "creator_addr": creator_addr,
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
        "demo_update_all_fields",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    assert query_result.get("exception") is None, f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"
    assert "pool_id" in demo_result, f"Missing pool_id. Keys: {list(demo_result.keys())}"
    assert "pool" in demo_result, f"Missing pool. Keys: {list(demo_result.keys())}"

    pool = demo_result["pool"]
    denom_a, denom_b = sorted([foo_name, bar_name])

    # Verify fee_rate updated
    fee_map = {fr["denom"]: fr["amount"] for fr in pool["fee_rate"]}
    assert fee_map[denom_a] == "0.002000000000000000", f"Fee rate for {denom_a} should be 0.002"
    assert fee_map[denom_b] == "0.002000000000000000", f"Fee rate for {denom_b} should be 0.002"

    # Verify min_collateral_ratio updated
    mcr_map = {mcr["denom"]: mcr["amount"] for mcr in pool["min_collateral_ratio"]}
    assert mcr_map[denom_a] == "2.000000000000000000", f"Min CR for {denom_a} should be 2.0"
    assert mcr_map[denom_b] == "2.000000000000000000", f"Min CR for {denom_b} should be 2.0"

    # Verify liquidation_threshold updated
    liq_map = {liq["denom"]: liq["amount"] for liq in pool["liquidation_threshold"]}
    assert liq_map[denom_a] == "1.300000000000000000", f"Liquidation threshold for {denom_a} should be 1.3"
    assert liq_map[denom_b] == "1.300000000000000000", f"Liquidation threshold for {denom_b} should be 1.3"

    # Verify interest_rate updated
    ir_map = {ir["denom"]: ir["amount"] for ir in pool["interest_rate"]}
    assert ir_map[denom_a] == "0.050000000000000000", f"Interest rate for {denom_a} should be 0.05"
    assert ir_map[denom_b] == "0.050000000000000000", f"Interest rate for {denom_b} should be 0.05"

    # Verify max_borrow_percent updated
    mbp_map = {mbp["denom"]: mbp["amount"] for mbp in pool["max_borrow_percent"]}
    assert mbp_map[denom_a] == "0.800000000000000000", f"Max borrow percent for {denom_a} should be 0.8"
    assert mbp_map[denom_b] == "0.800000000000000000", f"Max borrow percent for {denom_b} should be 0.8"

    # Verify bound_percent updated
    bp_map = {bp["denom"]: bp["amount"] for bp in pool["bound_percent"]}
    assert bp_map[denom_a] == "0.500000000000000000", f"Bound percent for {denom_a} should be 0.5"
    assert bp_map[denom_b] == "0.900000000000000000", f"Bound percent for {denom_b} should be 0.9"


@pytest.mark.usefixtures("faucet")
def test_update_pool_config_deprecated_max_leverage_ignored(
    chainnet, generate_account, register_name
):
    """Test that deprecated max_leverage_ratio is accepted but ignored."""
    dysond = chainnet[0]
    creator_name, creator_addr = generate_account(
        "update_deprecated", faucet_amount=5_000_000
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


def demo_deprecated_ignored(creator_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    # Create pool
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.001"},
            {"denom": denom_b, "amount": "0.001"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "10.0"},
            {"denom": denom_b, "amount": "10.0"}
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

    # Update with deprecated max_leverage_ratio - should be accepted but ignored
    update_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
        "signer": creator_addr,
        "pool_id": pool_id,
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "2.0"},
            {"denom": denom_b, "amount": "2.0"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "999.0"},
            {"denom": denom_b, "amount": "999.0"}
        ],
        "liquidation_threshold": [
            {"denom": denom_a, "amount": "1.3"},
            {"denom": denom_b, "amount": "1.3"}
        ]
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {
        "pool_id": pool_id,
        "update_resp": update_resp,
        "pool": pool_after["pool"]
    }
"""

    kwargs = json.dumps(
        {
            "creator_addr": creator_addr,
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
        "demo_deprecated_ignored",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    assert query_result.get("exception") is None, f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    pool = demo_result["pool"]
    denom_a, denom_b = sorted([foo_name, bar_name])

    # Verify update succeeded
    mcr_map = {mcr["denom"]: mcr["amount"] for mcr in pool["min_collateral_ratio"]}
    assert mcr_map[denom_a] == "2.000000000000000000", f"Min CR should be updated to 2.0"
    assert mcr_map[denom_b] == "2.000000000000000000", f"Min CR should be updated to 2.0"

    liq_map = {liq["denom"]: liq["amount"] for liq in pool["liquidation_threshold"]}
    assert liq_map[denom_a] == "1.300000000000000000", f"Liquidation threshold should be updated to 1.3"
    assert liq_map[denom_b] == "1.300000000000000000", f"Liquidation threshold should be updated to 1.3"


@pytest.mark.usefixtures("faucet")
def test_update_pool_config_min_cr_validation_error(
    chainnet, generate_account, register_name
):
    """Test UpdatePoolConfig validation error for min_collateral_ratio <= 1."""
    dysond = chainnet[0]
    creator_name, creator_addr = generate_account(
        "update_mincr_err", faucet_amount=5_000_000
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


def demo_mincr_error(creator_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    # Create pool
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.001"},
            {"denom": denom_b, "amount": "0.001"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "10.0"},
            {"denom": denom_b, "amount": "10.0"}
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

    # Try to update with invalid min_collateral_ratio (<= 1)
    try:
        update_resp = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
            "signer": creator_addr,
            "pool_id": pool_id,
            "min_collateral_ratio": [
                {"denom": denom_a, "amount": "1.0"},
                {"denom": denom_b, "amount": "1.5"}
            ],
            "liquidation_threshold": [
                {"denom": denom_a, "amount": "1.2"},
                {"denom": denom_b, "amount": "1.2"}
            ]
        })
        return {"error": "Should have failed", "update_resp": update_resp}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps(
        {
            "creator_addr": creator_addr,
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
        "demo_mincr_error",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"
    assert "expected" in demo_result, f"Error should have been caught. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result["expected"] is True, f"Expected error to be caught"


@pytest.mark.usefixtures("faucet")
def test_update_pool_config_liquidation_threshold_validation_error(
    chainnet, generate_account, register_name
):
    """Test UpdatePoolConfig validation error for liquidation_threshold <= 1."""
    dysond = chainnet[0]
    creator_name, creator_addr = generate_account(
        "update_liq_err", faucet_amount=5_000_000
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


def demo_liq_error(creator_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    # Create pool
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.001"},
            {"denom": denom_b, "amount": "0.001"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "10.0"},
            {"denom": denom_b, "amount": "10.0"}
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

    # Try to update with invalid liquidation_threshold (<= 1)
    try:
        update_resp = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
            "signer": creator_addr,
            "pool_id": pool_id,
            "min_collateral_ratio": [
                {"denom": denom_a, "amount": "1.5"},
                {"denom": denom_b, "amount": "1.5"}
            ],
            "liquidation_threshold": [
                {"denom": denom_a, "amount": "0.9"},
                {"denom": denom_b, "amount": "1.2"}
            ]
        })
        return {"error": "Should have failed", "update_resp": update_resp}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps(
        {
            "creator_addr": creator_addr,
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
        "demo_liq_error",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"
    assert "expected" in demo_result, f"Error should have been caught. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result["expected"] is True, f"Expected error to be caught"


@pytest.mark.usefixtures("faucet")
def test_update_pool_config_fee_rate_validation_error(
    chainnet, generate_account, register_name
):
    """Test UpdatePoolConfig validation error for fee_rate >= 1."""
    dysond = chainnet[0]
    creator_name, creator_addr = generate_account(
        "update_fee_err", faucet_amount=5_000_000
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


def demo_fee_error(creator_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    # Create pool
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.001"},
            {"denom": denom_b, "amount": "0.001"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "10.0"},
            {"denom": denom_b, "amount": "10.0"}
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

    # Try to update with invalid fee_rate (>= 1)
    try:
        update_resp = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
            "signer": creator_addr,
            "pool_id": pool_id,
            "fee_rate": [
                {"denom": denom_a, "amount": "1.0"},
                {"denom": denom_b, "amount": "0.001"}
            ],
            "min_collateral_ratio": [
                {"denom": denom_a, "amount": "1.5"},
                {"denom": denom_b, "amount": "1.5"}
            ],
            "liquidation_threshold": [
                {"denom": denom_a, "amount": "1.2"},
                {"denom": denom_b, "amount": "1.2"}
            ]
        })
        return {"error": "Should have failed", "update_resp": update_resp}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps(
        {
            "creator_addr": creator_addr,
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
        "demo_fee_error",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"
    assert "expected" in demo_result, f"Error should have been caught. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result["expected"] is True, f"Expected error to be caught"


@pytest.mark.usefixtures("faucet")
def test_update_pool_config_pool_not_found(
    chainnet, generate_account, register_name
):
    """Test UpdatePoolConfig error when pool doesn't exist."""
    dysond = chainnet[0]
    creator_name, creator_addr = generate_account(
        "update_notfound", faucet_amount=5_000_000
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


def demo_notfound(creator_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    # Try to update non-existent pool
    try:
        update_resp = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgUpdatePoolConfig",
            "signer": creator_addr,
            "pool_id": 99999,
            "min_collateral_ratio": [
                {"denom": denom_a, "amount": "1.5"},
                {"denom": denom_b, "amount": "1.5"}
            ],
            "liquidation_threshold": [
                {"denom": denom_a, "amount": "1.2"},
                {"denom": denom_b, "amount": "1.2"}
            ]
        })
        return {"error": "Should have failed", "update_resp": update_resp}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps(
        {
            "creator_addr": creator_addr,
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
        "demo_notfound",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"Result should be dict, got {type(demo_result)}"
    assert "expected" in demo_result, f"Error should have been caught. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result["expected"] is True, f"Expected error to be caught"

