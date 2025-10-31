"""
Finalize liquidation happy path and failure scenarios.

These tests exercise keeper logic by creating real pools/positions via CLI,
initializing liquidation through script execution, and finalizing it after the
required block delay. They also verify error handling for premature or missing
initialization attempts.
"""

import json

from utils import extract_script_result, poll_until_condition


SCRIPT_CODE = """
from dys import _msg


def initialize_liquidation(position_id, pool_id, initializer, user):
    _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": initializer,
        "user": user,
        "pool_id": int(pool_id),
        "position_id": int(position_id)
    })
    return {"status": "initialized"}


def finalize_liquidation(position_id, pool_id, liquidator, user):
    _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgFinalizeLiquidation",
        "liquidator": liquidator,
        "user": user,
        "pool_id": int(pool_id),
        "position_id": int(position_id)
    })
    return {"status": "finalized"}


def initialize_and_finalize_same_block(position_id, pool_id, liquidator, user):
    _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgInitializeLiquidation",
        "initializer": liquidator,
        "user": user,
        "pool_id": int(pool_id),
        "position_id": int(position_id)
    })
    return _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgFinalizeLiquidation",
        "liquidator": liquidator,
        "user": user,
        "pool_id": int(pool_id),
        "position_id": int(position_id)
    })


def finalize_without_init(position_id, pool_id, liquidator, user):
    _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgFinalizeLiquidation",
        "liquidator": liquidator,
        "user": user,
        "pool_id": int(pool_id),
        "position_id": int(position_id)
    })
    return {"status": "attempted"}
"""


def _deploy_liquidation_script(dysond, script_owner_name):
    update_tx = dysond(
        "tx",
        "script",
        "update",
        "--code",
        SCRIPT_CODE,
        "--from",
        script_owner_name,
    )
    assert (
        update_tx.get("code", 1) == 0
    ), f"Script update failed: {json.dumps(update_tx, indent=2)}"


def _create_pool_and_open_position(dysond, alice_name, foo, bar):
    pool_tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo}",
        "--coins",
        f"10000{bar}",
        "--min-collateral-ratio",
        "1.05",
        "--max-leverage-ratio",
        "5.0",
        "--max-borrow-percent",
        "0.8",
        "--liquidation-threshold",
        "1.2",
        "--from",
        alice_name,
    )
    assert (
        pool_tx.get("code", 1) == 0
    ), f"Pool creation failed: {json.dumps(pool_tx, indent=2)}"

    pool_id = [
        attr.get("value").strip('"')
        for event in pool_tx.get("events", [])
        for attr in event.get("attributes", [])
        if event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
        and attr.get("key") == "pool_id"
    ][0]

    open_tx = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"110{bar}",
        "--borrow",
        f"100{foo}",
        "--from",
        alice_name,
    )
    assert (
        open_tx.get("code", 1) == 0
    ), f"Open position failed: {json.dumps(open_tx, indent=2)}"

    position_id = [
        attr.get("value").strip('"')
        for event in open_tx.get("events", [])
        for attr in event.get("attributes", [])
        if event.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
        and attr.get("key") == "position_id"
    ][0]

    return pool_id, position_id


