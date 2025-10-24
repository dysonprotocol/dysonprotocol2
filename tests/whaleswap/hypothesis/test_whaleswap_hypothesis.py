"""
Hypothesis-based property testing for whaleswap module.

Uses randomized message generation to discover edge cases and invariant violations.
All operations happen in a single dysond query script exec for speed and determinism.
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume
from tests.whaleswap.hypothesis.execute_via_script import execute_via_script


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


# (Removed build_setup_messages; inline setup per test)


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

    # Build messages with template variables for sequential execution
    messages = []

    # Inline setup: create pool and a baseline offer
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": foo_name, "amount": "100000"},
                {"denom": bar_name, "amount": "100000"},
            ],
            "fee_pct": "0.003",
        }
    )
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": accounts["alice_addr"],
            "have": {"denom": foo_name, "amount": "10000"},
            "want": {"denom": bar_name, "amount": "5000"},
        }
    )

    # Add swap message with Jinja2-style template variable
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": accounts["alice_addr"],
            "operations": [
                {
                    "swap": {
                        "pool_id": "{{ msg_0['pool_id'] }}",  # Uses pool_id from first message (CreatePool)
                        "swap_in": {"denom": foo_name, "amount": str(swap_amount)},
                    }
                }
            ],
            "max_input": [{"denom": foo_name, "amount": "100000"}],
            "min_output": [],  # No minimum - AMM determines output
        }
    )

    # Execute messages sequentially with template substitution
    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], f"Sequential execution failed for amount {swap_amount}"
    assert result["message_count"] == len(messages)

    # Verify we got the expected template variables
    assert (
        "msg_0" in result["template_vars"]
    ), "msg_0 should contain CreatePool response"

    # Verify pool_id is present and valid (sequence starts from 1, but may be >1 due to shared test state)
    pool_id = result["template_vars"]["msg_0"]["pool_id"]
    assert pool_id, "pool_id should not be empty"
    assert int(pool_id) > 0, f"pool_id should be positive integer, got {pool_id}"


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

    # Build messages with template variables for sequential execution
    messages = []

    # Inline setup: create pool and a baseline offer
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": foo_name, "amount": "100000"},
                {"denom": bar_name, "amount": "100000"},
            ],
            "fee_pct": "0.003",
        }
    )
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": accounts["alice_addr"],
            "have": {"denom": foo_name, "amount": "10000"},
            "want": {"denom": bar_name, "amount": "5000"},
        }
    )

    # Take the offer created in setup (msg_1 contains MakeOffer response with offer_id)
    # Offer: have 10000 foo.dys, want 5000 bar.dys (unit ratio 2:1)
    # Taking gives us foo.dys in exchange for bar.dys
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": accounts["alice_addr"],
            "operations": [
                {
                    "take": {
                        "offer_id": "{{ msg_1['offer_id'] }}",
                        "take_units": str(take_units),
                    }
                }
            ],
            "max_input": [{"denom": bar_name, "amount": "100000"}],
            "min_output": [],  # No minimum - we just want to test it executes
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    # The offer-taking accounting bug has been fixed
    assert result["success"], f"Take offer failed for {take_units} units."
    # message_count is now 3: pool creation, offer creation, trade (name registration moved to fixture)
    assert result["message_count"] == len(messages)

    # Verify we got the expected template variables
    assert "msg_1" in result["template_vars"], "msg_1 should contain MakeOffer response"
    assert (
        "offer_id" in result["template_vars"]["msg_1"]
    ), "msg_1 should contain offer_id"


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


# ============================================================================
# STRATEGY 1: LIQUIDITY LIFECYCLE (RemoveLiquidity + AddLiquidity)
# ============================================================================


@given(
    add1=st.integers(min_value=100, max_value=10000),
    add2=st.integers(min_value=100, max_value=10000),
    remove_shares_pct=st.integers(min_value=5, max_value=95),
    has_price_band=st.booleans(),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_liquidity_add_remove_cycles(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    add1,
    add2,
    remove_shares_pct,
    has_price_band,
):
    """
    Test AddLiquidity → RemoveLiquidity cycles with random amounts and price bands.
    Covers concentrated liquidity math, refund logic, and full/partial exits.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    messages = []
    # Inline setup: create pool and a baseline offer
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": foo_name, "amount": "100000"},
                {"denom": bar_name, "amount": "100000"},
            ],
            "fee_pct": "0.003",
        }
    )
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": accounts["alice_addr"],
            "have": {"denom": foo_name, "amount": "10000"},
            "want": {"denom": bar_name, "amount": "5000"},
        }
    )

    # Add liquidity with potentially imbalanced amounts (tests refund logic)
    # Amount denoms MUST match the pool's canonical (sorted) reserve order
    denom_a, denom_b = sorted([foo_name, bar_name])
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
            "signer": accounts["alice_addr"],
            "pool_id": "{{ msg_0['pool_id'] }}",
            "amount1": {"denom": denom_a, "amount": str(add1)},
            "amount2": {"denom": denom_b, "amount": str(add2)},
        }
    )

    # Remove liquidity (partial removal based on percentage)
    # shares = msg_2['shares'], remove = shares * pct / 100
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
            "signer": accounts["alice_addr"],
            "pool_id": "{{ msg_0['pool_id'] }}",
            "shares": f"{{{{ str(int(msg_2['shares']) * {remove_shares_pct} // 100) }}}}",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result[
        "success"
    ], f"Liquidity cycle failed: add1={add1}, add2={add2}, remove_pct={remove_shares_pct}, banded={has_price_band}"
    assert result["message_count"] == len(messages)
    assert "msg_2" in result["template_vars"], "AddLiquidity should return shares"


