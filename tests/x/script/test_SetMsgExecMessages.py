#!/usr/bin/env python3
"""
Covers SetMsgExecMessages via tx script exec with attached messages.
"""

import json
from tests.conftest import dedent


def test_set_msg_exec_messages_via_cli(chainnet, generate_account, faucet):
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("alice")
    bob_name, bob_addr = generate_account("bob")
    faucet(alice_addr, denom="udys", amount="100000")
    faucet(bob_addr, denom="udys", amount="1")

    script_code = dedent(
        """
    def noop():
        return {"ok": True}
    """
    ).strip()
    create_result = dysond(
        "tx",
        "script",
        "create-new-script",
        "--code",
        script_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert create_result.get("code", 1) == 0, (
        f"Create script failed. Code: {create_result.get('code')}, "
        f"Raw log: {create_result.get('raw_log')}, Full: {json.dumps(create_result, indent=2)}"
    )
    create_events = [
        e
        for e in create_result.get("events", [])
        if e.get("type") == "dysonprotocol.script.v1.EventCreateNewScript"
    ]
    assert create_events, f"No EventCreateNewScript found: {json.dumps(create_result, indent=2)}"
    address_attrs = [
        a for a in create_events[0].get("attributes", []) if a.get("key") == "script_address"
    ]
    assert address_attrs, f"No script_address attribute found: {json.dumps(create_events[0], indent=2)}"
    script_address = json.loads(address_attrs[0]["value"])

    balances_before = dysond("query", "bank", "balances", bob_addr)
    coins_before = balances_before.get("balances", [])
    udys_before = [c for c in coins_before if c.get("denom") == "udys"]
    assert udys_before, f"udys balance missing: {json.dumps(balances_before, indent=2)}"
    before_amount = int(udys_before[0]["amount"])

    attached_msg = {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": bob_addr,
        "amount": [{"denom": "udys", "amount": "10"}],
    }
    exec_result = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        script_address,
        "--function-name",
        "noop",
        "--args",
        "[]",
        "--kwargs",
        "{}",
        "--attached-message",
        json.dumps(attached_msg),
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert exec_result.get("code", 1) == 0, (
        f"Exec failed. Code: {exec_result.get('code')}, "
        f"Raw log: {exec_result.get('raw_log')}, Full: {json.dumps(exec_result, indent=2)}"
    )

    balances_after = dysond("query", "bank", "balances", bob_addr)
    coins_after = balances_after.get("balances", [])
    udys_after = [c for c in coins_after if c.get("denom") == "udys"]
    assert udys_after, f"udys balance missing: {json.dumps(balances_after, indent=2)}"
    after_amount = int(udys_after[0]["amount"])
    assert after_amount == before_amount + 10, (
        f"Balance mismatch. Before: {before_amount}, After: {after_amount}"
    )
