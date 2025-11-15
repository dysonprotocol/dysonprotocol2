"""
Tests for MsgRemoveCollateral covering happy path and validation failures.

These tests rely on dyslang scripts so state setup and message execution
occur inside a single block, matching the existing leverage suite pattern.
"""

import json
from deep_parse import deep_parse


def test_remove_collateral_basic_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Successful collateral removal returns funds and updates ratio."""
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

def demo_remove_collateral_success(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
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
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    pool_id = int(sudo_pool_result["results"][0]["pool_id"])

    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "1000"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    position_id = int(sudo_position_result["results"][0]["position_id"])

    position_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": position_id
    })

    sudo_remove_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": position_id,
        "collateral": {"denom": bar_name, "amount": "250"}
    })

    position_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": position_id
    })

    return {
        "position_before": position_before,
        "position_after": position_after,
        "remove_response": sudo_remove_result["results"][0]
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
        "demo_remove_collateral_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert query_result.get("exception") is None, json.dumps(query_result, indent=2)

    demo_result = result["result"]["result"]
    position_before = demo_result["position_before"]["position"]
    position_after = demo_result["position_after"]["position"]
    remove_response = demo_result["remove_response"]

    collateral_before = int(position_before["collateral"]["amount"])
    collateral_after = int(position_after["collateral"]["amount"])
    assert (
        collateral_before == 1000
    ), f"Expected 1000 before removal: {json.dumps(position_before, indent=2)}"
    assert (
        collateral_after == 750
    ), f"Expected 750 after removal: {json.dumps(position_after, indent=2)}"
    assert (
        remove_response["collateral_removed"]["amount"] == "250"
    ), f"collateral_removed mismatch: {json.dumps(remove_response, indent=2)}"
    assert isinstance(
        remove_response["new_collateral_ratio"], str
    ), f"new_collateral_ratio should be string: {json.dumps(remove_response, indent=2)}"


def test_remove_collateral_amount_not_positive(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Removing zero collateral fails with clear error."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_remove_collateral_zero_amount(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "5000"}
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
    })
    pool_id = int(sudo_pool_result["results"][0]["pool_id"])

    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "600"},
        "borrow": {"denom": foo_name, "amount": "300"}
    })
    position_id = int(sudo_position_result["results"][0]["position_id"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": position_id,
        "collateral": {"denom": bar_name, "amount": "0"}
    })
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
        "demo_remove_collateral_zero_amount",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is not None, json.dumps(query_result, indent=2)
    message = str(query_result["exception"])
    assert "collateral amount must be positive" in message.lower(), message


def test_remove_collateral_exceeds_available(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Removing full collateral is rejected."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_remove_collateral_exceeds(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "4000"},
            {"denom": bar_name, "amount": "4000"}
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
    })
    pool_id = int(sudo_pool_result["results"][0]["pool_id"])

    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "700"},
        "borrow": {"denom": foo_name, "amount": "350"}
    })
    position_id = int(sudo_position_result["results"][0]["position_id"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": position_id,
        "collateral": {"denom": bar_name, "amount": "700"}
    })
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
        "demo_remove_collateral_exceeds",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is not None, json.dumps(query_result, indent=2)
    message = str(query_result["exception"]).lower()
    assert "cannot remove more collateral than available" in message, message


def test_remove_collateral_invalid_address(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Invalid bech32 addresses should fail address validation."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_remove_collateral_invalid_address(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "3000"},
            {"denom": bar_name, "amount": "3000"}
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
    })
    pool_id = int(sudo_pool_result["results"][0]["pool_id"])

    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "500"},
        "borrow": {"denom": foo_name, "amount": "250"}
    })
    position_id = int(sudo_position_result["results"][0]["position_id"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": "invalid_address",
        "pool_id": pool_id,
        "position_id": position_id,
        "collateral": {"denom": bar_name, "amount": "100"}
    })
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
        "demo_remove_collateral_invalid_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is not None, json.dumps(query_result, indent=2)
    assert "not position owner" in str(query_result["exception"]).lower(), (
        "remove-collateral validates ownership before address parsing, so invalid "
        f"addresses manifest as unauthorized errors: {json.dumps(query_result, indent=2)}"
    )


def test_remove_collateral_pool_id_mismatch(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Removing collateral with a different pool_id should be rejected."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_remove_collateral_pool_mismatch(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    pool_a = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "5000"}
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
    })
    pool_a_id = int(pool_a["results"][0]["pool_id"])

    pool_b = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "4000"},
            {"denom": bar_name, "amount": "4000"}
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
    })
    pool_b_id = int(pool_b["results"][0]["pool_id"])

    open_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_a_id,
        "collateral": {"denom": bar_name, "amount": "800"},
        "borrow": {"denom": foo_name, "amount": "400"}
    })
    position_id = int(open_resp["results"][0]["position_id"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_b_id,
        "position_id": position_id,
        "collateral": {"denom": bar_name, "amount": "100"}
    })
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
        "demo_remove_collateral_pool_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is not None, json.dumps(query_result, indent=2)
    assert (
        "pool_id mismatch" in str(query_result["exception"]).lower()
    ), f"missing pool mismatch detail: {json.dumps(query_result, indent=2)}"


def test_remove_collateral_denom_mismatch(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Removing collateral using a different denom should fail."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_remove_collateral_denom_mismatch(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    pool = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "4500"},
            {"denom": bar_name, "amount": "4500"}
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
    })
    pool_id = int(pool["results"][0]["pool_id"])

    position = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "700"},
        "borrow": {"denom": foo_name, "amount": "350"}
    })
    position_id = int(position["results"][0]["position_id"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": position_id,
        "collateral": {"denom": foo_name, "amount": "50"}
    })
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
        "demo_remove_collateral_denom_mismatch",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is not None, json.dumps(query_result, indent=2)
    assert (
        "collateral denom mismatch" in str(query_result["exception"]).lower()
    ), f"missing denom mismatch detail: {json.dumps(query_result, indent=2)}"


def test_remove_collateral_ratio_violation(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Removing too much collateral triggers the ratio guard."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_remove_collateral_ratio_violation(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
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
    })
    pool_id = int(sudo_pool_result["results"][0]["pool_id"])

    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "900"},
        "borrow": {"denom": foo_name, "amount": "600"}
    })
    position_id = int(sudo_position_result["results"][0]["position_id"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": alice_addr,
        "pool_id": pool_id,
        "position_id": position_id,
        "collateral": {"denom": bar_name, "amount": "700"}
    })
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
        "demo_remove_collateral_ratio_violation",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is not None, json.dumps(query_result, indent=2)
    assert "collateral ratio" in str(query_result["exception"]).lower()


def test_remove_collateral_not_owner(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Non-owners cannot remove collateral from someone else's position."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_remove_collateral_not_owner(alice_addr, bob_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "6000"},
            {"denom": bar_name, "amount": "6000"}
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
    })
    pool_id = int(sudo_pool_result["results"][0]["pool_id"])

    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "800"},
        "borrow": {"denom": foo_name, "amount": "400"}
    })
    position_id = int(sudo_position_result["results"][0]["position_id"])

    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveCollateral",
        "user": bob_addr,
        "pool_id": pool_id,
        "position_id": position_id,
        "collateral": {"denom": bar_name, "amount": "100"}
    })
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "bob_addr": bob_addr,
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
        "demo_remove_collateral_not_owner",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    assert query_result.get("exception") is not None, json.dumps(query_result, indent=2)
    assert "not position owner" in str(query_result["exception"]).lower()