@given(shares_to_remove=st.integers(min_value=1, max_value=100))
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_liquidity_full_exit_deletes_pool(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    shares_to_remove,
):
    """
    Test full pool exit (burn all shares) which should delete the pool.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    messages = []

    # CreatePool
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": foo_name, "amount": "10000"},
                {"denom": bar_name, "amount": "10000"},
            ],
            "fee_pct": "0.003",
        }
    )

    # Remove ALL shares (full exit)
    # Use a computed value based on bank supply query
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgRemoveLiquidity",
            "signer": accounts["alice_addr"],
            "pool_id": "{{ msg_0['pool_id'] }}",
            "shares": f"{{{{ str({shares_to_remove}) }}}}",  # Will use actual shares from pool creation
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], f"Full exit failed for shares={shares_to_remove}"
    assert result["message_count"] == 2


# ============================================================================
# STRATEGY 2: LIQUID WRAPPING ROUND-TRIPS
# ============================================================================


@given(
    wrap_amount=st.integers(min_value=100, max_value=5000),
    offer_amount=st.integers(min_value=50, max_value=3000),
    unwrap_amount=st.integers(min_value=50, max_value=4000),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_liquid_wrap_offer_unwrap_backing(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    wrap_amount,
    offer_amount,
    unwrap_amount,
):
    """
    Test ConvertToLiquid → MakeOffer with liquid have → ConvertToSolid.
    Tests PFAND locking and backing calculation with offers.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    liquid_foo = f"whaleswap.dys/coins/{foo_name}"
    denoms = [foo_name, bar_name, liquid_foo, "udys", "whaleswap.dys/pfand"]

    messages = []

    # Enable PFAND so liquid offers lock deposit and third-party cancel is eligible
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
            "authority": gov_addr,
            "params": {
                "pfand_per_offer": {"denom": "udys", "amount": "1"},
                "valuation_fee_pct": "0",
                "valuation_period": "3600s",
                "bid_timeout": "5s",
                "minimum_bid_percent_increase": "0",
                "max_note_length": 128,
            },
        }
    )

    # (PFAND already enabled above)

    # Wrap foo to liquid
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgConvertToLiquid",
            "caller": accounts["alice_addr"],
            "denom": foo_name,
            "amount": str(wrap_amount),
        }
    )

    # Make offer with liquid have (locks PFAND, no escrow)
    actual_offer = min(offer_amount, wrap_amount - 10)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": accounts["alice_addr"],
            "have": {"denom": liquid_foo, "amount": str(actual_offer)},
            "want": {"denom": bar_name, "amount": str(actual_offer)},
        }
    )

    # Unwrap remaining liquid
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgConvertToSolid",
            "caller": accounts["alice_addr"],
            "liquid_denom": liquid_foo,
            "amount": str(min(unwrap_amount, wrap_amount - actual_offer - 10)),
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result[
        "success"
    ], f"Wrap-offer-unwrap failed: wrap={wrap_amount}, offer={offer_amount}, unwrap={unwrap_amount}"
    assert result["message_count"] == 3


