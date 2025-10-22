"""
Whaleswap execution script - runs inside dyslang sandbox.

This script executes message sequences using MsgSudo and captures
comprehensive state before/after for invariant checking.

All setup (name registration, pool creation, etc.) happens here.
"""

from dys import _msg, _query, get_executor_address
import json


def query_account_balance(address, denom):
    """Query account balance for a denom."""
    result = _query(
        {
            "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
            "address": address,
            "denom": denom,
        }
    )
    return int(result.get("balance", {}).get("amount", "0"))


def capture_balances(denoms, accounts):
    """Capture account balances."""
    account_balances = {}
    for account in accounts:
        account_balances[account] = {}
        for denom in denoms:
            account_balances[account][denom] = query_account_balance(account, denom)
    return account_balances


def replace_in_dict(obj, placeholder, value):
    """
    Recursively replace placeholder strings in a dict/list structure.

    Avoids str.replace() and type() which are forbidden in dyslang.
    """
    # Handle dict
    is_dict = isinstance(obj, dict)
    is_list = isinstance(obj, list)
    is_str = isinstance(obj, str)

    # For dict, recurse on values
    new_dict = {}
    assert not is_dict or len(obj) >= 0
    for k in obj.keys() if is_dict else []:
        new_dict[k] = replace_in_dict(obj[k], placeholder, value)

    # For list, recurse on items
    new_list = [
        replace_in_dict(item, placeholder, value) for item in (obj if is_list else [])
    ]

    # For string, check if it matches placeholder exactly
    result = obj
    result = new_dict if is_dict else result
    result = new_list if is_list else result
    result = value if (is_str and obj == placeholder) else result

    return result


def process_messages(messages):
    """
    Process messages, computing hashes where needed.

    Handles special _compute_hash directives for nameservice registration.
    """
    processed = []
    computed_hash = None

    for msg in messages:
        # Handle hash computation directive
        if "_compute_hash" in msg:
            params = msg["_compute_hash"]
            hash_result = _query(
                {
                    "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
                    "name": params["name"],
                    "salt": params["salt"],
                    "committer": params["committer"],
                }
            )
            computed_hash = hash_result["hex_hash"]
            continue

        # Replace {COMPUTED_HASH} placeholder (without str.replace)
        processed_msg = replace_in_dict(
            msg,
            "{COMPUTED_HASH}",
            computed_hash if computed_hash else "{COMPUTED_HASH}",
        )
        processed.append(processed_msg)

    return processed


def execute_messages_with_sudo(messages, denoms, accounts, authority):
    """
    Execute a sequence of messages using MsgSudo.

    Args:
        messages: List of message dicts (includes setup + test operations)
        denoms: List of denoms to track
        accounts: List of account addresses to track
        authority: Authority address (gov module address)

    Returns:
        {
            "success": bool,
            "pre_balances": {...},
            "post_balances": {...},
            "message_count": int
        }
    """
    # Process messages (compute hashes, replace placeholders)
    processed_messages = process_messages(messages)

    # Capture pre-state
    pre_balances = capture_balances(denoms, accounts)

    # Execute all messages in a single MsgSudo for atomicity
    sudo_msg = {
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": authority,
        "messages": processed_messages,
    }

    result = _msg(sudo_msg)

    # Capture post-state
    post_balances = capture_balances(denoms, accounts)

    return {
        "success": True,
        "pre_balances": pre_balances,
        "post_balances": post_balances,
        "message_count": len(processed_messages),
        "sudo_result": result,
    }
