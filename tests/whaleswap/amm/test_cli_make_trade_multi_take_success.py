import json


def _take(offer_id, units):
    return {"take": {"offer_id": str(offer_id), "take_units": str(units)}}


def test_make_trade_multi_take_success(chainnet, ws_setup_env, ws_create_offer, faucet):
    """
    Test that multi-take MakeTrade operations work correctly.

    Previously this reproduced a bug where multi-take accounting would forget
    some taker inputs, causing module balance mismatch for udys.

    Error: invariant after MakeTrade: module balance mismatch for udys:
    have=3185276540 expected=3185276780
    (amm=2654397318 escrow=265439731 auction=265439731 pfand=<nil> liquid_backing=0)

    Module SHORT 240 udys after multi-take make-trade.

    This test now verifies the bug has been fixed.
    """
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    taker = env["acc1"]["name"]
    taker_addr = env["acc1"]["addr"]
    maker = env["acc2"]["name"]

    # Create three solid-have offers
    # Offer 1: 100a for 104udys  -> unit 25a / 26udys (3 units taken = 78udys want)
    o1 = ws_create_offer(maker, have=f"100{a}", want="104udys")
    # Offer 2: 88a for 75udys   -> unit 88a / 75udys (1 unit taken = 75udys want)
    o2 = ws_create_offer(maker, have=f"88{a}", want="75udys")
    # Offer 3: 77a for 87udys   -> unit 77a / 87udys (1 unit taken = 87udys want)
    o3 = ws_create_offer(maker, have=f"77{a}", want="87udys")

    # Ensure taker has sufficient udys for coverage
    faucet(taker_addr, amount=1_000_000)

    # Single MakeTrade with three take operations
    # Expected want total: 78 + 75 + 87 = 240 udys
    # Should succeed now that the accounting bug is fixed
    result = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--from",
        taker,
        "--max-input",
        "300udys",
        "--op",
        json.dumps(_take(o1, 3)),
        "--op",
        json.dumps(_take(o2, 1)),
        "--op",
        json.dumps(_take(o3, 1)),
        "--gas",
        "auto",
    )

    # Transaction should succeed (the bug that caused invariant failure has been fixed)
    assert result["code"] == 0, f"MakeTrade failed: {json.dumps(result, indent=2)}"

    # Transaction succeeded - the multi-take accounting bug has been fixed
    # Invariants passed, confirming the module balance is correct
