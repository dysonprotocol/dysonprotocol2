"""
Test that MakeTrade properly accounts for pfand release when taking an offer that closes.

When a liquid offer closes, pfand is released from module to taker.
This must be accounted as both:
- module input (pfand leaving module balance)
- taker output (taker receiving pfand)

Without the module input, the invariant check fails with a balance mismatch.
"""

import json


def test_make_trade_pfand_release_accounting(
    chainnet, generate_account, faucet, register_name
):
    """
    Reproduce pfand accounting bug when MakeTrade closes a liquid offer.

    Setup:
    1. Register name alice.dys, mint solid coins
    2. Alice makes liquid offer (locks pfand)
    3. Bob takes offer via MakeTrade with enough units to close it

    Expected:
    - Pfand should be released to Bob (taker)
    - Module balance should decrease by pfand amount
    - Invariant should pass

    Bug reproduces when module input for pfand release is missing.
    """
    dysond = chainnet[0]

    # Setup accounts
    [alice_name, alice_addr] = generate_account("pfand_alice")
    [bob_name, bob_addr] = generate_account("pfand_bob")
    faucet(alice_addr, amount=1_000_000)
    faucet(bob_addr, amount=1_000_000)

    # Register alice.dys and mint solid coins
    name = register_name(dysond, alice_name, alice_addr, "100udys")

    mint_amt = "1000"
    mint_fee_amt = "10"
    mint_tx = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{mint_amt}{name}",
        "--mint-fee",
        f"{mint_fee_amt}udys",
        "--from",
        alice_name,
        "-y",
    )
    assert mint_tx.get("code", 1) == 0

    # Send some solid alice.dys to Bob for want payment
    send_tx = dysond(
        "tx",
        "bank",
        "send",
        alice_name,
        bob_addr,
        f"500{name}",
        "--from",
        alice_name,
        "-y",
    )
    assert send_tx.get("code", 1) == 0

    # Convert some alice.dys to liquid for Alice's offer
    liquid_denom = f"whaleswap.dys/coins/{name}"
    convert_amt = "200"
    convert_tx = dysond(
        "tx",
        "whaleswap",
        "convert-to-liquid",
        "--denom",
        name,
        "--amount",
        convert_amt,
        "--from",
        alice_name,
        "-y",
    )
    assert convert_tx.get("code", 1) == 0

    # Alice makes liquid offer: have 100 liquid alice.dys, want 100 udys
    # This locks pfand (100 solid alice.dys in module)
    have_amt = 100
    want_amt = 100
    tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"{have_amt}{liquid_denom}",
        "--want",
        f"{want_amt}udys",
        "--from",
        alice_name,
        "-y",
    )
    assert tx.get("code", 1) == 0

    # Extract offer_id from events
    offer_created = [
        e
        for e in tx["events"]
        if e["type"] == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    assert len(offer_created) == 1
    offer_id = int(
        [a["value"] for a in offer_created[0]["attributes"] if a["key"] == "offer_id"][
            0
        ]
    )

    # Query offer to verify pfand locked
    offer_query = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    offer = offer_query["offer"]
    # Pfand denom is always whaleswap.dys/pfand (synthetic denom)
    assert offer["pfand_locked"]["denom"] == "whaleswap.dys/pfand"
    pfand_amount = int(offer["pfand_locked"]["amount"])
    # For liquid offers, pfand should equal the have amount in solid denom
    assert pfand_amount == have_amt, f"Expected pfand {have_amt}, got {pfand_amount}"

    # Get module balance before take
    module_addr = dysond("query", "whaleswap", "module-address")["address"]
    mod_bal_before = dysond("query", "bank", "balance", module_addr, name)
    mod_alice_dys_before = int(mod_bal_before["balance"]["amount"])

    # Bob takes ENTIRE offer via MakeTrade (closes it, triggers pfand release)
    # This will FAIL with invariant error if pfand accounting is broken
    take_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--from",
        bob_name,
        "--max-input",
        f"{want_amt}udys",
        "--op",
        f'{{"take": {{"offer_id": "{offer_id}"}}}}',
        "-y",
        "--gas",
        "auto",
    )

    # Verify transaction succeeded (if bug exists, invariant will fail here)
    assert (
        take_tx["code"] == 0
    ), f"Transaction failed: {take_tx.get('raw_log', take_tx)}"

    # Verify pfand was released in events
    pfand_events = [
        e
        for e in take_tx["events"]
        if e["type"] == "dysonprotocol.whaleswap.v1.EventPfandReleased"
    ]
    assert len(pfand_events) == 1
    pfand_attr = [a for a in pfand_events[0]["attributes"] if a["key"] == "amount"][0]
    pfand_coins = json.loads(pfand_attr["value"])
    pfand_released_amt = int(pfand_coins[0]["amount"])
    assert pfand_released_amt == pfand_amount

    # Verify module balance decreased by pfand amount
    mod_bal_after = dysond("query", "bank", "balance", module_addr, name)
    mod_alice_dys_after = int(mod_bal_after["balance"]["amount"])

    expected_decrease = pfand_amount
    actual_decrease = mod_alice_dys_before - mod_alice_dys_after
    assert (
        actual_decrease == expected_decrease
    ), f"Module balance change mismatch: expected decrease of {expected_decrease}, got {actual_decrease}"

    # Verify Bob received pfand
    bob_bal = dysond("query", "bank", "balance", bob_addr, name)
    bob_alice_dys = int(bob_bal["balance"]["amount"])
    # Bob started with 500, received 100 from offer + 100 pfand = 700
    expected_bob = 500 + have_amt + pfand_amount
    assert (
        bob_alice_dys == expected_bob
    ), f"Bob balance mismatch: expected {expected_bob}, got {bob_alice_dys}"
