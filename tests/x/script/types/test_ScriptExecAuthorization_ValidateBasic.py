#!/usr/bin/env python3
"""
Tests for ScriptExecAuthorization.ValidateBasic via MsgGrant submission.
Each test exercises a single validation failure path.
"""

import json
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
    assert create_events, f"No EventCreateNewScript found: {json.dumps(create_result, indent=2)}"
    address_attrs = [
        a for a in create_events[0].get("attributes", []) if a.get("key") == "script_address"
    ]
    assert address_attrs, f"No script_address attribute found: {json.dumps(create_events[0], indent=2)}"
    script_address = json.loads(address_attrs[0]["value"])
    return script_address


def _submit_invalid_grant(dysond, alice_name, alice_addr, bob_addr, script_address, authz_list):
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
                "attached_msg_authorizations": authz_list,
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
    return grant_result


def test_script_exec_authz_validate_basic_rejects_duplicate_msg_type(
    chainnet, generate_account, faucet
):
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("alice")
    _, bob_addr = generate_account("bob")
    faucet(alice_addr, denom="udys", amount="100000")
    faucet(bob_addr, denom="udys", amount="10000")

    script_address = _create_script(dysond, alice_name)
    authz_list = [
        {
            "@type": "/cosmos.bank.v1beta1.SendAuthorization",
            "spend_limit": [{"denom": "udys", "amount": "10"}],
        },
        {
            "@type": "/cosmos.bank.v1beta1.SendAuthorization",
            "spend_limit": [{"denom": "udys", "amount": "20"}],
        },
    ]
    grant_result = _submit_invalid_grant(
        dysond, alice_name, alice_addr, bob_addr, script_address, authz_list
    )
    assert grant_result.get("code", 0) != 0, (
        f"Expected duplicate MsgTypeURL to fail. Full: {json.dumps(grant_result, indent=2)}"
    )


def test_script_exec_authz_validate_basic_rejects_invalid_send_authorization(
    chainnet, generate_account, faucet
):
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("alice")
    _, bob_addr = generate_account("bob")
    faucet(alice_addr, denom="udys", amount="100000")
    faucet(bob_addr, denom="udys", amount="10000")

    script_address = _create_script(dysond, alice_name)
    authz_list = [
        {
            "@type": "/cosmos.bank.v1beta1.SendAuthorization",
            "spend_limit": [],
        }
    ]
    grant_result = _submit_invalid_grant(
        dysond, alice_name, alice_addr, bob_addr, script_address, authz_list
    )
    assert grant_result.get("code", 0) != 0, (
        f"Expected invalid SendAuthorization to fail. Full: {json.dumps(grant_result, indent=2)}"
    )
