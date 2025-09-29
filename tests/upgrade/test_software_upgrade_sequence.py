import json
import tempfile

from tests.utils import poll_until_condition


def _get_gov_addr(dysond):
    res = dysond("query", "auth", "module-account", "gov")
    return res.get("account", {}).get("value", {}).get("address", "")


def _submit_upgrade(dysond, gov_address: str, name: str, height: int):
    proposal = {
        "messages": [
            {
                "@type": "/cosmos.upgrade.v1beta1.MsgSoftwareUpgrade",
                "authority": gov_address,
                "plan": {"name": name, "height": str(height)},
            }
        ],
        "metadata": "test",
        "deposit": "2udys",
        "title": f"Upgrade to {name}",
        "summary": f"Schedule upgrade {name}",
        "expedited": True,
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=True) as fp:
        json.dump(proposal, fp)
        fp.flush()
        return dysond("tx", "gov", "submit-proposal", fp.name, "--from", "alice")


def _extract_proposal_id(tx_result: dict) -> str:
    events = tx_result.get("events", [])
    attrs = [
        a.get("value")
        for e in events
        if e.get("type") == "submit_proposal"
        for a in e.get("attributes", [])
        if a.get("key") == "proposal_id"
    ]
    assert len(attrs) > 0, f"proposal_id not found: {json.dumps(events, indent=2)}"
    return attrs[0]


def _vote_yes(dysond, proposal_id: str):
    return dysond("tx", "gov", "vote", proposal_id, "yes", "--from", "alice")


def _delegate_voting_power_from_alice(dysond, amount: str = "50000000udys"):
    vals = dysond("query", "staking", "validators")
    op = vals["validators"][0]["operator_address"]
    tx = dysond("tx", "staking", "delegate", op, amount, "--from", "alice")
    assert tx.get("code", 1) == 0, f"delegation failed: {tx}"


def _calc_plan_offset_blocks(dysond) -> int:
    params = dysond("query", "gov", "params")["params"]
    # expedited_voting_period like "5s"; default block time ~0.6s per chainnet config
    exp_s = int(params["expedited_voting_period"].removesuffix("s") or "5")
    blocks_for_vote = (exp_s + 0) / 0.5
    # add small margin for commit + restart
    return int(blocks_for_vote + 7)


def _wait_passed(dysond, proposal_id: str):
    poll_until_condition(
        lambda: dysond("query", "gov", "proposal", proposal_id)["proposal"]["status"]
        in [
            "PROPOSAL_STATUS_PASSED",
            "PROPOSAL_STATUS_REJECTED",
            "PROPOSAL_STATUS_FAILED",
        ],
        timeout=10,
        poll_interval=0.2,
    )
    proposal_json = dysond("query", "gov", "proposal", proposal_id)
    status = proposal_json["proposal"]["status"]
    current_height = int(dysond("status")["sync_info"]["latest_block_height"])
    # Assert expedited governance knobs match our assumptions
    gov_params = dysond("query", "gov", "params")["params"]
    assert (
        gov_params["expedited_voting_period"] == "5s"
    ), "unexpected expedited_voting_period: " + json.dumps(gov_params, indent=2)
    assert (
        gov_params["expedited_min_deposit"][0]["amount"] == "2"
    ), "unexpected expedited_min_deposit"
    assert status == "PROPOSAL_STATUS_PASSED", (
        "gov proposal did not pass: "
        + status
        + " | final_tally="
        + json.dumps(proposal_json.get("proposal", {}).get("final_tally_result", {}))
        + " | current_height="
        + str(current_height)
        + " | proposal="
        + json.dumps(proposal_json, indent=2)
    )


def _wait_applied(dysond, name: str, target_height: int):
    def _applied():
        ap = dysond("query", "upgrade", "applied", name, raw=True)
        print(f"applied: {ap}")
        return isinstance(ap, dict) and int(ap.get("height", "0")) >= target_height

    poll_until_condition(_applied, timeout=15, poll_interval=0.2)


def _assert_current_plan(dysond, name: str, height: int):
    cp = dysond("query", "upgrade", "plan")
    plan = cp.get("plan", {})
    print(f"current-plan: {plan}")
    assert (
        plan.get("name") == name
    ), f"current-plan name mismatch: {json.dumps(cp, indent=2)}"
    assert (
        int(plan.get("height", "0")) == height
    ), f"current-plan height mismatch: {json.dumps(cp, indent=2)}"


