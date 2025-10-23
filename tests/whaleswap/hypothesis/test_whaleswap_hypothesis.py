"""
Hypothesis-based property testing for whaleswap module.

Uses randomized message generation to discover edge cases and invariant violations.
All operations happen in a single dysond query script exec for speed and determinism.
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def execute_via_script(dysond, executor_script_path, gov_addr, function_name, args):
    """
    Execute a dyslang function and return parsed result.

    Uses gov address as both script and executor with --extra-code-path.
    """
    args_json = json.dumps(args)

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        function_name,
        "--args",
        args_json,
        "--extra-code-path",
        str(executor_script_path),
        "-o",
        "json",
    )

    # Parse nested JSON result
    # Handle both dict and string responses
    assert isinstance(result, dict), f"Expected dict result, got: {str(result)}"
    assert (
        "result" in result
    ), f"No 'result' key in response: {json.dumps(result, indent=2)}"
    assert (
        result["result"] is not None
    ), f"Result is None: {json.dumps(result, indent=2)}"
    outer = json.loads(result["result"])

    # Check for exception in script execution
    assert outer["exception"] is None, (
        f"Script execution failed with exception:\n"
        f"{json.dumps(outer['exception'], indent=2)}\n"
        f"Args: {args_json[:500]}"
    )

    assert outer["result"] is not None, (
        f"Script returned None result (no exception but no result):\n"
        f"Full output: {json.dumps(outer, indent=2)[:1000]}"
    )

    return outer["result"]


# ============================================================================
# MESSAGE BUILDERS
# ============================================================================


def build_setup_messages(alice_addr, foo_name, bar_name):
    """Build setup messages for whaleswap testing (pool creation and offer making).

    Names must already be registered and coins minted.
    """
    messages = []

    # Create initial pool (alice provides liquidity)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": alice_addr,
            "coins": [
                {"denom": foo_name, "amount": "100000"},
                {"denom": bar_name, "amount": "100000"},
            ],
            "fee_pct": "0.003",
        }
    )

    # Create initial offer (alice makes offer)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": alice_addr,
            "have": {"denom": foo_name, "amount": "10000"},
            "want": {"denom": bar_name, "amount": "5000"},
        }
    )

    return messages


# ============================================================================
# HYPOTHESIS TESTS
# ============================================================================


@given(swap_amount=st.integers(min_value=10, max_value=1000))
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_make_trade_single_swap_random_amount(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    swap_amount,
):
    """
    Test MsgMakeTrade with a single swap using random amounts.

    This is the baseline - single swaps should always work.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    messages = []
    messages.extend(build_setup_messages(accounts["alice_addr"], foo_name, bar_name))

    # Single swap
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": accounts["alice_addr"],
            "operations": [
                {
                    "swap": {
                        "pool_id": "1",
                        "swap_in": {"denom": foo_name, "amount": str(swap_amount)},
                    }
                }
            ],
            "max_input": [{"denom": foo_name, "amount": "100000"}],
            "min_output": [],  # No minimum - AMM determines output
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_with_sudo",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], f"Single swap failed for amount {swap_amount}"
    # message_count excludes _compute_hash directives
    actual_msg_count = sum(1 for m in messages if "@type" in m)
    assert result["message_count"] == actual_msg_count


@given(take_units=st.integers(min_value=1, max_value=100))
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_make_trade_take_offer_random_units(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    take_units,
):
    """
    Test MsgMakeTrade taking an offer with random units.

    This tests the scenario from test_cli_make_trade_take_offer_exact_user_scenario.py
    where taking an offer triggered an invariant violation.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    messages = []
    messages.extend(build_setup_messages(accounts["alice_addr"], foo_name, bar_name))

    # Take the offer (offer 1 was created in setup)
    # Offer: have 10000 foo.dys, want 5000 bar.dys (unit ratio 2:1)
    # Taking gives us foo.dys in exchange for bar.dys
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": accounts["alice_addr"],
            "operations": [{"take": {"offer_id": "1", "take_units": str(take_units)}}],
            "max_input": [{"denom": bar_name, "amount": "100000"}],
            "min_output": [],  # No minimum - we just want to test it executes
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_with_sudo",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    # The offer-taking accounting bug has been fixed
    assert result["success"], f"Take offer failed for {take_units} units."
    # message_count is now 3: pool creation, offer creation, trade (name registration moved to fixture)
    assert result["message_count"] == 3


def test_executor_script_basic(chainnet, hypo_accounts, executor_script_path, gov_addr):
    """
    Sanity test: Verify the executor script works with a simple MsgSudo message.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    # Simple bank send message (via MsgSudo)
    messages = [
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": accounts["alice_addr"],
            "to_address": accounts["bob_addr"],
            "amount": [{"denom": "udys", "amount": "100"}],
        }
    ]

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_with_sudo",
        [messages, ["udys"], [accounts["alice_addr"], accounts["bob_addr"]], gov_addr],
    )

    assert result["success"], f"Script execution failed"
    assert result["message_count"] == 1

    # Verify balance changed
    pre_balance = result["pre_balances"][accounts["bob_addr"]]["udys"]
    post_balance = result["post_balances"][accounts["bob_addr"]]["udys"]
    assert (
        post_balance == pre_balance + 100
    ), f"Expected +100, got {post_balance - pre_balance}"
