import json
import pytest


def test_make_trade_duplicate_pool_id_fails(chainnet, ws_setup_env):
    """Verify that MakeTrade rejects duplicate pool_id in operations."""
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]

    # Create pool a/b
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        taker_name,
    )
    assert txp["code"] == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"
    events = {e["type"]: e for e in txp["events"]}
    et = "dysonprotocol.whaleswap.v1.EventPoolCreated"
    assert et in events
    attrs = {a["key"]: a["value"] for a in events[et]["attributes"]}
    pid = int(json.loads(attrs["pool_id"]))
    assert pid > 0

    # Attempt two legs on the same pool - should fail
    leg1 = {"swap": {"pool_id": pid, "swap_in": {"denom": a, "amount": "5"}}}
    leg2 = {"swap": {"pool_id": pid, "swap_in": {"denom": a, "amount": "5"}}}

    with pytest.raises(Exception, match="duplicate pool_id"):
        dysond(
            "tx",
            "whaleswap",
            "make-trade",
            "--max-input",
            f"10{a}",
            "--op",
            json.dumps(leg1),
            "--op",
            json.dumps(leg2),
            "--from",
            taker_name,
            "--gas",
            "auto",
        )


def test_make_trade_duplicate_offer_id_fails(chainnet, ws_setup_env, ws_create_offer):
    """Verify that MakeTrade rejects duplicate offer_id in operations."""
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]
    maker_name = env["acc2"]["name"]

    # Maker creates offer
    offer_id = ws_create_offer(
        maker_name,
        have=f"100{a}",
        want=f"10{b}",
    )

    # Attempt two takes on the same offer - should fail
    take1 = {"take": {"offer_id": offer_id, "take_units": "1"}}
    take2 = {"take": {"offer_id": offer_id, "take_units": "1"}}

    with pytest.raises(Exception, match="duplicate offer_id"):
        dysond(
            "tx",
            "whaleswap",
            "make-trade",
            "--max-input",
            f"20{b}",
            "--op",
            json.dumps(take1),
            "--op",
            json.dumps(take2),
            "--from",
            taker_name,
            "--gas",
            "auto",
        )