def _assert_applied(dysond, name: str, height: int):
    ap = dysond("query", "upgrade", "applied", name)
    assert (
        int(ap.get("height", "0")) == height
    ), f"applied-plan mismatch: {json.dumps(ap, indent=2)}"


def test_upgrade_sequence_expedited(chainnet):
    dysond = chainnet[0]
    gov_addr = _get_gov_addr(dysond)
    assert (
        isinstance(gov_addr, str) and len(gov_addr) > 0
    ), "gov module address not found"

    # Ensure Alice holds voting power to pass proposals quickly
    _delegate_voting_power_from_alice(dysond)

    # 1) Upgrade to test-foo
    h_now = int(dysond("status")["sync_info"]["latest_block_height"])
    t1 = h_now + _calc_plan_offset_blocks(dysond)
    tx1 = _submit_upgrade(dysond, gov_addr, "test-foo", t1)
    assert (
        tx1["code"] == 0
    ), f"submit-proposal test-foo failed: {json.dumps(tx1, indent=2)}"
    pid1 = _extract_proposal_id(tx1)
    v1 = _vote_yes(dysond, pid1)
    assert v1["code"] == 0, f"vote test-foo failed: {json.dumps(v1, indent=2)}"
    _wait_passed(dysond, pid1)
    _assert_current_plan(dysond, "test-foo", t1)
    h_pass = int(dysond("status")["sync_info"]["latest_block_height"])
    remaining = t1 - h_pass
    assert (
        remaining >= 3
    ), f"not enough blocks remaining to reach upgrade height: remaining={remaining}, h_pass={h_pass}, t1={t1}"
    _wait_applied(dysond, "test-foo", t1)
    _assert_applied(dysond, "test-foo", t1)

    # 2) Upgrade to test-bar
    h_now = int(dysond("status")["sync_info"]["latest_block_height"])
    t2 = h_now + _calc_plan_offset_blocks(dysond)
    tx2 = _submit_upgrade(dysond, gov_addr, "test-bar", t2)
    assert (
        tx2["code"] == 0
    ), f"submit-proposal test-bar failed: {json.dumps(tx2, indent=2)}"
    pid2 = _extract_proposal_id(tx2)
    v2 = _vote_yes(dysond, pid2)
    assert v2["code"] == 0, f"vote test-bar failed: {json.dumps(v2, indent=2)}"
    _wait_passed(dysond, pid2)
    _assert_current_plan(dysond, "test-bar", t2)
    h_pass = int(dysond("status")["sync_info"]["latest_block_height"])
    remaining = t2 - h_pass
    assert (
        remaining >= 3
    ), f"not enough blocks remaining to reach upgrade height: remaining={remaining}, h_pass={h_pass}, t2={t2}"
    _wait_applied(dysond, "test-bar", t2)
    _assert_applied(dysond, "test-bar", t2)

    # 3) Upgrade back to test-foo variant (name reuse is disallowed by SDK)
    h_now = int(dysond("status")["sync_info"]["latest_block_height"])
    t3 = h_now + _calc_plan_offset_blocks(dysond)
    tx3 = _submit_upgrade(dysond, gov_addr, "test-baz", t3)
    assert (
        tx3["code"] == 0
    ), f"submit-proposal test-baz failed: {json.dumps(tx3, indent=2)}"
    pid3 = _extract_proposal_id(tx3)
    v3 = _vote_yes(dysond, pid3)
    assert v3["code"] == 0, f"vote test-baz failed: {json.dumps(v3, indent=2)}"
    _wait_passed(dysond, pid3)
    _assert_current_plan(dysond, "test-baz", t3)
    h_pass = int(dysond("status")["sync_info"]["latest_block_height"])
    remaining = t3 - h_pass
    assert (
        remaining >= 3
    ), f"not enough blocks remaining to reach upgrade height: remaining={remaining}, h_pass={h_pass}, t3={t3}"
    _wait_applied(dysond, "test-baz", t3)
    _assert_applied(dysond, "test-baz", t3)