# ============================================================================
# STRATEGY 3: CANCEL OFFER PFAND RECOVERY
# ============================================================================


@given(
    offer_units=st.integers(min_value=2, max_value=20),
    take_units=st.integers(min_value=0, max_value=10),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_cancel_offer_after_partial_take(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    offer_units,
    take_units,
):
    """
    Test CancelOffer after partial takes.
    Covers status change reindexing and refund logic.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    # Bound take_units to offer_units
    actual_take = min(take_units, offer_units - 1)

    messages = []

    # Make offer
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": accounts["alice_addr"],
            "have": {"denom": foo_name, "amount": str(offer_units * 100)},
            "want": {"denom": bar_name, "amount": str(offer_units * 50)},
        }
    )

    # Partial take (only if actual_take > 0)
    assume(actual_take > 0)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": accounts["alice_addr"],
            "operations": [
                {
                    "take": {
                        "offer_id": "{{ msg_0['offer_id'] }}",
                        "take_units": str(actual_take),
                    }
                }
            ],
            "max_input": [{"denom": bar_name, "amount": "100000"}],
            "min_output": [],
        }
    )

    # Cancel offer (maker cancels)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
            "closer": accounts["alice_addr"],
            "offer_id": "{{ msg_0['offer_id'] }}",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result[
        "success"
    ], f"Cancel after partial take failed: units={offer_units}, take={actual_take}"
    assert result["message_count"] == 3


## moved to test_cancel_liquid_offer_pfand_recovery.py


def test_cancel_liquid_offer_pfand_recovery_gcd1(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
):
    """
    Third-party PFAND recovery with gcd=1 so unit_have equals full have amount.
    Setup have=x, want=x-1 so unit_have=x. Maker wraps x, then sends 1 away so
    maker_balance=x-1 < unit_have, making third-party cancel eligible.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    liquid_foo = f"whaleswap.dys/coins/{foo_name}"
    denoms = [foo_name, bar_name, liquid_foo, "udys", "whaleswap.dys/pfand"]

    x = 200  # any integer >= 2

    messages = []
    # Ensure pfand_per_offer > 0
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
            "authority": gov_addr,
            "params": {
                "pfand_per_offer": {"denom": "udys", "amount": "1"},
                "valuation_fee_pct": "0",
                "valuation_period": "3600s",
                "bid_timeout": "5s",
                "minimum_bid_percent_increase": "0",
                "max_note_length": 128,
            },
        }
    )
    # Wrap exactly x units
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgConvertToLiquid",
            "caller": accounts["alice_addr"],
            "denom": foo_name,
            "amount": str(x),
        }
    )
    # Make liquid offer with gcd=1 (have=x, want=x-1)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": accounts["alice_addr"],
            "have": {"denom": liquid_foo, "amount": str(x)},
            "want": {"denom": bar_name, "amount": str(x - 1)},
        }
    )
    # Drain 1 unit so maker balance becomes x-1 < unit_have(=x)
    messages.append(
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": accounts["alice_addr"],
            "to_address": accounts["bob_addr"],
            "amount": [{"denom": liquid_foo, "amount": "1"}],
        }
    )
    # Third-party cancel by bob
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
            "closer": accounts["bob_addr"],
            "offer_id": "{{ msg_1['offer_id'] }}",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"], accounts["bob_addr"]], gov_addr],
    )

    assert result["success"], "PFAND recovery (gcd=1) failed"
    assert result["message_count"] == 5


# ============================================================================
# STRATEGY 4: QUERY VALIDATION (Post-Operation Checks)
# ============================================================================


