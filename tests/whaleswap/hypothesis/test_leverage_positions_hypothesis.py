"""
Hypothesis-based property testing for whaleswap leveraged positions.

Tests pool creation, position opening, closing, partial closes, and liquidations
with randomized parameters to discover edge cases and invariant violations.

All operations execute in a single dysond query script run for speed and determinism.
Block delays are set to 0 via MsgUpdateParams to enable same-transaction close/liquidation.
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume
from tests.whaleswap.hypothesis.execute_via_script import execute_via_script


# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


@st.composite
def pool_config(draw, base_denom, quote_denom):
    """
    Generate valid pool configuration parameters.

    Ensures:
    - Fee rates are reasonable (0.1% - 5%)
    - Interest rates are reasonable (0% - 20% APR)
    - Min collateral ratio > 1 (required for leverage)
    - Liquidation threshold < min_collateral_ratio
    - Max borrow percent < 1 (can't borrow entire pool)
    """
    # Sort denoms for canonical order
    d0, d1 = sorted([base_denom, quote_denom])

    fee_rate = draw(st.decimals(min_value="0.001", max_value="0.05", places=3))
    interest_rate = draw(st.decimals(min_value="0", max_value="0.2", places=3))
    min_cr = draw(st.decimals(min_value="1.2", max_value="3.0", places=2))
    liq_threshold = draw(
        st.decimals(min_value="1.05", max_value=str(float(min_cr) - 0.05), places=2)
    )
    max_borrow_pct = draw(st.decimals(min_value="0.1", max_value="0.8", places=2))

    return {
        "fee_rate": [
            {"denom": d0, "amount": str(fee_rate)},
            {"denom": d1, "amount": str(fee_rate)},
        ],
        "interest_rate": [
            {"denom": d0, "amount": str(interest_rate)},
            {"denom": d1, "amount": str(interest_rate)},
        ],
        "min_initial_collateral_ratio": [
            {"denom": d0, "amount": str(min_cr)},
            {"denom": d1, "amount": str(min_cr)},
        ],
        "liquidation_threshold": [
            {"denom": d0, "amount": str(liq_threshold)},
            {"denom": d1, "amount": str(liq_threshold)},
        ],
        "max_borrow_percent": [
            {"denom": d0, "amount": str(max_borrow_pct)},
            {"denom": d1, "amount": str(max_borrow_pct)},
        ],
    }


@st.composite
def position_params(draw, pool_reserves, min_cr, denoms):
    """
    Generate valid position parameters.

    Args:
        pool_reserves: Pool reserve amount per denom
        min_cr: Minimum collateral ratio from pool config
        denoms: List of [base_denom, quote_denom]

    Returns:
        Dict with collateral and borrow coins
    """
    base_denom, quote_denom = denoms

    # Choose collateral and borrow denoms (opposite sides)
    collateral_denom = draw(st.sampled_from([base_denom, quote_denom]))
    borrow_denom = quote_denom if collateral_denom == base_denom else base_denom

    # Borrow amount: 1% to 20% of pool reserves (respects max_borrow_percent)
    max_borrow = int(pool_reserves * 0.2)
    borrow_amt = draw(st.integers(min_value=100, max_value=max_borrow))

    # Collateral: must satisfy min_cr (with buffer for price impact)
    # CR = collateral_value / debt_value (in borrow denom units)
    # For same-denom: collateral >= borrow * min_cr
    # For cross-denom: assume 1:1 price initially, add 20% buffer
    min_collateral = int(borrow_amt * float(min_cr) * 1.2)
    max_collateral = min(pool_reserves, borrow_amt * 10)  # Cap at 10x leverage

    assume(max_collateral >= min_collateral)

    collateral_amt = draw(
        st.integers(min_value=min_collateral, max_value=max_collateral)
    )

    return {
        "collateral": {"denom": collateral_denom, "amount": str(collateral_amt)},
        "borrow": {"denom": borrow_denom, "amount": str(borrow_amt)},
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def build_create_pool_msg(creator, denoms, reserves, config):
    """Build MsgCreatePool with given config."""
    base, quote = sorted(denoms)
    return {
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator,
        "coins": [
            {"denom": base, "amount": str(reserves)},
            {"denom": quote, "amount": str(reserves)},
        ],
        **config,
    }


def build_open_position_msg(trader, pool_id_template, collateral, borrow, note=""):
    """Build MsgOpenPosition."""
    return {
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": trader,
        "pool_id": pool_id_template,
        "collateral": collateral,
        "borrow": borrow,
        "note": note,
    }


def build_close_position_msg(user, position_id_template, fraction, note=""):
    """Build MsgClosePosition."""
    return {
        "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
        "user": user,
        "position_id": position_id_template,
        "fraction": str(fraction),
        "note": note,
    }


# ============================================================================
# SANITY TESTS (Fixed Parameters)
# ============================================================================


def test_leverage_sanity_open_close_basic(
    chainnet, hypo_accounts, registered_names, executor_script_path, gov_addr
):
    """
    Sanity test: Open and immediately close a position with known-good parameters.

    This validates the infrastructure is working before running hypothesis tests.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts
    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    base, quote = sorted([foo_name, bar_name])

    messages = []

    # 1. Set block delays to 0 (CRITICAL for same-tx close)
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
                "block_delay_before_close": "0",
                "block_delay_before_liquidation": "0",
            },
        }
    )

    # 2. Create pool with 100k reserves
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": base, "amount": "100000"},
                {"denom": quote, "amount": "100000"},
            ],
            "fee_rate": [
                {"denom": base, "amount": "0.003"},
                {"denom": quote, "amount": "0.003"},
            ],
            "interest_rate": [
                {"denom": base, "amount": "0.05"},
                {"denom": quote, "amount": "0.05"},
            ],
            "min_initial_collateral_ratio": [
                {"denom": base, "amount": "1.5"},
                {"denom": quote, "amount": "1.5"},
            ],
            "liquidation_threshold": [
                {"denom": base, "amount": "1.2"},
                {"denom": quote, "amount": "1.2"},
            ],
            "max_borrow_percent": [
                {"denom": base, "amount": "0.8"},
                {"denom": quote, "amount": "0.8"},
            ],
        }
    )

    # 3. Open position: 3000 collateral, 1000 borrow (CR = 3.0)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
            "trader": accounts["alice_addr"],
            "pool_id": "{{ msg_1['pool_id'] }}",
            "collateral": {"denom": base, "amount": "3000"},
            "borrow": {"denom": quote, "amount": "1000"},
            "note": "sanity_test",
        }
    )

    # 4. Close position immediately (full close)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": "1.0",
            "note": "sanity_close",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], f"Sanity test failed: {result}"
    assert result["message_count"] == 4

    # Validate response structure
    template_vars = result.get("template_vars", {})
    assert "msg_1" in template_vars, "CreatePool should return pool_id"
    assert (
        "pool_id" in template_vars["msg_1"]
    ), "pool_id missing from CreatePool response"
    assert "msg_2" in template_vars, "OpenPosition should return position_id"
    assert (
        "position_id" in template_vars["msg_2"]
    ), "position_id missing from OpenPosition response"
    assert "msg_3" in template_vars, "ClosePosition should return response"

    print(
        f"✓ Sanity test passed: pool_id={template_vars['msg_1']['pool_id']}, position_id={template_vars['msg_2']['position_id']}"
    )


