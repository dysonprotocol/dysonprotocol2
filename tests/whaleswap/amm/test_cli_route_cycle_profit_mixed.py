import json
from decimal import Decimal, ROUND_CEILING

from tests.whaleswap.amm.normalize_events import normalize_events
from tests.whaleswap.amm.parse_amounts_multi import sum_transfers_for_addr


def test_cycle_profit_mixed_swaps_offers(chainnet, ws_setup_env, ws_create_offer):
    dysond = chainnet[0]
    env = ws_setup_env

    acc1 = env["acc1"]["name"]
    taddr = env["acc1"]["addr"]
    a, b, c = env["denoms"]

    # Create two pools and one offer to complete the cycle
    # Pools: A/B and B/C with skew for favorable direction; Offer: C→A with slight edge
    creator = env["owner_name"]

    def _mint(denom, units):
        params = dysond("query", "nameservice", "params")
        assert isinstance(params, dict) and isinstance(
            params.get("params"), dict
        ), json.dumps(params, indent=2)
        fee_per = (
            Decimal(params["params"]["mint_fee_per_coin"])
            if params["params"].get("mint_fee_per_coin")
            else Decimal("0")
        )
        fee = int((Decimal(units) * fee_per).to_integral_value(rounding=ROUND_CEILING))
        res = dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{denom}",
            "--mint-fee",
            f"{fee}udys",
            "--from",
            creator,
        )
        assert isinstance(res, dict) and res["code"] == 0, json.dumps(res, indent=2)

    def _create_pool(denom_x, amt_x, denom_y, amt_y):
        _mint(denom_x, amt_x)
        _mint(denom_y, amt_y)
        tx = dysond(
            "tx",
            "whaleswap",
            "create-pool",
            "--coins",
            f"{amt_x}{denom_x}",
            "--coins",
            f"{amt_y}{denom_y}",
            "--from",
            creator,
        )
        assert isinstance(tx, dict) and tx["code"] == 0, json.dumps(tx, indent=2)
        ev = normalize_events(tx["events"])
        et = "dysonprotocol.whaleswap.v1.EventPoolCreated"
        assert et in ev and len(ev[et]) == 1, json.dumps(ev, indent=2)
        return int(ev[et][0]["pool_id"])

    ab = _create_pool(a, 100, b, 100000)
    bc = _create_pool(b, 100, c, 100000)

    # Offer: 101A -> 10C (edge): taker pays 10C (from swaps) and receives 101A
    oid_ca = ws_create_offer(env["acc2"]["name"], have=f"101{a}", want=f"10{c}")

    # Pre balances
    pre = dysond("query", "bank", "balances", taddr)
    assert isinstance(pre, dict) and isinstance(pre["balances"], list), json.dumps(
        pre, indent=2
    )
    pre_map = {row["denom"]: int(row["amount"]) for row in pre["balances"]}

    # Ops: swap A->B, swap B->C, then take A for C
    op1 = json.dumps({"swap": {"pool_id": ab, "swap_in": {"denom": a, "amount": "10"}}})
    op2 = json.dumps({"swap": {"pool_id": bc, "swap_in": {"denom": b, "amount": "10"}}})
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

    # Expect 2 pool swaps and 3 trades total (2 swaps + 1 take)
    ev = normalize_events(tx["events"])
    et = "dysonprotocol.whaleswap.v1.EventPoolSwap"
    assert et in ev and len(ev[et]) == 2, json.dumps(ev, indent=2)
    et = "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    assert et in ev and len(ev[et]) == 3, json.dumps(ev, indent=2)

    debits, credits = sum_transfers_for_addr(tx, taddr)
    assert isinstance(debits, list) and isinstance(credits, list), json.dumps(
        [debits, credits], indent=2
    )
    assert debits == [], json.dumps([debits, credits], indent=2)
    cred_map = {}
    for amt, den in credits:
        cred_map[den] = cred_map.get(den, 0) + int(amt)

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
