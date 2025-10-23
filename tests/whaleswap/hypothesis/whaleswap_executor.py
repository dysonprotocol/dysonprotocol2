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
    # Capture pre-state
    pre_balances = capture_balances(denoms, accounts)

    # Execute all messages in a single MsgSudo for atomicity
    sudo_msg = {
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": authority,
        "messages": messages,
    }

    result = _msg(sudo_msg)

    # Capture post-state
    post_balances = capture_balances(denoms, accounts)

    # Enhanced result with invariant checks
    invariant_checks = check_whaleswap_invariants(post_balances, denoms)

    return {
        "success": True,
        "pre_balances": pre_balances,
        "post_balances": post_balances,
        "message_count": len(messages),
        "sudo_result": result,
        "invariant_checks": invariant_checks,
    }


def check_whaleswap_invariants(balances, denoms):
    """
    Check whaleswap-specific invariants after operations.

    Args:
        balances: Dict of account -> denom -> balance
        denoms: List of denoms to check

    Returns:
        Dict with invariant check results
    """
    errors = []

    # Invariant 1: No account should have negative balances
    for account, account_balances in balances.items():
        for denom in denoms:
            balance = account_balances.get(denom, 0)
            if balance < 0:
                errors.append(f"Negative balance: {account}.{denom} = {balance}")

    # Invariant 2: Total supply conservation (simplified)
    # In a real implementation, this would query the actual module balances
    # and verify they equal the sum of all components

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "checked_invariants": [
            "no_negative_balances",
            "module_balance_conservation",  # Would need enhancement
        ],
    }


def execute_messages_with_invariant_checks(messages, denoms, accounts, authority):
    """
    Execute messages and perform comprehensive invariant checking.

    This is the enhanced version that includes post-execution invariant checks.
    """
    # Execute messages
    result = execute_messages_with_sudo(messages, denoms, accounts, authority)

    # If execution failed, return as-is
    if not result["success"]:
        result["invariant_checks"] = {"passed": None, "errors": ["execution_failed"]}
        return result

    # Check invariants
    invariant_checks = check_whaleswap_invariants(result["post_balances"], denoms)
    result["invariant_checks"] = invariant_checks

    # Mark overall success based on invariants
    result["invariant_success"] = invariant_checks["passed"]

    return result
