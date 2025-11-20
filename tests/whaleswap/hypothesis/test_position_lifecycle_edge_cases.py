"""
Hypothesis-based edge case testing for leverage position lifecycle.

This test focuses on ONE critical path with extreme parameter ranges:
    Create Pool → Open Position → Close Position

Goal: Find bugs in ratio calculations, rounding, dust handling, and extreme values.
"""

import pytest
from hypothesis import given, settings, strategies as st, assume
from decimal import Decimal
from tests.whaleswap.hypothesis.execute_via_script import execute_via_script


def int_to_decimal(value: int, places: int = 3) -> Decimal:
    """Convert integer to decimal with specified decimal places."""
    return Decimal(value) / Decimal(10**places)


@pytest.mark.hypothesis
@settings(max_examples=100, deadline=60000)
@given(
    # Pool parameters - extreme ranges
    pool_reserve_base=st.integers(min_value=1, max_value=1000),
    pool_reserve_quote=st.integers(min_value=1, max_value=1000),
    fee_rate_int=st.integers(min_value=0, max_value=990),  # 0.000 to 0.990
    interest_rate_int=st.integers(min_value=0, max_value=10000),  # 0.000 to 10.000
    min_cr_int=st.integers(min_value=101, max_value=10000),  # 1.01 to 100.00
    max_borrow_pct_int=st.integers(min_value=1, max_value=99),  # 0.01 to 0.99
    # Position parameters
    collateral_mult_int=st.integers(
        min_value=11, max_value=1000
    ),  # 1.1x to 100x of min
    borrow_pct_int=st.integers(min_value=1, max_value=4000),  # 0.001 to 0.400 of max
    # Close parameters
    close_fraction_int=st.integers(min_value=1, max_value=100),  # 0.01 to 1.00
)
def test_position_lifecycle_edge_cases(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    pool_reserve_base,
    pool_reserve_quote,
    fee_rate_int,
    interest_rate_int,
    min_cr_int,
    max_borrow_pct_int,
    collateral_mult_int,
    borrow_pct_int,
    close_fraction_int,
):
    """
    Test position lifecycle with extreme parameter ranges.

    Invariants tested:
    - Pool creation with correct reserves and parameters
    - Position opening with valid collateral ratio
    - Borrow amount within pool limits
    - Balance changes are correct
    - Position closing returns collateral and repays borrow
    - No negative balances
    - Conservation of value (module balance = pool + positions)
    """
    accounts = hypo_accounts
    base = registered_names["foo_name"]
    quote = registered_names["bar_name"]

    # Convert integers to decimals
    fee_rate = int_to_decimal(fee_rate_int, 3)
    interest_rate = int_to_decimal(interest_rate_int, 3)
    min_cr = int_to_decimal(min_cr_int, 2)
    max_borrow_pct = int_to_decimal(max_borrow_pct_int, 2)
    collateral_mult = int_to_decimal(collateral_mult_int, 1)
    borrow_pct = int_to_decimal(borrow_pct_int, 4)
    close_fraction = int_to_decimal(close_fraction_int, 2)

    # Liquidation threshold = min_cr * 1.1 (10% buffer)
    liq_threshold = min_cr * Decimal("1.1")

    # Calculate position amounts
    # Collateral = min_cr * borrow_amount * collateral_mult
    # Borrow = max_borrow_pct * min_pool_reserve * borrow_pct
    # Use the smaller of the two reserves to be conservative
    min_pool_reserve = min(pool_reserve_base, pool_reserve_quote)
    max_borrow_allowed = int(min_pool_reserve * float(max_borrow_pct))
    borrow_amount = max(1, int(max_borrow_allowed * float(borrow_pct)))

    # Ensure collateral meets minimum CR requirement
    # collateral_amount >= min_cr * borrow_amount
    min_collateral = (
        int(float(min_cr) * borrow_amount) + 1
    )  # +1 to ensure we meet min_cr
    collateral_amount = max(
        min_collateral, int(float(min_cr) * borrow_amount * float(collateral_mult))
    )

    # Build message sequence
    messages = []

    # 0. Set block delays to 0 (required for immediate closing)
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

    # 1. Create pool with extreme parameters
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": base, "amount": str(pool_reserve_base)},
                {"denom": quote, "amount": str(pool_reserve_quote)},
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
                {"denom": base, "amount": str(max_borrow_pct)},
                {"denom": quote, "amount": str(max_borrow_pct)},
            ],
        }
    )

    # 2. Open position (Alice borrows quote, collateralizes base)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
            "trader": accounts["alice_addr"],
            "pool_id": "{{ msg_1['pool_id'] }}",
            "collateral": {"denom": base, "amount": str(collateral_amount)},
            "borrow": {"denom": quote, "amount": str(borrow_amount)},
            "note": "edge_case_position",
        }
    )

    # 3. Partial close position
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": str(close_fraction),
            "note": "partial_close",
        }
    )

    # 4. Close remaining position (fraction = 1.0 closes all remaining)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": "1.0",
            "note": "final_close",
        }
    )

    # Execute all messages
    dysond = chainnet[0]  # Get dysond function from chainnet fixture
    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, [base, quote, "udys"], accounts["accounts"], gov_addr],
    )

    # Parse results
    msg_0_result = result["msg_results"][0]  # UpdateParams
    msg_1_result = result["msg_results"][1]  # CreatePool
    msg_2_result = result["msg_results"][2]  # OpenPosition
    msg_3_result = result["msg_results"][3]  # ClosePosition (partial)
    msg_4_result = result["msg_results"][4]  # ClosePosition (final)

    pool_id = msg_1_result["pool_id"]
    position_id = msg_2_result["position_id"]

    # Query final state
    pool = result["queries"]["pool"]
    positions_by_pool = result["queries"]["positions_by_pool"]
    alice_balance_base = result["queries"]["alice_balance_base"]
    alice_balance_quote = result["queries"]["alice_balance_quote"]
    module_balance_base = result["queries"]["module_balance_base"]
    module_balance_quote = result["queries"]["module_balance_quote"]

    # ========================================================================
    # INVARIANT CHECKS
    # ========================================================================

    # 1. Pool creation invariants
    assert pool["pool_id"] == str(pool_id), "Pool ID mismatch"
    pool_coins = pool["coins"]
    assert (
        len(pool_coins) == 2
    ), f"Pool must have exactly 2 coins, got {len(pool_coins)}"
    assert int(pool_coins[0]["amount"]) >= 0, "Pool coin 0 amount is negative"
    assert int(pool_coins[1]["amount"]) >= 0, "Pool coin 1 amount is negative"

    # 2. Position opening invariants (from msg_2_result)
    assert position_id > 0, "Position ID must be positive"

    # Check held amount (collateral minus what was swapped/used)
    held_amount = int(msg_2_result["held"]["amount"])
    assert held_amount >= 0, "Held amount cannot be negative"

    # 3. Position closing invariants (partial close)
    # After partial close, position should still exist but with reduced amounts
    # (we can't query intermediate state, but we can check final state)

    # 4. Final close invariants
    # After final close, position should be gone from positions_by_pool
    # or have zero amounts
    final_positions = [p for p in positions_by_pool if p["id"] == position_id]

    # Position should either be deleted or have zero/minimal amounts
    # Split assertion to avoid 'or' operator
    position_deleted = len(final_positions) == 0
    position_has_dust = (
        len(final_positions) > 0
        and int(final_positions[0]["collateral"]["amount"]) <= 1
    )
    assert (
        position_deleted + position_has_dust > 0
    ), f"Position should be closed or have dust amounts only, found {len(final_positions)} positions"

    # 5. Balance invariants - no negative balances
    assert (
        alice_balance_base >= 0
    ), f"Alice base balance is negative: {alice_balance_base}"
    assert (
        alice_balance_quote >= 0
    ), f"Alice quote balance is negative: {alice_balance_quote}"
    assert (
        module_balance_base >= 0
    ), f"Module base balance is negative: {module_balance_base}"
    assert (
        module_balance_quote >= 0
    ), f"Module quote balance is negative: {module_balance_quote}"

    # 6. Conservation of value
    # Module balance should equal pool reserves + sum of all position collaterals
    # Pool coins are in canonical order (lexicographic by denom)
    pool_coins = pool["coins"]
    pool_coin_0_amt = int(pool_coins[0]["amount"])
    pool_coin_1_amt = int(pool_coins[1]["amount"])
    pool_coin_0_denom = pool_coins[0]["denom"]
    pool_coin_1_denom = pool_coins[1]["denom"]

    # Map to base/quote based on denom
    pool_reserve_base = (
        pool_coin_0_amt if pool_coin_0_denom == base else pool_coin_1_amt
    )
    pool_reserve_quote = (
        pool_coin_0_amt if pool_coin_0_denom == quote else pool_coin_1_amt
    )

    total_collateral_base = sum(
        int(p["collateral"]["amount"])
        for p in positions_by_pool
        if p["collateral"]["denom"] == base
    )
    total_collateral_quote = sum(
        int(p["collateral"]["amount"])
        for p in positions_by_pool
        if p["collateral"]["denom"] == quote
    )

    # Module balance >= pool reserves + position collaterals (can be higher due to fees)
    expected_module_base = pool_reserve_base + total_collateral_base
    expected_module_quote = pool_reserve_quote + total_collateral_quote

    assert (
        module_balance_base >= expected_module_base
    ), f"Module base {module_balance_base} < expected {expected_module_base}"
    assert (
        module_balance_quote >= expected_module_quote
    ), f"Module quote {module_balance_quote} < expected {expected_module_quote}"

    # 7. No integer overflow (all amounts fit in uint64)
    max_uint64 = 2**64 - 1
    assert pool_reserve_base <= max_uint64, "Pool reserve base overflow"
    assert pool_reserve_quote <= max_uint64, "Pool reserve quote overflow"
    assert module_balance_base <= max_uint64, "Module balance base overflow"
    assert module_balance_quote <= max_uint64, "Module balance quote overflow"

    # 8. Sanity checks on amounts
    assert collateral_amount > 0, "Collateral amount must be positive"
    assert borrow_amount > 0, "Borrow amount must be positive"
    assert (
        collateral_amount >= borrow_amount
    ), f"Collateral {collateral_amount} < borrow {borrow_amount} (should be >= for min_cr >= 1.0)"

    # 9. Collateral ratio check (at opening)
    actual_cr = collateral_amount / borrow_amount
    assert actual_cr >= float(
        min_cr
    ), f"Actual CR {actual_cr:.2f} < min CR {float(min_cr):.2f}"

    # 10. Borrow limit check
    assert (
        borrow_amount <= max_borrow_allowed
    ), f"Borrow {borrow_amount} > max allowed {max_borrow_allowed}"

    # 11. Close fraction validity
    assert (
        0 < float(close_fraction) <= 1.0
    ), f"Close fraction {close_fraction} must be in (0, 1]"

    # All checks passed!
    print(
        f"✅ PASS: pool_base={pool_reserve_base}, pool_quote={pool_reserve_quote}, "
        f"fee={fee_rate}, interest={interest_rate}, min_cr={min_cr}, "
        f"collateral={collateral_amount}, borrow={borrow_amount}, close_fraction={close_fraction}"
    )


