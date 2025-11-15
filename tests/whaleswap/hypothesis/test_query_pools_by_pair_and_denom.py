import json
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume
from tests.whaleswap.hypothesis.execute_via_script import execute_via_script


@given(
    num_pools=st.integers(min_value=1, max_value=3),
    pool_reserves=st.lists(
        st.integers(min_value=1000, max_value=10000), min_size=1, max_size=3
    ),
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_query_pools_by_pair_and_denom(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    num_pools,
    pool_reserves,
):
    """
    Test pool query endpoints after creating multiple pools.
    Covers PoolsByPair, PoolsByDenom queries.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    actual_num = min(num_pools, len(pool_reserves))
    assume(actual_num >= 1)

    # Sort denoms lexicographically for config arrays
    base, quote = sorted([foo_name, bar_name])

    messages = []
    for i in range(actual_num):
        messages.append(
            {
                "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
                "creator": accounts["alice_addr"],
                "coins": [
                    {"denom": foo_name, "amount": str(pool_reserves[i])},
                    {"denom": bar_name, "amount": str(pool_reserves[i])},
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

    # Create and query within a single script run so queries see writes
    cq = execute_via_script(
        dysond,
        executor_script_path,
        gov_addr,
        "create_and_query_pools",
        [messages, foo_name, bar_name, denoms, [accounts["alice_addr"]], gov_addr],
    )

    assert cq["success"], f"Pool creation failed: num={actual_num}"
    assert cq["message_count"] == actual_num
    assert (
        len(cq["pair"]) >= actual_num
    ), f"Expected at least {actual_num} pools for pair"
    assert (
        len(cq["denom"]) >= actual_num
    ), f"Expected at least {actual_num} pools containing {foo_name}"
