"""
Isolated PFAND recovery test for CancelOffer with liquid-mode offers.

This test enables PFAND explicitly before any operations to ensure
third-party cancel eligibility is evaluated with pfand_locked > 0.
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from tests.whaleswap.hypothesis.execute_via_script import execute_via_script


@given(
    liquid_offer_amount=st.integers(min_value=100, max_value=5000),
    drain_amount=st.integers(min_value=50, max_value=4000),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_cancel_liquid_offer_pfand_recovery(
    chainnet,
    hypo_accounts,
    registered_names,
    executor_script_path,
    gov_addr,
    liquid_offer_amount,
    drain_amount,
):
    """
    Test third-party PFAND recovery when maker's liquid balance drops below unit_have.
    Tests CancelOffer eligibility check for non-makers.
    """
    dysond = chainnet[0]
    accounts = hypo_accounts

    foo_name = registered_names["foo_name"]
    bar_name = registered_names["bar_name"]
    denoms = [foo_name, bar_name, "udys"]

    messages = []

    # Enable PFAND before any liquid operations
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

    # Make liquid-mode offer (locks PFAND, no escrow)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": accounts["alice_addr"],
            "have": {"denom": foo_name, "amount": str(liquid_offer_amount)},
            # Choose want = have - 1 to force gcd=1 → unit_have = have
            "want": {"denom": bar_name, "amount": str(liquid_offer_amount - 1)},
            "settlement_mode": "SETTLEMENT_LIQUID",
        }
    )

    # Drain alice's BASE balance below unit_have (send to bob)
    # registered_names minted 1_000_000 units to alice; leave (have-1) so balance < unit_have
    actual_drain = 1_000_000 - (liquid_offer_amount - 1)
    messages.append(
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": accounts["alice_addr"],
            "to_address": accounts["bob_addr"],
            "amount": [{"denom": foo_name, "amount": str(actual_drain)}],
        }
    )

    # Third-party cancel (bob recovers PFAND)
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

    assert result[
        "success"
    ], f"PFAND recovery failed: offer={liquid_offer_amount}, drain={drain_amount}"
    assert result["message_count"] == 4