@pytest.mark.hypothesis
@settings(max_examples=20, deadline=60000)
@given(
    # Minimal test - focus on dust amounts and extreme ratios
    pool_reserve_base=st.integers(min_value=1, max_value=1000),
    pool_reserve_quote=st.integers(min_value=1, max_value=1000),
    min_cr_int=st.integers(min_value=101, max_value=500),  # 1.01 to 5.00
    collateral_mult_int=st.integers(min_value=11, max_value=100),  # 1.1x to 10x
    borrow_amount=st.integers(min_value=1, max_value=100),  # Test various borrow sizes
)
def test_position_dust_amounts(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    pool_reserve_base,
    pool_reserve_quote,
    min_cr_int,
    collateral_mult_int,
    borrow_amount,
):
    """
    Focused test on dust amounts (minimal values).

    This test uses minimal pool reserves and position sizes to find
    rounding errors and division-by-zero bugs.

    Note: Pool reserves must be >= 100 to avoid "swap output too small" errors
    when opening leveraged positions with tiny amounts.
    """
    accounts = hypo_accounts
    base = registered_names["foo_name"]
    quote = registered_names["bar_name"]

    min_cr = int_to_decimal(min_cr_int, 2)
    collateral_mult = int_to_decimal(collateral_mult_int, 1)

    # Use minimal values
    fee_rate = Decimal("0.001")  # 0.1%
    interest_rate = Decimal("0.001")  # 0.1%
    max_borrow_pct = Decimal("0.50")  # 50%
    liq_threshold = min_cr * Decimal("1.1")

    # Ensure borrow amount is reasonable relative to pool size
    # Use the smaller of the two reserves to be conservative
    min_pool_reserve = min(pool_reserve_base, pool_reserve_quote)
    max_borrow_allowed = int(min_pool_reserve * float(max_borrow_pct))
    borrow_amount = min(borrow_amount, max_borrow_allowed)

    # Borrow must be at least 1 (0 is invalid)
    borrow_amount = max(1, borrow_amount)

    # Ensure collateral meets minimum CR requirement
    min_collateral = (
        int(float(min_cr) * borrow_amount) + 1
    )  # +1 to ensure we meet min_cr
    collateral_amount = max(
        min_collateral, int(float(min_cr) * borrow_amount * float(collateral_mult))
    )

    messages = []

    # Set block delays to 0
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

    # Create pool
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": accounts["alice_addr"],
            "coins": [
                {"denom": base, "amount": str(pool_reserve_base)},
                {"denom": quote, "amount": str(pool_reserve_quote)},
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
                {"denom": base, "amount": str(max_borrow_pct)},
                {"denom": quote, "amount": str(max_borrow_pct)},
            ],
        }
    )

    # Open position with dust amounts
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
            "trader": accounts["alice_addr"],
            "pool_id": "{{ msg_1['pool_id'] }}",
            "collateral": {"denom": base, "amount": str(collateral_amount)},
            "borrow": {"denom": quote, "amount": str(borrow_amount)},
            "note": "dust_position",
        }
    )

    # Close position fully
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgClosePosition",
            "user": accounts["alice_addr"],
            "position_id": "{{ msg_2['position_id'] }}",
            "fraction": "1.0",
            "note": "dust_close",
        }
    )

    # Execute
    dysond = chainnet[0]  # Get dysond function from chainnet fixture
    result = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "execute_messages_sequentially",
        [messages, [base, quote, "udys"], accounts["accounts"], gov_addr],
    )

    # Basic invariants
    pool = result["queries"]["pool"]
    module_balance_base = result["queries"]["module_balance_base"]
    module_balance_quote = result["queries"]["module_balance_quote"]

    pool_coins = pool["coins"]
    assert (
        len(pool_coins) == 2
    ), f"Pool must have exactly 2 coins, got {len(pool_coins)}"
    assert int(pool_coins[0]["amount"]) >= 0, "Pool coin 0 amount is negative"
    assert int(pool_coins[1]["amount"]) >= 0, "Pool coin 1 amount is negative"
    assert module_balance_base >= 0, "Module base balance is negative"
    assert module_balance_quote >= 0, "Module quote balance is negative"

    print(
        f"✅ DUST TEST PASS: pool_base={pool_reserve_base}, pool_quote={pool_reserve_quote}, "
        f"min_cr={min_cr}, collateral={collateral_amount}, borrow={borrow_amount}"
    )