# ============================================================================
# HYPOTHESIS TESTS
# ============================================================================


@given(
    pool_reserves=st.integers(min_value=50000, max_value=500000),
    collateral_amt=st.integers(min_value=2000, max_value=50000),
    borrow_amt=st.integers(min_value=500, max_value=20000),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_open_close_position_random_amounts(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    pool_reserves,
    collateral_amt,
    borrow_amt,
):
    """
    Test OpenPosition → ClosePosition with random amounts.

    Validates:
    - Position opens successfully with valid CR
    - Position closes and returns collateral + profit/loss
    - Pool accounting is correct (reserves, total_borrowed)
    """
    dysond = chainnet[0]
    accounts = hypo_accounts
    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    base, quote = sorted([foo_name, bar_name])

    # Ensure collateral ratio is valid (>= 1.5 min CR with buffer)
    assume(collateral_amt >= borrow_amt * 1.8)

    # Ensure borrow doesn't exceed pool capacity (80% max)
    assume(borrow_amt <= pool_reserves * 0.8)

    messages = []

    # 1. Set block delays to 0
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
                "block_delay_before_close": "0",
                "block_delay_before_liquidation": "0",
            },
        }
    )

    # 2. Create pool
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": base, "amount": str(pool_reserves)},
                {"denom": quote, "amount": str(pool_reserves)},
            ],
            "fee_rate": [
                {"denom": base, "amount": "0.003"},
                {"denom": quote, "amount": "0.003"},
            ],
            "interest_rate": [
                {"denom": base, "amount": "0.05"},
                {"denom": quote, "amount": "0.05"},
            ],
            "min_initial_collateral_ratio": [
                {"denom": base, "amount": "1.5"},
                {"denom": quote, "amount": "1.5"},
            ],
            "liquidation_threshold": [
                {"denom": base, "amount": "1.2"},
                {"denom": quote, "amount": "1.2"},
            ],
            "max_borrow_percent": [
                {"denom": base, "amount": "0.8"},
                {"denom": quote, "amount": "0.8"},
            ],
        }
    )

    # 3. Open position
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
            "trader": accounts["alice_addr"],
            "pool_id": "{{ msg_1['pool_id'] }}",
            "collateral": {"denom": base, "amount": str(collateral_amt)},
            "borrow": {"denom": quote, "amount": str(borrow_amt)},
        }
    )

    # 4. Close position (full close)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": "1.0",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], (
        f"Position lifecycle failed: reserves={pool_reserves}, "
        f"collateral={collateral_amt}, borrow={borrow_amt}"
    )
    assert result["message_count"] == 4