def test_finalize_liquidation_success(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_name = leverage_accounts["bob"]["name"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo = leverage_names_and_coins["foo_name"]
    bar = leverage_names_and_coins["bar_name"]

    pool_id, position_id = _create_pool_and_open_position(dysond, alice_name, foo, bar)
    _deploy_liquidation_script(dysond, bob_name)

    init_exec = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        bob_addr,
        "--function-name",
        "initialize_liquidation",
        "--kwargs",
        json.dumps(
            {
                "position_id": position_id,
                "pool_id": pool_id,
                "initializer": bob_addr,
                "user": alice_addr,
            }
        ),
        "--from",
        bob_name,
    )
    assert (
        init_exec.get("code", 1) == 0
    ), f"Initialize liquidation failed: {json.dumps(init_exec, indent=2)}"

    init_tx = dysond("query", "wait-tx", init_exec["txhash"])
    init_result = extract_script_result(init_tx)
    assert (
        init_result["status"] == "initialized"
    ), f"Unexpected script status: {json.dumps(init_result, indent=2)}"

    init_attrs = [
        (attr.get("key"), attr.get("value"))
        for event in init_tx.get("events", [])
        if event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeverageLiquidationInitialized"
        for attr in event.get("attributes", [])
    ]
    init_map = {key: value.strip('"') for key, value in init_attrs}

    assert (
        init_map["collateral_ratio"] == "1.100000000000000000"
    ), f"Unexpected collateral ratio: {json.dumps(init_map, indent=2)}"
    assert (
        init_map["liquidation_threshold"] == "1.200000000000000000"
    ), f"Unexpected liquidation threshold: {json.dumps(init_map, indent=2)}"

    status_before = dysond("status")
    init_height = int(status_before["sync_info"]["latest_block_height"])
    target_height = init_height + 1

    poll_until_condition(
        lambda: int(dysond("status")["sync_info"]["latest_block_height"])
        >= target_height,
        timeout=5,
        poll_interval=0.1,
        error_message=f"Failed to advance block height to {target_height}",
    )

    finalize_exec = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        bob_addr,
        "--function-name",
        "finalize_liquidation",
        "--kwargs",
        json.dumps(
            {
                "position_id": position_id,
                "pool_id": pool_id,
                "liquidator": bob_addr,
                "user": alice_addr,
            }
        ),
        "--from",
        bob_name,
    )
    assert (
        finalize_exec.get("code", 1) == 0
    ), f"Finalize liquidation failed: {json.dumps(finalize_exec, indent=2)}"

    finalize_tx = dysond("query", "wait-tx", finalize_exec["txhash"])
    finalize_result = extract_script_result(finalize_tx)
    assert (
        finalize_result["status"] == "finalized"
    ), f"Unexpected finalize status: {json.dumps(finalize_result, indent=2)}"

    finalize_attrs = [
        (attr.get("key"), attr.get("value"))
        for event in finalize_tx.get("events", [])
        if event.get("type")
        == "dysonprotocol.whaleswap.v1.EventLeverageLiquidationFinalized"
        for attr in event.get("attributes", [])
    ]
    finalize_map = {key: value.strip('"') for key, value in finalize_attrs}

    collateral = json.loads(finalize_map["collateral_received"])
    repayment = json.loads(finalize_map["repayment_amount"])
    accrued_interest = json.loads(finalize_map["accrued_interest"])

    assert (
        collateral["denom"] == bar
    ), f"Collateral denom mismatch: {json.dumps(collateral, indent=2)}"
    assert (
        collateral["amount"] == "110"
    ), f"Collateral amount mismatch: {json.dumps(collateral, indent=2)}"
    assert (
        repayment["denom"] == foo
    ), f"Repayment denom mismatch: {json.dumps(repayment, indent=2)}"
    assert (
        repayment["amount"] == "100"
    ), f"Repayment amount mismatch: {json.dumps(repayment, indent=2)}"
    assert (
        accrued_interest["amount"] == "0"
    ), f"Interest should be zero: {json.dumps(accrued_interest, indent=2)}"


def test_finalize_liquidation_requires_initialization(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_name = leverage_accounts["bob"]["name"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo = leverage_names_and_coins["foo_name"]
    bar = leverage_names_and_coins["bar_name"]

    pool_id, position_id = _create_pool_and_open_position(dysond, alice_name, foo, bar)
    _deploy_liquidation_script(dysond, bob_name)

    finalize_exec = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        bob_addr,
        "--function-name",
        "finalize_without_init",
        "--kwargs",
        json.dumps(
            {
                "position_id": position_id,
                "pool_id": pool_id,
                "liquidator": bob_addr,
                "user": alice_addr,
            }
        ),
        "--from",
        bob_name,
    )
    assert (
        finalize_exec.get("code", 0) != 0
    ), f"Finalize without initialization unexpectedly succeeded: {json.dumps(finalize_exec, indent=2)}"

    tx_info = dysond("query", "wait-tx", finalize_exec["txhash"])
    assert "liquidation not initialized" in tx_info.get(
        "raw_log", ""
    ), f"Expected missing initialization error: {json.dumps(tx_info, indent=2)}"


def test_finalize_liquidation_block_delay_enforced(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_name = leverage_accounts["bob"]["name"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo = leverage_names_and_coins["foo_name"]
    bar = leverage_names_and_coins["bar_name"]

    pool_id, position_id = _create_pool_and_open_position(dysond, alice_name, foo, bar)
    _deploy_liquidation_script(dysond, bob_name)

    combined_exec = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        bob_addr,
        "--function-name",
        "initialize_and_finalize_same_block",
        "--kwargs",
        json.dumps(
            {
                "position_id": position_id,
                "pool_id": pool_id,
                "liquidator": bob_addr,
                "user": alice_addr,
            }
        ),
        "--from",
        bob_name,
    )
    assert (
        combined_exec.get("code", 0) != 0
    ), f"Finalize in same block unexpectedly succeeded: {json.dumps(combined_exec, indent=2)}"

    combined_info = dysond("query", "wait-tx", combined_exec["txhash"])
    assert "liquidation block delay not passed" in combined_info.get(
        "raw_log", ""
    ), f"Expected block delay error: {json.dumps(combined_info, indent=2)}"
