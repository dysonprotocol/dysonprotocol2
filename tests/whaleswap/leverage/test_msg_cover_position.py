import json


def test_cover_position_partial_reduce_principal(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    foo = leverage_names_and_coins["foo_name"]
    bar = leverage_names_and_coins["bar_name"]

    # Create pool (defaults for APR are acceptable)
    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{foo}",
        "--coins",
        f"10000{bar}",
        "--fee-rate",
        f"0.003{foo}",
        "--fee-rate",
        f"0.003{bar}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        alice_name,
    )
    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"
    pool_id = [
        a.get("value")
        for e in pool_result.get("events", [])
        for a in e.get("attributes", [])
        if a.get("key") == "pool_id"
        and e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ][0].strip('"')

    # Open position: borrow 500 foo, collateral 800 foo (held will be bar)
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"800{foo}",
        "--borrow",
        f"500{foo}",
        "--from",
        alice_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"
    position_id = [
        a.get("value")
        for e in open_result.get("events", [])
        for a in e.get("attributes", [])
        if a.get("key") == "position_id"
        and e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ][0].strip('"')

    # Partially cover: pay 100 foo (>= interest, reduce principal)
    cover_result = dysond(
        "tx",
        "whaleswap",
        "cover-position",
        "--position-id",
        position_id,
        "--payment",
        f"100{foo}",
        "--from",
        alice_name,
    )
    assert cover_result.get("code", 1) == 0, f"Cover failed: {cover_result}"

    cover_events = [
        e
        for e in cover_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionCovered"
    ]
    assert len(cover_events) == 1, "EventLeveragePositionCovered not found"
    attrs = {
        a.get("key"): a.get("value", "").strip('"')
        for a in cover_events[0].get("attributes", [])
    }
    assert "closed" in attrs, f"closed attr missing: {attrs}"
    assert (
        attrs.get("closed") == "false"
    ), f"Expected closed=false for partial cover, got: {attrs.get('closed')}"
    assert "interest_paid" in attrs, f"interest_paid missing: {attrs}"
    assert "principal_paid" in attrs, f"principal_paid missing: {attrs}"


def test_cover_position_overpay_autoclose_refund(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    dysond = chainnet[0]
    bob_name = leverage_accounts["bob"]["name"]
    bob_addr = leverage_accounts["bob"]["addr"]
    foo = leverage_names_and_coins["foo_name"]
    bar = leverage_names_and_coins["bar_name"]

    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"12000{foo}",
        "--coins",
        f"12000{bar}",
        "--fee-rate",
        f"0.003{foo}",
        "--fee-rate",
        f"0.003{bar}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        bob_name,
    )
    assert pool_result.get("code", 1) == 0, f"Pool creation failed: {pool_result}"
    pool_id = [
        a.get("value")
        for e in pool_result.get("events", [])
        for a in e.get("attributes", [])
        if a.get("key") == "pool_id"
        and e.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated"
    ][0].strip('"')

    # Open position: borrow 300 foo, collateral 500 foo
    borrow_amt = 300
    open_result = dysond(
        "tx",
        "whaleswap",
        "open-position",
        "--pool-id",
        pool_id,
        "--collateral",
        f"500{foo}",
        "--borrow",
        f"{borrow_amt}{foo}",
        "--from",
        bob_name,
    )
    assert open_result.get("code", 1) == 0, f"Open position failed: {open_result}"
    position_id = [
        a.get("value")
        for e in open_result.get("events", [])
        for a in e.get("attributes", [])
        if a.get("key") == "position_id"
        and e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionOpened"
    ][0].strip('"')

    # Overpay: payment == borrow_amt + 50 (refund 50 expected), auto-close
    extra = 50
    cover_result = dysond(
        "tx",
        "whaleswap",
        "cover-position",
        "--position-id",
        position_id,
        "--payment",
        f"{borrow_amt + extra}{foo}",
        "--from",
        bob_name,
    )
    assert cover_result.get("code", 1) == 0, f"Cover failed: {cover_result}"

    # Covered event shows closed=true and refunded
    cover_events = [
        e
        for e in cover_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionCovered"
    ]
    assert len(cover_events) == 1, "EventLeveragePositionCovered not found"
    attrs = {
        a.get("key"): a.get("value", "").strip('"')
        for a in cover_events[0].get("attributes", [])
    }
    assert (
        attrs.get("closed") == "true"
    ), f"Expected closed=true, got: {attrs.get('closed')}"
    assert "refunded" in attrs, f"refunded missing: {attrs}"
    assert foo in attrs.get(
        "refunded", ""
    ), f"Refund denom mismatch: {attrs.get('refunded')}"

    # Also expect standard close event
    close_events = [
        e
        for e in cover_result.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventLeveragePositionClosed"
    ]
    assert (
        len(close_events) == 1
    ), "EventLeveragePositionClosed not emitted on overpay close"


def test_cover_position_overpay_block_delay_enforced(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    dysond = chainnet[0]
    gov = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]
    alice = leverage_accounts["alice"]["addr"]
    foo = leverage_names_and_coins["foo_name"]
    bar = leverage_names_and_coins["bar_name"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_cover_block_delay(alice, foo, bar):
    pool = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice,
        "coins": [
            {"denom": foo, "amount": "500"},
            {"denom": bar, "amount": "500"}
        ],
        "fee_rate": [
            {"denom": foo, "amount": "0.003"},
            {"denom": bar, "amount": "0.003"}
        ],
        "interest_rate": [
            {"denom": foo, "amount": "0.05"},
            {"denom": bar, "amount": "0.05"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": foo, "amount": "1.5"},
            {"denom": bar, "amount": "1.5"}
        ],
        "liquidation_threshold": [
            {"denom": foo, "amount": "1.2"},
            {"denom": bar, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": foo, "amount": "0.8"},
            {"denom": bar, "amount": "0.8"}
        ]
    })
    pool_id = pool["results"][0]["pool_id"]

    opened = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice,
        "pool_id": pool_id,
        "collateral": {"denom": foo, "amount": "50"},
        "borrow": {"denom": foo, "amount": "20"}
    })
    pos_id = opened["results"][0]["position_id"]

    # Overpay in same block: should fail with block delay error
    _ = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCoverPosition",
        "user": alice,
        "position_id": pos_id,
        "payment": {"denom": foo, "amount": "25"}
    })

    return {"unexpected": "should have failed"}
"""

    kwargs = json.dumps({"alice": alice, "foo": foo, "bar": bar})
    res = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov,
        "--executor-address",
        gov,
        "--function-name",
        "demo_cover_block_delay",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    assert (
        "exception" in res
    ), f"Expected exception for block delay; got: {json.dumps(res, indent=2)}"
    emsg = str(res["exception"]).lower()
    assert "block" in emsg, f"Expected 'block' in error message, got: {emsg}"
    assert "locked" in emsg, f"Expected 'locked' in error message, got: {emsg}"