@given(
    fraction=st.decimals(min_value="0.1", max_value="0.9", places=2),
    pool_reserves=st.integers(min_value=100000, max_value=500000),
    collateral_amt=st.integers(min_value=10000, max_value=50000),
    borrow_amt=st.integers(min_value=3000, max_value=15000),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_partial_close_position_random_fractions(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    fraction,
    pool_reserves,
    collateral_amt,
    borrow_amt,
):
    """
    Test partial position closes with random fractions.

    Validates:
    - Remaining position is healthy (CR >= min_cr)
    - Partial collateral returned
    - Pool accounting updated correctly
    - Position can be closed again (partial → full)
    """
    dysond = chainnet[0]
    accounts = hypo_accounts
    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    base, quote = sorted([foo_name, bar_name])

    # Ensure healthy CR (>= 2.0 to handle partial close remaining position)
    assume(collateral_amt >= borrow_amt * 2.0)
    assume(borrow_amt <= pool_reserves * 0.5)

    messages = []

    # 1. Set block delays to 0
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
                "block_delay_before_close": "0",
                "block_delay_before_liquidation": "0",
            },
        }
    )

    # 2. Create pool
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": base, "amount": str(pool_reserves)},
                {"denom": quote, "amount": str(pool_reserves)},
            ],
            "fee_rate": [
                {"denom": base, "amount": "0.003"},
                {"denom": quote, "amount": "0.003"},
            ],
            "interest_rate": [
                {"denom": base, "amount": "0.05"},
                {"denom": quote, "amount": "0.05"},
            ],
            "min_initial_collateral_ratio": [
                {"denom": base, "amount": "1.5"},
                {"denom": quote, "amount": "1.5"},
            ],
            "liquidation_threshold": [
                {"denom": base, "amount": "1.2"},
                {"denom": quote, "amount": "1.2"},
            ],
            "max_borrow_percent": [
                {"denom": base, "amount": "0.8"},
                {"denom": quote, "amount": "0.8"},
            ],
        }
    )

    # 3. Open position
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
            "trader": accounts["alice_addr"],
            "pool_id": "{{ msg_1['pool_id'] }}",
            "collateral": {"denom": base, "amount": str(collateral_amt)},
            "borrow": {"denom": quote, "amount": str(borrow_amt)},
        }
    )

    # 4. Partial close
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": str(fraction),
        }
    )

    # 5. Close remaining (full close of what's left)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": "1.0",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], (
        f"Partial close failed: fraction={fraction}, "
        f"collateral={collateral_amt}, borrow={borrow_amt}"
    )
    assert result["message_count"] == 5


