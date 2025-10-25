import json
from tests.utils import poll_until_condition
import requests


def _get_api_host(dysond_bin):
    address = dysond_bin("config", "get", "app", "api.address", raw=True)
    host, port = address.split("//")[1].split(":")
    return f"http://{host}:{port}"


def test_rest_subscription_event_merge_and_trigger_count(
    chainnet, generate_account, faucet, api_address
):
    dysond = chainnet[0]
    base = _get_api_host(dysond)

    # Accounts
    [creator_name, creator_addr] = generate_account("rest_sub")
    faucet(creator_addr, amount=1_000_000)

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
        creator_name,
        "--yes",
    )
    assert del_tx.get("code", 1) == 0, f"delegate failed: {del_tx}"

    # Script that returns kwargs.event
    script_code = """
from dys import _msg
import json

def show_event(event=None):
    return {"event": event}
"""
    up = dysond(
        "tx",
        "script",
        "update",
        "--code",
        script_code,
        "--from",
        creator_name,
        "--yes",
    )
    assert up.get("code", 1) == 0, f"script update failed: {up}"

    # Script to emit event
    emit_code = """
from dys import emit_event
def emit_evt():
    emit_event("payment_processed", "ok")
    return True
"""
    up2 = dysond(
        "tx",
        "script",
        "update",
        "--code",
        emit_code,
        "--from",
        creator_name,
        "--yes",
    )
    assert up2.get("code", 1) == 0

    # Create subscription via REST (autocli query shows service name; tx via CLI is acceptable if REST encoding differs)
    create_sub = dysond(
        "tx",
        "crontask",
        "create-subscription",
        "--filter",
        '#(attributes.key=="payment_processed")',
        "--script-address",
        creator_addr,
        "--function",
        "show_event",
        "--args",
        "[]",
        "--kwargs",
        "{}",
        "--task-gas-limit",
        "1200000",
        "--task-gas-fee",
        "1udys",
        "--from",
        creator_name,
        "--yes",
    )
    assert create_sub.get("code", 1) == 0, f"create subscription failed: {create_sub}"

    # Emit twice to increment trigger_count two times
    for _ in range(2):
        exec_emit = dysond(
            "tx",
            "script",
            "exec",
            "--script-address",
            creator_addr,
            "--function-name",
            "emit_evt",
            "--from",
            creator_name,
        )
        assert exec_emit.get("code", 1) == 0

    # Wait for at least one scheduled task (trigger_count will still reflect both)
    def _has_one():
        res = dysond("query", "crontask", "tasks-by-address", "--creator", creator_addr)
        tasks = res.get("tasks", [])
        return any(t.get("status") in ("SCHEDULED", "PENDING", "DONE") for t in tasks)

    poll_until_condition(
        _has_one,
        timeout=12,
        poll_interval=0.2,
        error_message="Did not see a scheduled task",
    )

    # Query subscriptions by creator (REST via CLI) and assert trigger_count >= 2
    subs = dysond(
        "query", "crontask", "subscriptions-by-creator", "--creator", creator_addr
    )
    sub_list = subs.get("subscriptions", [])
    assert sub_list, f"no subscriptions found: {subs}"
    sub = sub_list[0]
    assert (
        int(sub.get("trigger_count", "0")) >= 2
    ), f"trigger_count not incremented: {json.dumps(sub, indent=2)}"

    # Verify creator-specific pagination returns at least one result and respects limit
    creator_resp = requests.get(
        f"{base}/dysonprotocol/crontask/v1/subscriptions/creator/{creator_addr}",
        params={"pagination.limit": 1, "pagination.count_total": True},
        timeout=15,
    )
    creator_resp.raise_for_status()
    creator_payload = creator_resp.json()
    creator_total = int(creator_payload["pagination"]["total"])
    assert creator_total >= 1

    # Store subscriptions in a list without using comprehensions/generators
    creator_subs = []
    idx = 0
    subs_payload = creator_payload["subscriptions"]
    while idx < len(subs_payload):
        creator_subs.append(subs_payload[idx])
        idx += 1

    assert len(creator_subs) == 1

    creator_values = []
    idx = 0
    while idx < len(creator_subs):
        creator_values.append(creator_subs[idx]["creator"])
        idx += 1

    assert creator_values[0] == creator_addr

    # Verify all-subscriptions endpoint returns total count and respects limit
    all_resp = requests.get(
        f"{base}/dysonprotocol/crontask/v1/subscriptions",
        params={"pagination.limit": 1, "pagination.count_total": True},
        timeout=15,
    )
    all_resp.raise_for_status()
    all_payload = all_resp.json()
    all_total = int(all_payload["pagination"]["total"])
    assert all_total >= creator_total

    all_subs = []
    idx = 0
    all_subs_payload = all_payload["subscriptions"]
    while idx < len(all_subs_payload):
        all_subs.append(all_subs_payload[idx])
        idx += 1

    assert len(all_subs) == 1
