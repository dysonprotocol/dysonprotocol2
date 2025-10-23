"""
Whaleswap execution script - runs inside dyslang sandbox.

This script executes message sequences using MsgSudo and captures
comprehensive state before/after for invariant checking.

All setup (name registration, pool creation, etc.) happens here.

SEQUENTIAL EXECUTION WITH DYS_EVAL TEMPLATE SUBSTITUTION:

The execute_messages_sequentially() function allows you to chain messages
where results from one message can be used in subsequent messages.

Example:
    messages = [
        {"@type": "CreatePool", ...},  # Creates pool, returns pool_id
        {
            "@type": "MakeTrade",
            "pool_id": "{{ msg_0['pool_id'] }}",  # Uses pool_id from first message response
            # ... other fields
        }
    ]

The function:
1. Executes each message individually via MsgSudo
2. Stores complete response as msg_resp_{index} (JSON string)
3. Stores response dict as msg_{index} for template access
4. Uses dys_eval to evaluate {{ python_expression }} templates within dyslang runtime
5. Accumulates variables across all messages

Available template variables:
- msg_resp_0: Complete JSON response from first message
- msg_0: Response dict from first message (use msg_0['pool_id'])
- msg_1: Response dict from second message (use msg_1['offer_id'])
- etc.

dys_eval provides full Python expression evaluation within the dyslang sandbox.
"""

from dys import _msg, _query, get_executor_address, dys_eval
import json
import re


def dys_eval_template_substitution(json_str, template_vars):
    """
    Substitute {{ expression }} templates in JSON string using dys_eval.

    Args:
        json_str: JSON string containing {{ expression }} templates
        template_vars: Dictionary of variables available to expressions

    Returns:
        JSON string with templates substituted
    """
    # Log for debugging
    print(
        f"TEMPLATE_DEBUG: Starting substitution with template_vars keys: {list(template_vars.keys())}"
    )

    def replace_template(match):
        expression = match.group(1).strip()
        print(f"TEMPLATE_DEBUG: Evaluating expression: '{expression}'")
        print(f"TEMPLATE_DEBUG: Available vars: {template_vars}")

        try:
            result = dys_eval(expression, scope=template_vars)
            print(f"TEMPLATE_DEBUG: dys_eval result: {result}")
            if isinstance(result, list):
                final_result = result[-1]
                print(f"TEMPLATE_DEBUG: Using last element: {final_result}")
            else:
                final_result = result
            print(f"TEMPLATE_DEBUG: Final result: {final_result}")
            return str(final_result)
        except Exception as e:
            print(f"TEMPLATE_DEBUG: ERROR evaluating '{expression}': {e}")
            raise

    # Pattern to match {{ expression }} (non-greedy, allows nested braces)
    pattern = r"\{\{\s*(.*?)\s*\}\}"
    matches = re.findall(pattern, json_str)
    print(f"TEMPLATE_DEBUG: Found template matches: {matches}")

    result = re.sub(pattern, replace_template, json_str)
    print(f"TEMPLATE_DEBUG: Final substituted JSON: {result}")
    return result


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

    return {
        "success": True,
        "pre_balances": pre_balances,
        "post_balances": post_balances,
        "message_count": len(messages),
        "sudo_result": result,
    }


def execute_messages_sequentially(messages, denoms, accounts, authority):
    """
    Execute messages sequentially, using results from previous messages to substitute
    variables in subsequent messages via string templates.

    Args:
        messages: List of message dicts with potential template variables like $pool_id.
                 Messages can include an optional "_extract_vars" field specifying
                 which fields from the response should be extracted as template variables.
        denoms: List of denoms to track
        accounts: List of account addresses to track
        authority: Authority address (gov module address)

    Returns:
        {
            "success": bool,
            "pre_balances": {...},
            "post_balances": {...},
            "message_count": int,
            "message_results": [...],
            "template_vars": {...}
        }
    """
    # Capture pre-state
    pre_balances = capture_balances(denoms, accounts)

    message_results = []
    template_vars = {}

    for i, msg_template in enumerate(messages):
        print(
            f"SEQUENTIAL_DEBUG: Processing message {i}, template_vars keys: {list(template_vars.keys())}"
        )

        # Convert message to JSON string for template substitution
        msg_json = json.dumps(msg_template)
        print(f"SEQUENTIAL_DEBUG: Original message JSON: {msg_json}")

        # Apply dys_eval template substitution with accumulated variables
        if template_vars:
            msg_json = dys_eval_template_substitution(msg_json, template_vars)
        else:
            print("SEQUENTIAL_DEBUG: No template_vars available, skipping substitution")

        # Parse back to dict
        msg_dict = json.loads(msg_json)
        print(f"SEQUENTIAL_DEBUG: Final message dict: {msg_dict}")

        # Execute single message with MsgSudo
        sudo_msg = {
            "@type": "/dysonprotocol.script.v1.MsgSudo",
            "authority": authority,
            "messages": [msg_dict],
        }

        result = _msg(sudo_msg)

        # Store result for return
        message_results.append(result)

        # Store response in deterministic key for future reference
        if result and "results" in result and result["results"]:
            msg_result = result["results"][0]
            print(f"SEQUENTIAL_DEBUG: Message {i} result: {msg_result}")

            # Store complete response as JSON string
            template_vars[f"msg_resp_{i}"] = json.dumps(msg_result)

            # Store response as simple dict for template access
            template_vars[f"msg_{i}"] = msg_result

            print(
                f"SEQUENTIAL_DEBUG: Stored template_vars for msg_{i}: {template_vars[f'msg_{i}']}"
            )
        else:
            print(f"SEQUENTIAL_DEBUG: No results in response for message {i}")

    # Capture post-state
    post_balances = capture_balances(denoms, accounts)

    return {
        "success": True,
        "pre_balances": pre_balances,
        "post_balances": post_balances,
        "message_count": len(messages),
        "message_results": message_results,
        "template_vars": template_vars,
    }
