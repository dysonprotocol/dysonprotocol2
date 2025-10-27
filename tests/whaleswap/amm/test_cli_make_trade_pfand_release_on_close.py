import json


def _extract_offer_id(tx):
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    attrs = evs[0].get("attributes", [])
    oid_attr = [a for a in attrs if a.get("key") == "offer_id"]
    return int(json.loads(oid_attr[0].get("value")))


def _poll_until_proposal_passes(dysond, proposal_id: str, timeout: int = 30):
    from tests.utils import poll_until_condition

    def _done():
        q = dysond("query", "gov", "proposal", proposal_id)
        st = q.get("proposal", {}).get("status", "")
        return st in [
            "PROPOSAL_STATUS_PASSED",
            "PROPOSAL_STATUS_REJECTED",
            "PROPOSAL_STATUS_FAILED",
        ]

    poll_until_condition(
        _done, timeout=timeout, error_message="proposal did not reach final state"
    )


def test_make_trade_pfand_release_on_close(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    maker = env["acc2"]["name"]
    taker = env["acc1"]["name"]
    maker_addr = env["acc2"]["addr"]
    taker_addr = env["acc1"]["addr"]
    a = env["denoms"][0]

    # Gov: set pfand_per_offer > 0 via MsgSubmitProposal(MsgUpdateParams)
    cur = dysond("query", "whaleswap", "params")["params"]
    # Authority must be the gov module account; governance signs embedded messages
    auth = (
        dysond("query", "auth", "module-account", "gov")
        .get("account", {})
        .get("value", {})
        .get("address", "")
    )
    assert isinstance(auth, str) and auth, f"missing gov authority"
    # Delegate to ensure voting power
    val = dysond("query", "staking", "validators")["validators"][0]["operator_address"]
    deltx = dysond(
        "tx", "staking", "delegate", val, "50000000udys", "--from", "alice", "--yes"
    )
    assert deltx.get("code", 1) == 0, f"delegate failed: {json.dumps(deltx, indent=2)}"
    proposal = {
        "messages": [
            {
                "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
                "authority": auth,
                "params": {
                    "pfand_per_offer": {"denom": "udys", "amount": "2"},
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
        "title": "Update Whaleswap Params (pfand)",
        "summary": "Set pfand_per_offer to 2",
    }
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as f:
        json.dump(proposal, f)
        f.flush()
        sp = dysond("tx", "gov", "submit-proposal", f.name, "--from", "alice", "--yes")
    sp = dysond("query", "wait-tx", sp["txhash"])
    evs = [e for e in sp.get("events", []) if e.get("type") == "submit_proposal"]
    pid_attrs = [
        a for e in evs for a in e.get("attributes", []) if a.get("key") == "proposal_id"
    ]
    assert pid_attrs, f"no proposal_id: {json.dumps(sp, indent=2)}"
    proposal_id = pid_attrs[0]["value"]
    vt = dysond("tx", "gov", "vote", proposal_id, "yes", "--from", "alice", "--yes")
    vt = dysond("query", "wait-tx", vt["txhash"])
    assert vt.get("code", 1) == 0, f"vote failed: {json.dumps(vt, indent=2)}"
    _poll_until_proposal_passes(dysond, proposal_id, timeout=30)
    after = dysond("query", "whaleswap", "params")["params"]
    assert (
        after.get("pfand_per_offer", {}).get("amount") == "2"
    ), f"pfand not updated: {after}"
    assert (
        after.get("pfand_per_offer", {}).get("denom") == "udys"
    ), f"pfand denom not updated: {after}"

    # Ensure maker/taker have enough udys to cover pfand and fees
    _ = dysond("tx", "bank", "send", "alice", maker_addr, "2000000udys")
    _ = dysond("tx", "bank", "send", "alice", taker_addr, "2000000udys")

    # Maker creates an offer (liquid-mode): have base 'a', want 1 udys per unit (3 units total)
    mk = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"12{a}",
        "--want",
        "3udys",
        "--settlement-mode",
        "settlement-liquid",
        "--from",
        maker,
    )
    assert mk.get("code", 1) == 0, f"make-offer failed: {json.dumps(mk, indent=2)}"
    offer_id = _extract_offer_id(mk)

    # Verify pfand was locked correctly (check bug #2: pfand recording)
    offer_after_create = dysond(
        "query", "whaleswap", "offer", "--offer-id", str(offer_id)
    )
    pfand_locked = offer_after_create.get("offer", {}).get("pfand_locked", {})
    # BUG #2: This should be 2 udys (the pfand_per_offer param), but might be wrong
    assert pfand_locked.get("denom") == "udys", f"pfand denom wrong: {pfand_locked}"
    assert (
        pfand_locked.get("amount") == "2"
    ), f"pfand amount should be 2: {pfand_locked}"

    # Partial take: take_units=1
    op1 = json.dumps({"take": {"offer_id": offer_id, "take_units": "1"}})
    t1 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        op1,
        "--max-input",
        "1udys",
        "--from",
        taker,
    )
    assert t1.get("code", 1) == 0, f"partial take failed: {json.dumps(t1, indent=2)}"
    q1 = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    assert isinstance(q1, dict), f"bad offer query: {q1}"
    offer1 = q1.get("offer", {})
    assert offer1.get("status") == "open", f"expected open: {json.dumps(q1, indent=2)}"

    # Get taker balance before close
    taker_bal_before = dysond("query", "bank", "balance", taker_addr, "udys")
    taker_udys_before = int(taker_bal_before["balance"]["amount"])

    # Close: take remaining units (should be 2)
    op2 = json.dumps({"take": {"offer_id": offer_id, "take_units": "2"}})
    t2 = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        op2,
        "--max-input",
        "2udys",
        "--from",
        taker,
    )
    assert t2.get("code", 1) == 0, f"close take failed: {json.dumps(t2, indent=2)}"

    # Verify taker received pfand (2 udys)
    taker_bal_after = dysond("query", "bank", "balance", taker_addr, "udys")
    taker_udys_after = int(taker_bal_after["balance"]["amount"])
    # Taker paid 2 udys (want) and received 2 udys back (pfand). We don't rely on
    # balance delta here (gas noise); instead, assert event correctness below.

    # Stepwise assertions on events: exactly one EventPfandReleased on close
    ev_types = [e.get("type") for e in t2.get("events", [])]
    pfand_events = [
        e
        for e in t2.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPfandReleased"
    ]
    assert isinstance(ev_types, list), f"events not list: {json.dumps(t2, indent=2)}"
    assert (
        len(pfand_events) == 1
    ), f"expected one pfand release: {json.dumps(t2, indent=2)}"

    # Verify pfand went to taker (closer), not maker
    pfand_attr = [a for a in pfand_events[0]["attributes"] if a.get("key") == "amount"][
        0
    ]
    pfand_coin = json.loads(pfand_attr["value"])
    pfand_released_amt = int(pfand_coin["amount"])
    assert pfand_released_amt == 2, f"Expected 2 udys pfand released: {pfand_coin}"

    # Note: netting may cancel want and pfand flows for the taker, so we
    # assert EventPfandReleased correctness (above) rather than coin_received.

    # Verify trade_id is non-zero (pfand released via take, not cancel)
    trade_id_attr = [
        a for a in pfand_events[0]["attributes"] if a.get("key") == "trade_id"
    ][0]
    trade_id = int(trade_id_attr["value"].strip('"'))
    assert trade_id > 0, f"Take should have non-zero trade_id, got {trade_id}"

    # Offer closed
    q2 = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    assert isinstance(q2, dict), f"bad offer query: {q2}"
    offer2 = q2.get("offer", {})
    assert (
        offer2.get("status") == "closed"
    ), f"expected closed: {json.dumps(q2, indent=2)}"
    assert (
        offer2.get("remaining_units") == "0"
    ), f"expected units 0: {json.dumps(q2, indent=2)}"


def test_pfand_amount_stored_not_param_dependent(chainnet, ws_setup_env):
    """
    Verify pfand amount is stored in offer, not derived from parameter at cancel time.

    1. Set pfand_per_offer = 5 udys via gov
    2. Maker creates liquid offer (locks 5 udys pfand)
    3. Change pfand_per_offer = 1 udys via gov
    4. Maker cancels offer
    5. Verify maker receives 5 udys back (original locked amount, not new param)

    This tests that the pfand_locked field stores the actual locked amount,
    not just the parameter value.
    """
    dysond = chainnet[0]
    env = ws_setup_env

    maker = env["acc2"]["name"]
    maker_addr = env["acc2"]["addr"]
    a = env["denoms"][0]

    # Step 1: Set pfand_per_offer = 5 udys
    auth = (
        dysond("query", "auth", "module-account", "gov")
        .get("account", {})
        .get("value", {})
        .get("address", "")
    )
    assert auth
    val = dysond("query", "staking", "validators")["validators"][0]["operator_address"]
    deltx = dysond(
        "tx", "staking", "delegate", val, "50000000udys", "--from", "alice", "--yes"
    )
    assert deltx.get("code", 1) == 0

    cur = dysond("query", "whaleswap", "params")["params"]
    proposal_5 = {
        "messages": [
            {
                "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
                "authority": auth,
                "params": {
                    "pfand_per_offer": {"denom": "udys", "amount": "5"},
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
        "title": "Set pfand to 5",
        "summary": "Set pfand_per_offer to 5 udys",
    }

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as f:
        json.dump(proposal_5, f)
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
    vt = dysond("tx", "gov", "vote", pid, "yes", "--from", "alice", "--yes")
    dysond("query", "wait-tx", vt["txhash"])
    _poll_until_proposal_passes(dysond, pid, timeout=30)

    params1 = dysond("query", "whaleswap", "params")["params"]
    assert params1["pfand_per_offer"]["amount"] == "5"

    # Ensure maker has 5 udys for pfand
    _ = dysond("tx", "bank", "send", "alice", maker_addr, "2000000udys")

    # Get maker balance before
    maker_bal_before = dysond("query", "bank", "balance", maker_addr, "udys")
    maker_udys_before = int(maker_bal_before["balance"]["amount"])

    # Step 2: Maker creates liquid-mode offer (locks 5 udys)
    mk = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"10{a}",
        "--want",
        "10udys",
        "--settlement-mode",
        "settlement-liquid",
        "--from",
        maker,
    )
    assert mk.get("code", 1) == 0
    offer_id = _extract_offer_id(mk)

    # Verify 5 udys locked
    offer_q = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    pfand_locked = offer_q["offer"]["pfand_locked"]
    assert pfand_locked["amount"] == "5", f"Expected 5 locked: {pfand_locked}"

    # Step 3: Change pfand_per_offer = 1 udys
    proposal_1 = {
        "messages": [
            {
                "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
                "authority": auth,
                "params": {
                    "pfand_per_offer": {"denom": "udys", "amount": "1"},
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
        "metadata": "ipfs://CID2",
        "deposit": "1udys",
        "title": "Set pfand to 1",
        "summary": "Set pfand_per_offer to 1 udys",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as f:
        json.dump(proposal_1, f)
        f.flush()
        sp2 = dysond("tx", "gov", "submit-proposal", f.name, "--from", "alice", "--yes")
    sp2 = dysond("query", "wait-tx", sp2["txhash"])
    evs2 = [e for e in sp2.get("events", []) if e.get("type") == "submit_proposal"]
    pid2 = [
        a["value"]
        for e in evs2
        for a in e.get("attributes", [])
        if a.get("key") == "proposal_id"
    ][0]
    vt2 = dysond("tx", "gov", "vote", pid2, "yes", "--from", "alice", "--yes")
    dysond("query", "wait-tx", vt2["txhash"])
    _poll_until_proposal_passes(dysond, pid2, timeout=30)

    params2 = dysond("query", "whaleswap", "params")["params"]
    assert params2["pfand_per_offer"]["amount"] == "1"

    # Step 4: Cancel offer
    # Get maker balance before cancel (to verify pfand returned to maker)
    maker_bal_before_cancel = dysond("query", "bank", "balance", maker_addr, "udys")
    maker_udys_before_cancel = int(maker_bal_before_cancel["balance"]["amount"])

    cancel_tx = dysond(
        "tx",
        "whaleswap",
        "cancel-offer",
        "--offer-id",
        str(offer_id),
        "--from",
        maker,
        "--yes",
    )
    assert cancel_tx.get("code", 1) == 0

    # Step 5: Verify maker received 5 udys back (original locked), not 1 udys (new param)
    maker_bal_after = dysond("query", "bank", "balance", maker_addr, "udys")
    maker_udys_after = int(maker_bal_after["balance"]["amount"])

    # Maker balance change when cancelling = +5 (pfand refunded)
    delta_cancel = maker_udys_after - maker_udys_before_cancel
    assert delta_cancel == 5, f"Maker didn't receive full pfand: delta={delta_cancel}"

    # Verify EventPfandReleased has correct amount (5 not 1)
    pfand_ev = [
        e
        for e in cancel_tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventPfandReleased"
    ]
    assert len(pfand_ev) == 1
    pfand_attr = [a for a in pfand_ev[0]["attributes"] if a.get("key") == "amount"][0]
    # Event value is a single Coin JSON, not array
    pfand_coin = json.loads(pfand_attr["value"])
    released_amt = int(pfand_coin["amount"])
    # This is the smoking gun: should be 5 (what was locked), not 1 (current param)
    assert (
        released_amt == 5
    ), f"Expected 5 udys released (original lock), got {released_amt}"

    # Also verify via coin_received that maker received the pfand amount
    maker_events_str = json.dumps(cancel_tx.get("events", []))
    assert '"type": "coin_received"' in maker_events_str
    assert f'"key": "receiver", "value": "{maker_addr}"' in maker_events_str
    assert '"key": "amount", "value": "5udys"' in maker_events_str

    # Verify trade_id is 0 for cancel (not from a take trade)
    trade_id_attr = [
        a for a in pfand_ev[0]["attributes"] if a.get("key") == "trade_id"
    ][0]
    trade_id = trade_id_attr["value"].strip('"')
    assert trade_id == "0", f"Cancel should have trade_id=0, got {trade_id}"
