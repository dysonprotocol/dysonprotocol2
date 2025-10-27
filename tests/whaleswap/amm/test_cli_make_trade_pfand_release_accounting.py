"""
Test that MakeTrade properly accounts for pfand release when taking an offer that closes.

When a liquid offer closes, pfand is released from module to taker.
This must be accounted as both:
- module input (pfand leaving module balance)
- taker output (taker receiving pfand)

Without the module input, the invariant check fails with a balance mismatch.
"""

import json
from utils import poll_until_condition
from tests.whaleswap.amm.normalize_events import normalize_events


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

    # Set pfand_per_offer to 100 udys via governance proposal
    gov_auth = (
        dysond("query", "auth", "module-account", "gov")
        .get("account", {})
        .get("value", {})
        .get("address", "")
    )
    assert gov_auth

    # Give alice voting power by delegating
    val = dysond("query", "staking", "validators")["validators"][0]["operator_address"]
    deltx = dysond(
        "tx", "staking", "delegate", val, "50000000udys", "--from", "alice", "--yes"
    )
    assert deltx.get("code", 1) == 0

    # Get current params and create proposal to set pfand_per_offer
    cur = dysond("query", "whaleswap", "params")["params"]
    proposal = {
        "messages": [
            {
                "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
                "authority": gov_auth,
                "params": {
                    "pfand_per_offer": {"denom": "udys", "amount": "100"},
                    "valuation_fee_pct": cur.get("valuation_fee_pct", "0"),
                    "valuation_period": cur.get("valuation_period", "1h0m0s"),
                    "bid_timeout": cur.get("bid_timeout", "5s"),
                    "minimum_bid_percent_increase": cur.get(
                        "minimum_bid_percent_increase", "0"
                    ),
                    "max_note_length": cur.get("max_note_length", 128),
                    "block_delay_before_close": cur.get(
                        "block_delay_before_close", "1"
                    ),
                    "block_delay_before_liquidation": cur.get(
                        "block_delay_before_liquidation", "1"
                    ),
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "1udys",
        "title": "Set pfand to 100",
        "summary": "Set pfand_per_offer to 100 udys",
    }

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as f:
        json.dump(proposal, f)
        f.flush()
        sp = dysond("tx", "gov", "submit-proposal", f.name, "--from", "alice", "--yes")

    sp = dysond("query", "wait-tx", sp["txhash"])
    evs = [e for e in sp.get("events", []) if e.get("type") == "submit_proposal"]
    pid = [
        a["value"]
        for e in evs
        for a in e.get("attributes", [])
        if a.get("key") == "proposal_id"
    ][0]

    # Vote yes
    vt = dysond("tx", "gov", "vote", str(pid), "yes", "--from", "alice", "--yes")
    dysond("query", "wait-tx", vt["txhash"])

    # Wait for proposal to reach final state
    def _final():
        p = dysond("query", "gov", "proposal", str(pid))
        status = p.get("proposal", {}).get("status", "")
        return status in [
            "PROPOSAL_STATUS_PASSED",
            "PROPOSAL_STATUS_REJECTED",
            "PROPOSAL_STATUS_FAILED",
        ]

    poll_until_condition(
        _final, timeout=60, poll_interval=2, error_message="Proposal did not finalize"
    )

    # Verify proposal passed
    final_prop = dysond("query", "gov", "proposal", str(pid))
    final_status = final_prop.get("proposal", {}).get("status", "")
    assert (
        final_status == "PROPOSAL_STATUS_PASSED"
    ), f"Proposal did not pass, status: {final_status}"

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

    # Alice makes liquid-mode offer: have 100 alice.dys (base), want 100 udys
    # This locks pfand (100 udys as configured in pfand_per_offer parameter)
    have_amt = 100
    want_amt = 100
    tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"{have_amt}{name}",
        "--want",
        f"{want_amt}udys",
        "--settlement-mode",
        "settlement-liquid",
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
    # Pfand denom is configured via pfand_per_offer parameter (set to udys in this test)
    assert offer["pfand_locked"]["denom"] == "udys"
    pfand_amount = int(offer["pfand_locked"]["amount"])
    # Pfand amount equals the pfand_per_offer parameter amount (100 udys)
    assert pfand_amount == have_amt, f"Expected pfand {have_amt}, got {pfand_amount}"

    # Get module udys balance before take (pfand denom)
    module_addr = dysond("query", "auth", "module-account", "whaleswap")["account"][
        "value"
    ]["address"]
    mod_bal_before = dysond("query", "bank", "balance", module_addr, "udys")
    mod_udys_before = int(mod_bal_before["balance"]["amount"])

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
    )

    # Verify transaction succeeded (if bug exists, invariant will fail here)
    assert (
        take_tx["code"] == 0
    ), f"Transaction failed: {take_tx.get('raw_log', take_tx)}"

    # Verify pfand was released in events
    evdict = normalize_events(take_tx["events"])
    etype = "dysonprotocol.whaleswap.v1.EventPfandReleased"
    assert etype in evdict, f"missing {etype}: {json.dumps(evdict, indent=2)}"
    pfand_rows = evdict[etype]
    assert (
        len(pfand_rows) == 1
    ), f"expected one {etype}, got {len(pfand_rows)}: {pfand_rows}"
    pfand_attrs = pfand_rows[0]
    assert "amount" in pfand_attrs, f"missing amount in pfand event: {pfand_attrs}"
    pfand_coin = pfand_attrs["amount"]
    pfand_released_amt = int(pfand_coin["amount"])
    assert pfand_released_amt == pfand_amount

    # Verify module udys balance decreased by pfand amount
    mod_bal_after = dysond("query", "bank", "balance", module_addr, "udys")
    mod_udys_after = int(mod_bal_after["balance"]["amount"])

    expected_decrease = pfand_amount
    actual_decrease = mod_udys_before - mod_udys_after
    assert (
        actual_decrease == expected_decrease
    ), f"Module balance change mismatch: expected decrease of {expected_decrease}, got {actual_decrease}"

    # Verify Bob received pfand (but netting cancels udys flows)
    bob_bal = dysond("query", "bank", "balance", bob_addr, name)
    bob_alice_dys = int(bob_bal["balance"]["amount"])
    # Bob started with 500, received 100 from offer (udys flows cancel due to netting)
    expected_bob = 500 + have_amt
    assert (
        bob_alice_dys == expected_bob
    ), f"Bob balance mismatch: expected {expected_bob}, got {bob_alice_dys}"