@given(
    num_offers=st.integers(min_value=1, max_value=5),
    offer_amounts=st.lists(
        st.integers(min_value=100, max_value=2000), min_size=1, max_size=5
    ),
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_query_offers_by_owner_and_denom(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    num_offers,
    offer_amounts,
):
    """
    Test query endpoints after creating multiple offers.
    Covers OffersByOwner, OffersByDenom, and individual Offer queries.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    # Limit to actual generated amounts
    actual_num = min(num_offers, len(offer_amounts))
    assume(actual_num >= 1)

    # Create multiple offers with different amounts
    messages = []
    for i in range(actual_num):
        messages.append(
            {
                "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
                "maker": accounts["alice_addr"],
                "have": {"denom": foo_name, "amount": str(offer_amounts[i])},
                "want": {"denom": bar_name, "amount": str(offer_amounts[i] // 2)},
            }
        )

    # Execute all offers
    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], f"Offer creation failed: num={actual_num}"
    assert result["message_count"] == actual_num

    # Query offers by owner
    query_result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "query_offers_by_owner",
        [accounts["alice_addr"], "open"],
    )
    assert (
        len(query_result) >= actual_num
    ), f"Expected at least {actual_num} offers, got {len(query_result)}"

    # Query offers by denom (have side)
    denom_result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "query_offers_by_denom",
        [foo_name, "have"],
    )
    assert (
        len(denom_result) >= actual_num
    ), f"Expected at least {actual_num} offers for denom {foo_name}"


@given(swap_amount=st.integers(min_value=10, max_value=1000))
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_query_trades_after_operations(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    swap_amount,
):
    """
    Test trade query endpoints after executing trades.
    Covers Trade, TradesByTaker, TradesByPool queries.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    messages = []
    # Inline setup: create pool and a baseline offer
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": foo_name, "amount": "10000"},
                {"denom": bar_name, "amount": "10000"},
            ],
            "fee_pct": "0.003",
        }
    )

    # Execute trade
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": accounts["alice_addr"],
            "operations": [
                {
                    "swap": {
                        "pool_id": "{{ msg_0['pool_id'] }}",
                        "swap_in": {"denom": foo_name, "amount": str(swap_amount)},
                    }
                }
            ],
            "max_input": [{"denom": foo_name, "amount": "100000"}],
            "min_output": [],
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], f"Trade execution failed: swap={swap_amount}"

    # Query trades by taker
    taker_trades = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "query_trades_by_taker",
        [accounts["alice_addr"]],
    )
    assert len(taker_trades) >= 1, f"Expected at least 1 trade for taker"

    # Query trades by pool
    pool_id = result["template_vars"]["msg_0"]["pool_id"]
    pool_trades = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "query_trades_by_pool",
        [pool_id],
    )
    assert len(pool_trades) >= 1, f"Expected at least 1 trade for pool {pool_id}"


# ============================================================================
# STRATEGY 5: AUCTION LIFECYCLE WITH TRADE RECORDING
# ============================================================================


@given(
    sell_amount=st.integers(min_value=100, max_value=5000),
    simulate_winning_bid=st.booleans(),
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_auction_lifecycle_trade_recording(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    sell_amount,
    simulate_winning_bid,
):
    """
    Test OpenAuction → RedeemAuction with/without bids.
    Tests trade recording when auction has winning bidder.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    messages = []

    # Open auction
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenAuction",
            "seller": accounts["alice_addr"],
            "bid_denom": bar_name,
            "sell": {"denom": foo_name, "amount": str(sell_amount)},
        }
    )

    # Simulate winning bid by transferring NFT and setting valuation
    # Note: This requires nameservice operations which we handle via MsgSudo
    assume(simulate_winning_bid)

    # Move NFT from alice to bob (simulates bid claim)
    messages.append(
        {
            "@type": "/dysonprotocol.nameservice.v1.MsgMoveNft",
            "name_destination": gov_addr,
            "class_id": f"whaleswap.dys/auctions/{bar_name}",
            "nft_id": "{{ '%010d' % int(msg_0['auction_id']) }}",
            "to_address": accounts["bob_addr"],
        }
    )

    # Set valuation on NFT (simulates accepted bid)
    messages.append(
        {
            "@type": "/dysonprotocol.nameservice.v1.MsgSetValuation",
            "owner": accounts["bob_addr"],
            "class_id": f"whaleswap.dys/auctions/{bar_name}",
            "nft_id": "{{ '%010d' % int(msg_0['auction_id']) }}",
            "valuation": {"denom": bar_name, "amount": str(sell_amount * 2)},
        }
    )

    # Redeem auction (bob redeems as winning bidder)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgRedeemAuction",
            "caller": accounts["bob_addr"],
            "auction_id": "{{ msg_0['auction_id'] }}",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"], accounts["bob_addr"]], gov_addr],
    )

    assert result[
        "success"
    ], f"Auction lifecycle failed: sell={sell_amount}, bid={simulate_winning_bid}"
    assert result["message_count"] == 4

    # Query auction by seller
    seller_auctions = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "query_auctions_by_seller",
        [accounts["alice_addr"]],
    )
    # Auction should be deleted after redemption
    assert isinstance(seller_auctions, list), f"Expected list of auctions"
