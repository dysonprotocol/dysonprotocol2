"""
Test MsgInitializeLiquidation for leverage positions.

Covers the keeper logic for marking a position as liquidatable and the
validation that rejects healthy positions. These tests exercise both the
success path (CR below liquidation_threshold) and the failure path (CR above
threshold) to ensure the keeper enforces safety invariants.
"""

import json
from deep_parse import deep_parse


def test_initialize_liquidation_liquidatable_position(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Initialize liquidation when CR < liquidation_threshold."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    initializer_addr = leverage_accounts["bob"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")[
        "account"
    ]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address


def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })


def demo_initialize_liquidation(alice_addr, initializer_addr, borrow_denom, collateral_denom):
    base, quote = sorted([borrow_denom, collateral_denom])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": borrow_denom, "amount": "10000"},
            {"denom": collateral_denom, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.100000000000000000"},
            {"denom": quote, "amount": "1.100000000000000000"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "5.000000000000000000"},
            {"denom": quote, "amount": "5.000000000000000000"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.200000000000000000"},
            {"denom": quote, "amount": "1.200000000000000000"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.800000000000000000"},
            {"denom": quote, "amount": "0.800000000000000000"}
        ]
    })

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]

    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": borrow_denom, "amount": "115"},
        "borrow": {"denom": borrow_denom, "amount": "100"}
    })

    position_result = sudo_position_result["results"][0]
    position_id = position_result["position_id"]

    sudo_liquidation_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": initializer_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })

    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": int(position_id)
    })

    return {
        "pool_id": pool_id,
        "position_id": position_id,
        "liquidation_result": sudo_liquidation_result["results"][0],
        "position_query": position_query
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "initializer_addr": initializer_addr,
            "borrow_denom": foo_name,
            "collateral_denom": bar_name,
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
        "demo_initialize_liquidation",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert isinstance(
        parsed, dict
    ), f"Parsed result must be dict. type={type(parsed)} full={json.dumps(query_result, indent=2)}"
    assert (
        parsed is not None
    ), f"Parsed result must not be None. raw={json.dumps(query_result, indent=2)}"
    assert "result" in parsed, f"Missing 'result' key. keys={list(parsed.keys())}"

    payload = parsed["result"]["result"]
    assert isinstance(
        payload, dict
    ), f"Payload must be dict. type={type(payload)} full={json.dumps(parsed, indent=2)}"

    liquidation_result = payload["liquidation_result"]
    position_query = payload["position_query"]

    assert isinstance(
        liquidation_result, dict
    ), f"Liquidation result must be dict. type={type(liquidation_result)}"
    assert (
        liquidation_result["collateral_ratio"]
        == "1.150000000000000000"
    ), f"Collateral ratio mismatch. result={json.dumps(liquidation_result, indent=2)}"
    assert (
        liquidation_result["liquidation_threshold"]
        == "1.200000000000000000"
    ), f"Liquidation threshold mismatch. result={json.dumps(liquidation_result, indent=2)}"

    assert isinstance(
        position_query, dict
    ), f"Position query must be dict. type={type(position_query)}"
    assert "position" in position_query, f"Position response missing 'position'. keys={list(position_query.keys())}"
    position = position_query["position"]
    assert (
        position["liquidation_status"]
        == "LIQUIDATION_STATUS_INITIALIZED"
    ), f"Liquidation status incorrect. position={json.dumps(position, indent=2)}"
    assert (
        int(position["liquidation_initialized_block_height"]) > 0
    ), f"Initialization block height must be > 0. position={json.dumps(position, indent=2)}"


def test_initialize_liquidation_rejects_healthy_position(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Reject initialization when CR >= liquidation_threshold."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    initializer_addr = leverage_accounts["bob"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")[
        "account"
    ]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address


def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })


def demo_initialize_liquidation_failure(alice_addr, initializer_addr, borrow_denom, collateral_denom):
    base, quote = sorted([borrow_denom, collateral_denom])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": borrow_denom, "amount": "10000"},
            {"denom": collateral_denom, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.100000000000000000"},
            {"denom": quote, "amount": "1.100000000000000000"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "5.000000000000000000"},
            {"denom": quote, "amount": "5.000000000000000000"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.200000000000000000"},
            {"denom": quote, "amount": "1.200000000000000000"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.800000000000000000"},
            {"denom": quote, "amount": "0.800000000000000000"}
        ]
    })

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]

    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": borrow_denom, "amount": "130"},
        "borrow": {"denom": borrow_denom, "amount": "100"}
    })

    position_result = sudo_position_result["results"][0]
    position_id = position_result["position_id"]

    return _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": initializer_addr,
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": int(position_id)
    })
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "initializer_addr": initializer_addr,
            "borrow_denom": foo_name,
            "collateral_denom": bar_name,
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
        "demo_initialize_liquidation_failure",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert (
        query_result.get("result") is None
    ), f"Script should not return result. full={json.dumps(query_result, indent=2)}"
    exception = query_result.get("exception")
    assert isinstance(
        exception, dict
    ), f"Exception must be dict. type={type(exception)} full={json.dumps(query_result, indent=2)}"
    assert (
        exception.get("class") == "DysRuntimeError"
    ), f"Unexpected exception class. exception={json.dumps(exception, indent=2)}"

    expected_msg = (
        "DysMsgException('failed to DispatchMessage: failed to dispatch message: "
        "sudo message failed (index=0 type=/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation): "
        "failed to dispatch sudo message: collateral ratio 1.300000000000000000 >= "
        "liquidation threshold 1.200000000000000000: position not liquidatable')"
    )
    assert (
        exception.get("msg") == expected_msg
    ), f"Unexpected exception message. expected={expected_msg} actual={json.dumps(exception, indent=2)}"

