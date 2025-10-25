import json
from tests.utils import poll_until_condition


def test_dyslang_subscription_flow(chainnet, generate_account, faucet):
    dysond = chainnet[0]

    [name, addr] = generate_account("dys_sub")
    faucet(addr, amount=1_000_000)

    # Ensure sufficient delegated stake for subscriptions
    vals = dysond("query", "staking", "validators")
    valopers = vals.get("validators", [])
    assert valopers, f"no validators: {vals}"
    valoper = valopers[0].get("operator_address") or valopers[0].get("operatorAddress")
    assert valoper, f"missing operator_address: {valopers[0]}"
    del_tx = dysond(
        "tx",
        "staking",
        "delegate",
        valoper,
        "2000udys",
        "--from",
        name,
        "--yes",
        )
    assert del_tx.get("code", 1) == 0, f"delegate failed: {del_tx}"

    # Emitter (keep show defined; update script to include both functions)
    emit_code = """
from dys import emit_event
import json

def show(event=None):
    print(f"event: {event}")
    v = event and event.get("attributes", {}).get("value")
    return {"value": v}

def go():
    emit_event("alpha", json.dumps({"foo": "bar"}))
    return True
"""
    up2 = dysond(
        "tx",
        "script",
        "update",
        "--code",
        emit_code,
        "--from",
        name,
        "--yes",
         )
    assert up2.get("code", 1) == 0

    # Subscribe to type alpha
    sub = dysond(
        "tx",
        "crontask",
        "create-subscription",
        "--filter",
        '#(attributes.value.foo=="bar")',
        "--script-address",
        addr,
        "--function",
        "show",
        "--args",
        "[]",
        "--kwargs",
        "{}",
        "--task-gas-limit",
        "1500000",
        "--task-gas-fee",
        "1udys",
        "--from",
        name,
        "--yes",
    )
    assert sub.get("code", 1) == 0, f"create subscription failed: {sub}"

    # Extract subscription_id from events and assert status is not "error"
    sub_events = [
        e
        for e in sub.get("events", [])
        if e.get("type") == "dysonprotocol.crontask.v1.EventSubscriptionCreated"
    ]
    sub_id_attrs = [
        a
        for e in sub_events
        for a in e.get("attributes", [])
        if a.get("key") == "subscription_id"
    ]
    assert (
        sub_id_attrs
    ), f"No subscription_id attribute found in events: {json.dumps(sub.get('events', []), indent=2)}"
    sub_id = json.loads(sub_id_attrs[0].get("value"))
    subq = dysond(
        "query", "crontask", "subscription-by-id", "--subscription-id", str(sub_id)
    )
    assert isinstance(subq, dict) and subq.get(
        "subscription"
    ), f"invalid subscription query response: {subq}"
    sub_status = subq.get("subscription", {}).get("status")
    assert (
        sub_status != "error"
    ), f"subscription entered error state: {json.dumps(subq, indent=2)}"

    # Emit once
    ex = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        addr,
        "--function-name",
        "go",
        "--from",
        name,
         )
    assert ex.get("code", 1) == 0

    # Wait until exactly one task exists for this creator
    def _exactly_one():
        res = dysond("query", "crontask", "tasks-by-address", "--creator", addr)
        tasks = res.get("tasks", [])
        return len(tasks) == 1

    poll_until_condition(
        _exactly_one,
        timeout=10,
        poll_interval=0.2,
        error_message="did not observe exactly one task for creator",
    )

    # Wait until the single task is DONE
    def _only_done():
        res = dysond("query", "crontask", "tasks-by-address", "--creator", addr)
        tasks = res.get("tasks", [])
        only = (len(tasks) == 1 and tasks[0]) or {}
        assert only.get("status") != "FAILED", f"task failed: {only}"
        return only.get("status") == "DONE"

    poll_until_condition(
        _only_done,
        timeout=10,
        poll_interval=0.2,
        error_message="task did not reach DONE",
    )

    # Assert the task contains kwargs.event with value == "1"
    res = dysond("query", "crontask", "tasks-by-address", "--creator", addr)
    tasks = res.get("tasks", [])
    assert (
        len(tasks) == 1
    ), f"expected exactly one task, got {len(tasks)}: {json.dumps(tasks, indent=2)}"
    latest = tasks[0]
    msgs = latest.get("msgs", [])
    assert msgs, f"task missing msgs: {latest}"
    m0 = msgs[0]
    # kwargs may be nested under value.kwargs or at top-level depending on Any JSON
    kwargs_str = (
        (m0.get("value", {}) and m0.get("value", {}).get("kwargs"))
        or m0.get("kwargs")
        or "{}"
    )
    parsed = json.loads(kwargs_str)
    event_val = parsed.get("event", {}).get("attributes", {}).get("value")
    assert (
        isinstance(event_val, dict) and event_val.get("foo") == "bar"
    ), f"expected event value.foo == 'bar', got: {event_val} in {parsed}"
