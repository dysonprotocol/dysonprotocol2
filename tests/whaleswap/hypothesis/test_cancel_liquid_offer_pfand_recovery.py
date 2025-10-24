"""
Isolated PFAND recovery test for CancelOffer with liquid-have offers.

This test enables PFAND explicitly before any liquid operations to ensure
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
    liquid_foo = f"whaleswap.dys/coins/{foo_name}"
    denoms = [foo_name, bar_name, liquid_foo, "udys", "whaleswap.dys/pfand"]

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

    # Wrap to liquid
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgConvertToLiquid",
            "caller": accounts["alice_addr"],
            "denom": foo_name,
            "amount": str(liquid_offer_amount + 1000),
        }
    )

    # Make liquid offer (locks PFAND)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeOffer",
            "maker": accounts["alice_addr"],
            "have": {"denom": liquid_foo, "amount": str(liquid_offer_amount)},
            "want": {"denom": bar_name, "amount": str(liquid_offer_amount)},
        }
    )

    # Drain alice's liquid balance below unit_have (send to bob)
    actual_drain = liquid_offer_amount + 1000
    messages.append(
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": accounts["alice_addr"],
            "to_address": accounts["bob_addr"],
            "amount": [{"denom": liquid_foo, "amount": str(actual_drain)}],
        }
    )

    # Third-party cancel (bob recovers PFAND)
    messages.append(
        {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCancelOffer",
            "closer": accounts["bob_addr"],
            "offer_id": "{{ msg_2['offer_id'] }}",
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
    assert result["message_count"] == 5
