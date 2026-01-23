#!/usr/bin/env python3
"""
Tests for ScriptExecAuthorization.Accept with attached message grants.
Each test exercises a single Accept path via authz exec.
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone

from tests.conftest import dedent


def _create_script(dysond, alice_name):
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
    assert (
        create_events
    ), f"No EventCreateNewScript found: {json.dumps(create_result, indent=2)}"
    address_attrs = [
        a
        for a in create_events[0].get("attributes", [])
        if a.get("key") == "script_address"
    ]
    assert (
        address_attrs
    ), f"No script_address attribute found: {json.dumps(create_events[0], indent=2)}"
    script_address = json.loads(address_attrs[0]["value"])
    return script_address


def _submit_script_exec_grant_with_attached_authz(
    dysond, alice_name, alice_addr, bob_addr, script_address, spend_limit
):
    expiration = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    grant_msg = {
        "@type": "/cosmos.authz.v1beta1.MsgGrant",
        "granter": alice_addr,
        "grantee": bob_addr,
        "grant": {
            "authorization": {
                "@type": "/dysonprotocol.script.v1.ScriptExecAuthorization",
                "script_address": script_address,
                "function_names": ["noop"],
                "attached_msg_authorizations": [
                    {
                        "@type": "/cosmos.bank.v1beta1.SendAuthorization",
                        "spend_limit": [{"denom": "udys", "amount": str(spend_limit)}],
                    }
                ],
            },
            "expiration": expiration,
        },
    }
    grant_result = dysond(
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
        json.dumps(grant_msg),
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert grant_result.get("code", 1) == 0, (
        f"Grant tx failed. Code: {grant_result.get('code')}, "
        f"Raw log: {grant_result.get('raw_log')}, Full: {json.dumps(grant_result, indent=2)}"
    )
    return grant_msg


def _get_udys_balance(dysond, address):
    balances = dysond("query", "bank", "balances", address)
    coins = balances.get("balances", [])
    assert isinstance(
        coins, list
    ), f"balances should be list: {json.dumps(balances, indent=2)}"
    udys = [c for c in coins if c.get("denom") == "udys"]
    assert udys, f"udys balance missing: {json.dumps(balances, indent=2)}"
    amount = udys[0].get("amount")
    assert isinstance(
        amount, str
    ), f"udys amount should be string: {json.dumps(udys[0], indent=2)}"
    return int(amount)


def _get_script_exec_grant(grants_result):
    grants = grants_result.get("grants", [])
    assert isinstance(
        grants, list
    ), f"grants should be list: {json.dumps(grants_result, indent=2)}"
    matching = [
        g
        for g in grants
        if g.get("authorization", {}).get("type")
        == "/dysonprotocol.script.v1.ScriptExecAuthorization"
        or g.get("authorization", {}).get("@type")
        == "/dysonprotocol.script.v1.ScriptExecAuthorization"
    ]
    assert (
        matching
    ), f"ScriptExecAuthorization not found: {json.dumps(grants_result, indent=2)}"
    return matching[0]


def _get_send_auth_from_grant(exec_grant):
    auth_value = exec_grant.get("authorization", {}).get("value", {})
    attached_auths = auth_value.get("attached_msg_authorizations", [])
    assert isinstance(
        attached_auths, list
    ), f"attached_msg_authorizations should be list: {json.dumps(auth_value, indent=2)}"
    send_auths = [
        a
        for a in attached_auths
        if a.get("type") == "/cosmos.bank.v1beta1.SendAuthorization"
        or a.get("@type") == "/cosmos.bank.v1beta1.SendAuthorization"
    ]
    assert (
        send_auths
    ), f"SendAuthorization not found: {json.dumps(attached_auths, indent=2)}"
    return send_auths[0]


def test_script_exec_authz_accept_attached_send_updates_grant(
    chainnet, generate_account, faucet
):
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("alice")
    bob_name, bob_addr = generate_account("bob")
    _, charlie_addr = generate_account("charlie")
    faucet(alice_addr, denom="udys", amount="100000")
    faucet(bob_addr, denom="udys", amount="10000")
    faucet(charlie_addr, denom="udys", amount="1")

    script_address = _create_script(dysond, alice_name)
    _submit_script_exec_grant_with_attached_authz(
        dysond, alice_name, alice_addr, bob_addr, script_address, spend_limit=50
    )

    balances_before = _get_udys_balance(dysond, charlie_addr)

    exec_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": alice_addr,
        "script_address": script_address,
        "function_name": "noop",
        "args": "[]",
        "kwargs": "{}",
        "attached_messages": [
            {
                "@type": "/cosmos.bank.v1beta1.MsgSend",
                "from_address": alice_addr,
                "to_address": charlie_addr,
                "amount": [{"denom": "udys", "amount": "10"}],
            }
        ],
    }
    tx_body = {"body": {"messages": [exec_msg]}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()
        exec_result = dysond(
            "tx",
            "authz",
            "exec",
            tx_file.name,
            "--from",
            bob_name,
            "--keyring-backend",
            "test",
            "--yes",
        )
    assert exec_result.get("code", 1) == 0, (
        f"Authz exec failed. Code: {exec_result.get('code')}, "
        f"Raw log: {exec_result.get('raw_log')}, Full: {json.dumps(exec_result, indent=2)}"
    )

    balances_after = _get_udys_balance(dysond, charlie_addr)
    assert (
        balances_after == balances_before + 10
    ), f"Charli balance mismatch. Before: {balances_before}, After: {balances_after}"

    grants_result = dysond("query", "authz", "grants", alice_addr, bob_addr)
    exec_grant = _get_script_exec_grant(grants_result)
    send_auth = _get_send_auth_from_grant(exec_grant)
    send_value = send_auth.get("value", {})
    spend_limit = send_value.get("spend_limit", [])
    assert isinstance(
        spend_limit, list
    ), f"spend_limit should be list: {json.dumps(send_value, indent=2)}"
    udys_limit = [c for c in spend_limit if c.get("denom") == "udys"]
    assert udys_limit, f"udys spend_limit missing: {json.dumps(spend_limit, indent=2)}"
    assert (
        udys_limit[0].get("amount") == "40"
    ), f"Spend limit not updated to 40. Full: {json.dumps(send_value, indent=2)}"


def test_script_exec_authz_accept_attached_send_missing_grant_fails(
    chainnet, generate_account, faucet
):
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("alice")
    bob_name, bob_addr = generate_account("bob")
    _, charlie_addr = generate_account("charlie")
    faucet(alice_addr, denom="udys", amount="100000")
    faucet(bob_addr, denom="udys", amount="10000")
    faucet(charlie_addr, denom="udys", amount="1")

    script_address = _create_script(dysond, alice_name)
    expiration = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    grant_msg = {
        "@type": "/cosmos.authz.v1beta1.MsgGrant",
        "granter": alice_addr,
        "grantee": bob_addr,
        "grant": {
            "authorization": {
                "@type": "/dysonprotocol.script.v1.ScriptExecAuthorization",
                "script_address": script_address,
                "function_names": ["noop"],
            },
            "expiration": expiration,
        },
    }
    grant_result = dysond(
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
        json.dumps(grant_msg),
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert grant_result.get("code", 1) == 0, (
        f"Grant tx failed. Code: {grant_result.get('code')}, "
        f"Raw log: {grant_result.get('raw_log')}, Full: {json.dumps(grant_result, indent=2)}"
    )

    exec_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": alice_addr,
        "script_address": script_address,
        "function_name": "noop",
        "args": "[]",
        "kwargs": "{}",
        "attached_messages": [
            {
                "@type": "/cosmos.bank.v1beta1.MsgSend",
                "from_address": alice_addr,
                "to_address": charlie_addr,
                "amount": [{"denom": "udys", "amount": "10"}],
            }
        ],
    }
    tx_body = {"body": {"messages": [exec_msg]}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()
        exec_result = dysond(
            "tx",
            "authz",
            "exec",
            tx_file.name,
            "--from",
            bob_name,
            "--keyring-backend",
            "test",
            "--yes",
        )
    assert (
        exec_result.get("code", 0) != 0
    ), f"Expected authz exec to fail. Full: {json.dumps(exec_result, indent=2)}"


def test_script_exec_authz_accept_attached_send_wrong_signer_fails(
    chainnet, generate_account, faucet
):
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("alice")
    bob_name, bob_addr = generate_account("bob")
    _, charlie_addr = generate_account("charlie")
    faucet(alice_addr, denom="udys", amount="100000")
    faucet(bob_addr, denom="udys", amount="10000")
    faucet(charlie_addr, denom="udys", amount="1")

    script_address = _create_script(dysond, alice_name)
    _submit_script_exec_grant_with_attached_authz(
        dysond, alice_name, alice_addr, bob_addr, script_address, spend_limit=50
    )

    exec_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": alice_addr,
        "script_address": script_address,
        "function_name": "noop",
        "args": "[]",
        "kwargs": "{}",
        "attached_messages": [
            {
                "@type": "/cosmos.bank.v1beta1.MsgSend",
                "from_address": bob_addr,
                "to_address": charlie_addr,
                "amount": [{"denom": "udys", "amount": "10"}],
            }
        ],
    }
    tx_body = {"body": {"messages": [exec_msg]}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as tx_file:
        json.dump(tx_body, tx_file)
        tx_file.flush()
        exec_result = dysond(
            "tx",
            "authz",
            "exec",
            tx_file.name,
            "--from",
            bob_name,
            "--keyring-backend",
            "test",
            "--yes",
        )
    assert (
        exec_result.get("code", 0) != 0
    ), f"Expected authz exec to fail for wrong signer. Full: {json.dumps(exec_result, indent=2)}"
