import json

from tests.whaleswap.amm.normalize_events import normalize_events
from tests.whaleswap.amm.parse_amounts_multi import sum_transfers_for_addr


def test_cycle_profit_offers_only(chainnet, ws_setup_env, ws_create_offer, faucet):
    dysond = chainnet[0]
    env = ws_setup_env

    owner = env["owner_name"]
    acc1 = env["acc1"]["name"]
    a, b, c = env["denoms"]
    taddr = env["acc1"]["addr"]

    # Makers: use acc2 and acc3 to host complementary offers
    maker1 = env["acc2"]["name"]
    maker2 = env["acc3"]["name"]

    # Create three offers forming A→B, B→C, C→A cycle with exact netting and +1A profit at end:
    # 10A -> 10B, 10B -> 10C, 10C -> 9A
    oid_ab = ws_create_offer(maker1, have=f"10{a}", want=f"10{b}")
    oid_bc = ws_create_offer(maker2, have=f"10{b}", want=f"10{c}")
    oid_ca = ws_create_offer(maker1, have=f"10{c}", want=f"9{a}")

    # Pre balances
    pre = dysond("query", "bank", "balances", taddr)
    assert isinstance(pre, dict) and isinstance(pre["balances"], list), json.dumps(
        pre, indent=2
    )
    pre_map = {row["denom"]: int(row["amount"]) for row in pre["balances"]}

    # MakeTrade: take one unit from each (no caps => zero by default; we only receive credits)
    # Take 10 units on AB and BC (gcd(10,10)=10 ⇒ unit=1; 10 units → 10 amounts),
    # and 1 unit on CA (gcd(10,9)=1 ⇒ unit=10C→9A). This nets to +1A, zero debits.
    op1 = json.dumps({"take": {"offer_id": oid_ab, "take_units": "10"}})
    op2 = json.dumps({"take": {"offer_id": oid_bc, "take_units": "10"}})
    op3 = json.dumps({"take": {"offer_id": oid_ca, "take_units": "1"}})

    tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        op1,
        "--op",
        op2,
        "--op",
        op3,
        "--min-output",
        f"1{a}",
        "--from",
        acc1,
    )
    assert isinstance(tx, dict), json.dumps(tx, indent=2)
    assert tx["code"] == 0, json.dumps(tx, indent=2)
    assert "events" in tx and isinstance(tx["events"], list), json.dumps(tx, indent=2)

    # 3 trades recorded for takes
    ev = normalize_events(tx["events"])
    et = "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    # Now 1 Trade with multiple operations, not multiple Trades
    assert (
        et in ev and len(ev[et]) == 1
    ), f"expected 1 EventTradeRecorded: {json.dumps(ev, indent=2)}"

    # Exact net flows
    debits, credits = sum_transfers_for_addr(tx, taddr)
    assert isinstance(debits, list) and isinstance(credits, list), json.dumps(
        [debits, credits], indent=2
    )
    assert debits == [], json.dumps([debits, credits], indent=2)
    cred_map = {}
    for amt, den in credits:
        cred_map[den] = cred_map.get(den, 0) + int(amt)

    # Post balances
    post = dysond("query", "bank", "balances", taddr)
    assert isinstance(post, dict) and isinstance(post["balances"], list), json.dumps(
        post, indent=2
    )
    post_map = {row["denom"]: int(row["amount"]) for row in post["balances"]}

    for d in [a, b, c]:
        assert (
            d in post_map and d in pre_map
        ), f"missing denom {d} in balances: pre={pre_map} post={post_map}"
        delta = post_map[d] - pre_map[d]
        exp = cred_map.get(d, 0)
        assert (
            delta == exp
        ), f"{d} delta mismatch: got {delta}, expected {exp}; transfers={json.dumps([debits, credits], indent=2)}"