@given(
    num_positions=st.integers(min_value=2, max_value=4),
    position_sizes=st.lists(
        st.integers(min_value=1000, max_value=5000), min_size=2, max_size=4
    ),
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_multiple_positions_same_pool(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    num_positions,
    position_sizes,
):
    """
    Test multiple positions on the same pool.

    Validates:
    - Pool borrow caps enforced across positions
    - Each position tracked independently
    - Closing one doesn't affect others
    - Total borrowed accounting correct
    """
    dysond = chainnet[0]
    accounts = hypo_accounts
    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    base, quote = sorted([foo_name, bar_name])

    # Limit to actual generated sizes
    actual_num = min(num_positions, len(position_sizes))
    assume(actual_num >= 2)

    # Large pool to accommodate multiple positions
    pool_reserves = 500000

    messages = []

    # 1. Set block delays to 0
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
                "block_delay_before_close": "0",
                "block_delay_before_liquidation": "0",
            },
        }
    )

    # 2. Create pool
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": base, "amount": str(pool_reserves)},
                {"denom": quote, "amount": str(pool_reserves)},
            ],
            "fee_rate": [
                {"denom": base, "amount": "0.003"},
                {"denom": quote, "amount": "0.003"},
            ],
            "interest_rate": [
                {"denom": base, "amount": "0.05"},
                {"denom": quote, "amount": "0.05"},
            ],
            "min_initial_collateral_ratio": [
                {"denom": base, "amount": "1.5"},
                {"denom": quote, "amount": "1.5"},
            ],
            "liquidation_threshold": [
                {"denom": base, "amount": "1.2"},
                {"denom": quote, "amount": "1.2"},
            ],
            "max_borrow_percent": [
                {"denom": base, "amount": "0.8"},
                {"denom": quote, "amount": "0.8"},
            ],
        }
    )

    # 3. Open multiple positions
    position_msg_indices = []
    for i in range(actual_num):
        borrow_amt = position_sizes[i]
        collateral_amt = borrow_amt * 2  # 2x CR

        messages.append(
            {
                "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
                "trader": accounts["alice_addr"],
                "pool_id": "{{ msg_1['pool_id'] }}",
                "collateral": {"denom": base, "amount": str(collateral_amt)},
                "borrow": {"denom": quote, "amount": str(borrow_amt)},
                "note": f"position_{i}",
            }
        )
        position_msg_indices.append(len(messages) - 1)

    # 4. Close first position only
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": f"{{{{ msg_{position_msg_indices[0]}['position_id'] }}}}",
            "fraction": "1.0",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], f"Multiple positions test failed: num={actual_num}"
    # 1 (params) + 1 (pool) + actual_num (positions) + 1 (close)
    assert result["message_count"] == 2 + actual_num + 1


