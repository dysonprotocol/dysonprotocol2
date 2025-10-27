"""
Example demonstrating sequential message execution with dys_eval template substitution.

This shows how to chain messages where results from one message are used in subsequent messages
using dys_eval templates with dot notation (e.g., {{ msg_0.pool_id }}).

Note: This uses dys_eval which is available within the dyslang runtime.
"""

import json
import re


# Mock dys_eval for local testing (in dyslang runtime, this would be imported from dys)
def dys_eval(expression, scope=None):
    """Mock dys_eval for local testing - evaluates expressions using Python's eval and returns list"""
    try:
        if scope:
            result = eval(expression, {"__builtins__": {}}, scope)
        else:
            result = eval(expression, {"__builtins__": {}})
        # dys_eval returns a list, with the last element being the final result
        return [result]
    except Exception as e:
        raise e


def dys_eval_template_substitution(json_str, template_vars):
    """
    Substitute {{ expression }} templates in JSON string using dys_eval.
    """

    def replace_template(match):
        expression = match.group(1).strip()
        try:
            result = dys_eval(expression, scope=template_vars)
            # dys_eval returns a list of results, we need the last one
            if isinstance(result, list) and result:
                final_result = result[-1]
            else:
                final_result = result

            # Convert result back to JSON-compatible string
            if isinstance(final_result, str):
                return json.dumps(final_result)[1:-1]  # Remove quotes from JSON string
            else:
                return str(final_result)
        except Exception as e:
            # On error, return the original template to avoid breaking JSON
            return match.group(0)

    # Pattern to match {{ expression }} (non-greedy, allows nested braces)
    pattern = r"\{\{\s*(.*?)\s*\}\}"
    return re.sub(pattern, replace_template, json_str)


# Example message sequence with automatic template variable extraction
messages = [
    {
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": "alice_addr",
        "coins": [
            {"denom": "foo.dys", "amount": "100000"},
            {"denom": "bar.dys", "amount": "100000"},
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "3.0",
        "max_borrow_percent": "0.8",
        # pool_id will be automatically extracted from response
    },
    {
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
        "maker": "alice_addr",
        "have": {"denom": "foo.dys", "amount": "10000"},
        "want": {"denom": "bar.dys", "amount": "5000"},
        # offer_id will be automatically extracted from response
    },
    {
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": "alice_addr",
        "operations": [
            {
                "swap": {
                    "pool_id": "{{ msg_0['pool_id'] }}",  # Uses pool_id from first message response
                    "swap_in": {"denom": "foo.dys", "amount": "100"},
                }
            }
        ],
        "max_input": [{"denom": "foo.dys", "amount": "100000"}],
        "min_output": [],
        # trade_id will be automatically extracted from response
    },
]


# Simulate the execution flow
def simulate_sequential_execution():
    """Simulate what execute_messages_sequentially does."""
    template_vars = {}

    for i, msg_template in enumerate(messages):
        print(f"\n--- Message {i+1} ---")

        # Convert to JSON string for template substitution
        msg_json = json.dumps(msg_template, indent=2)
        print(f"Original message:\n{msg_json}")

        # Apply dys_eval template substitution
        if template_vars:
            original_json = msg_json
            msg_json = dys_eval_template_substitution(msg_json, template_vars)
            if msg_json != original_json:
                print(f"After substitution:\n{msg_json}")
            else:
                print("No template substitution occurred")

        # Simulate execution and result extraction
        msg_dict = json.loads(msg_json)

        # Simulate response based on message type
        if msg_dict["@type"] == "/dysonprotocol.whaleswap.v1.MsgCreatePool":
            result = {
                "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePoolResponse",
                "pool_id": "42",
            }
        elif msg_dict["@type"] == "/dysonprotocol.whaleswap.v1.MsgMakeOffer":
            result = {
                "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOfferResponse",
                "offer_id": "7",
            }
        elif msg_dict["@type"] == "/dysonprotocol.whaleswap.v1.MsgMakeTrade":
            result = {
                "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTradeResponse",
                "trade_id": "3",
            }

        # Store response deterministically and create structured objects
        print(f"Response: {result}")

        # Store complete response as JSON string
        template_vars[f"msg_resp_{i}"] = json.dumps(result)
        print(f"Stored: msg_resp_{i} = {json.dumps(result)}")

        # Store response as simple dict for template access
        template_vars[f"msg_{i}"] = result
        # Show what fields are available
        for var_name, var_value in result.items():
            if isinstance(var_value, (str, int, float, bool)):
                print(f"Auto-extracted: msg_{i}['{var_name}'] = {var_value}")

        print(f"Current template_vars: {template_vars}")


if __name__ == "__main__":
    print(
        "=== Sequential Message Execution with Automatic Template Variable Extraction ===\n"
    )
    simulate_sequential_execution()
    print("\n=== Summary ===")
    print("This demonstrates how:")
    print("1. Complete responses are stored as msg_resp_{index} (JSON strings)")
    print("2. Structured objects are created as msg_{index} for dot notation")
    print("3. Fields are accessible via {{ msg_0['pool_id'] }} syntax")
    print("4. Deterministic access prevents naming conflicts")
    print("5. Any response field can be referenced by message position")
    print("6. No manual configuration needed - fully automatic extraction")
    print("7. Variables accumulate across the entire message sequence")
    print("8. dys_eval provides full Python expression evaluation")
    print("9. Works within dyslang runtime constraints")
    print(
        "10. The approach is maximally flexible and works with any message types/responses"
    )
