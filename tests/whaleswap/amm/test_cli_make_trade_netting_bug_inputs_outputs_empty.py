import json


def _take(offer_id, units):
    return {"take": {"offer_id": str(offer_id), "take_units": str(units)}}


def test_make_trade_netting_bug_inputs_outputs_empty(
    chainnet, ws_setup_env, ws_create_offer
):
    """
    Test that reproduces the netting bug where inputs=1, outputs=0.

    This test creates a scenario where the netting logic results in unbalanced
    inputs and outputs, causing the "inputs/outputs cannot be empty" error.

    The bug occurs when:
    1. Trader has credits that can be netted against makers' wants
    2. The netting logic reduces trader outputs but doesn't properly balance inputs
    3. Result: inputs=1, outputs=0, which violates wsMoveCoins requirements
    """
    dysond = chainnet[0]
    env = ws_setup_env

    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    maker1_name = env["acc2"]["name"]
    maker2_name = env["acc3"]["name"]

    # Create two offers where the trader can net their outputs against makers' wants
    # This should create a scenario where netting results in inputs=1, outputs=0

    # Offer 1: Maker1 wants denom A, has denom B
    offer1 = ws_create_offer(maker1_name, have=f"100{b}", want=f"50{a}")

    # Offer 2: Maker2 wants denom B, has denom A
    offer2 = ws_create_offer(maker2_name, have=f"100{a}", want=f"50{b}")

    # Give the trader some of both denoms so they can net
    # This creates the scenario where the trader has credits that can be netted
    dysond(
        "tx",
        "bank",
        "send",
        maker1_name,
        taker_addr,
        f"10{b}",
        "--from",
        maker1_name,
        "--yes",
    )
    dysond(
        "tx",
        "bank",
        "send",
        maker2_name,
        taker_addr,
        f"10{a}",
        "--from",
        maker2_name,
        "--yes",
    )

    # Also give the trader some udys for gas and potential debits
    dysond(
        "tx",
        "bank",
        "send",
        "alice",
        taker_addr,
        "1000000udys",
        "--from",
        "alice",
        "--yes",
    )

    # Attempt a trade that should trigger the netting bug
    # The trader will take both offers, but the netting should result in unbalanced inputs/outputs
    result = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--from",
        taker_name,
        "--max-input",
        f"100{a}",
        "--max-input",
        f"100{b}",
        "--op",
        json.dumps(_take(offer1, 1)),
        "--op",
        json.dumps(_take(offer2, 1)),
        "--note",
        "Test netting bug reproduction",
    )

    # The trade should now succeed (the bug has been fixed)
    # Check that the trade completed successfully
    assert (
        result["code"] == 0
    ), f"Expected trade to succeed after fix, but got return code {result['code']}: {result['stderr']}"
