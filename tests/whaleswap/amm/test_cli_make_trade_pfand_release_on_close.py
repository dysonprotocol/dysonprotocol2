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
    la = env["liquid_denoms"][0]

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

    # Maker creates an offer with have as liquid a, want as 1 udys per unit (3 units total)
    mk = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"12{la}",
        "--want",
        "3udys",
        "--from",
        maker,
    )
    assert mk.get("code", 1) == 0, f"make-offer failed: {json.dumps(mk, indent=2)}"
    offer_id = _extract_offer_id(mk)

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
        "--gas",
        "auto",
    )
    assert t1.get("code", 1) == 0, f"partial take failed: {json.dumps(t1, indent=2)}"
    q1 = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_id))
    assert isinstance(q1, dict), f"bad offer query: {q1}"
    offer1 = q1.get("offer", {})
    assert offer1.get("status") == "open", f"expected open: {json.dumps(q1, indent=2)}"

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
        "--gas",
        "auto",
    )
    assert t2.get("code", 1) == 0, f"close take failed: {json.dumps(t2, indent=2)}"

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