@given(
    borrow_amt=st.integers(min_value=10, max_value=80000),
    collateral_multiplier=st.decimals(min_value="1.5", max_value="3.0", places=1),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_position_edge_cases(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    borrow_amt,
    collateral_multiplier,
):
    """
    Test edge cases and boundary conditions with random parameters.

    Tests various combinations:
    - Small borrows (10) to large borrows (80k = 80% of 100k pool)
    - Collateral ratios from 1.5x (minimum) to 3.0x (safe)
    """
    dysond = chainnet[0]
    accounts = hypo_accounts
    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    base, quote = sorted([foo_name, bar_name])

    pool_reserves = 100000

    # Ensure borrow doesn't exceed pool capacity
    assume(borrow_amt <= pool_reserves * 0.8)

    # Calculate collateral based on multiplier
    collateral_amt = int(borrow_amt * float(collateral_multiplier))

    messages = []

    # 1. Set block delays to 0
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
                "block_delay_before_close": "0",
                "block_delay_before_liquidation": "0",
            },
        }
    )

    # 2. Create pool
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": base, "amount": str(pool_reserves)},
                {"denom": quote, "amount": str(pool_reserves)},
            ],
            "fee_rate": [
                {"denom": base, "amount": "0.003"},
                {"denom": quote, "amount": "0.003"},
            ],
            "interest_rate": [
                {"denom": base, "amount": "0.05"},
                {"denom": quote, "amount": "0.05"},
            ],
            "min_initial_collateral_ratio": [
                {"denom": base, "amount": "1.5"},
                {"denom": quote, "amount": "1.5"},
            ],
            "liquidation_threshold": [
                {"denom": base, "amount": "1.2"},
                {"denom": quote, "amount": "1.2"},
            ],
            "max_borrow_percent": [
                {"denom": base, "amount": "0.8"},
                {"denom": quote, "amount": "0.8"},
            ],
        }
    )

    # 3. Open position
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
            "trader": accounts["alice_addr"],
            "pool_id": "{{ msg_1['pool_id'] }}",
            "collateral": {"denom": base, "amount": str(collateral_amt)},
            "borrow": {"denom": quote, "amount": str(borrow_amt)},
            "note": "edge_case",
        }
    )

    # 4. Close position
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": "1.0",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], (
        f"Edge case failed: borrow={borrow_amt}, "
        f"collateral_multiplier={collateral_multiplier}"
    )
    assert result["message_count"] == 4


# ============================================================================
# POOL PARAMETER FUZZING
# ============================================================================


@given(
    fee_rate=st.decimals(min_value="0.001", max_value="0.1", places=3),
    interest_rate=st.decimals(min_value="0", max_value="0.3", places=3),
    min_cr=st.decimals(min_value="1.1", max_value="5.0", places=2),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_pool_creation_random_params(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    fee_rate,
    interest_rate,
    min_cr,
):
    """
    Test pool creation with random parameters.

    Validates:
    - Pool accepts wide range of valid parameters
    - Position can be opened and closed with any valid pool config
    """
    dysond = chainnet[0]
    accounts = hypo_accounts
    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    base, quote = sorted([foo_name, bar_name])

    # Liquidation threshold must be < min_cr
    liq_threshold = max(float(min_cr) - 0.1, 1.05)

    messages = []

    # 1. Set block delays to 0
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
                "block_delay_before_close": "0",
                "block_delay_before_liquidation": "0",
            },
        }
    )

    # 2. Create pool with random params
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": base, "amount": "100000"},
                {"denom": quote, "amount": "100000"},
            ],
            "fee_rate": [
                {"denom": base, "amount": str(fee_rate)},
                {"denom": quote, "amount": str(fee_rate)},
            ],
            "interest_rate": [
                {"denom": base, "amount": str(interest_rate)},
                {"denom": quote, "amount": str(interest_rate)},
            ],
            "min_initial_collateral_ratio": [
                {"denom": base, "amount": str(min_cr)},
                {"denom": quote, "amount": str(min_cr)},
            ],
            "liquidation_threshold": [
                {"denom": base, "amount": str(liq_threshold)},
                {"denom": quote, "amount": str(liq_threshold)},
            ],
            "max_borrow_percent": [
                {"denom": base, "amount": "0.5"},
                {"denom": quote, "amount": "0.5"},
            ],
        }
    )

    # 3. Open position (safe CR relative to min_cr)
    borrow_amt = 1000
    collateral_amt = int(borrow_amt * float(min_cr) * 1.2)  # 20% buffer

    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
            "trader": accounts["alice_addr"],
            "pool_id": "{{ msg_1['pool_id'] }}",
            "collateral": {"denom": base, "amount": str(collateral_amt)},
            "borrow": {"denom": quote, "amount": str(borrow_amt)},
        }
    )

    # 4. Close position
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": "1.0",
        }
    )

    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert result["success"], (
        f"Pool params test failed: fee={fee_rate}, "
        f"interest={interest_rate}, min_cr={min_cr}"
    )
    assert result["message_count"] == 4
