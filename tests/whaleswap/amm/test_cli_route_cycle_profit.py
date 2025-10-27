import json
from decimal import Decimal, ROUND_CEILING

from tests.whaleswap.amm.normalize_events import normalize_events
from tests.whaleswap.amm.parse_amounts_multi import sum_transfers_for_addr


def _mint(dysond, owner, denom, units):
    params = dysond("query", "nameservice", "params")
    assert isinstance(params, dict), json.dumps(params, indent=2)
    assert "params" in params and isinstance(params["params"], dict), json.dumps(
        params, indent=2
    )
    fee_per = Decimal(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
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
        owner,
    )
    assert isinstance(res, dict), json.dumps(res, indent=2)
    assert res["code"] == 0, json.dumps(res, indent=2)


def _create_pool(dysond, owner, denom_x, amt_x, denom_y, amt_y):
    _mint(dysond, owner, denom_x, amt_x)
    _mint(dysond, owner, denom_y, amt_y)
    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"{amt_x}{denom_x}",
        "--coins",
        f"{amt_y}{denom_y}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        owner,
    )
    assert isinstance(tx, dict), json.dumps(tx, indent=2)
    assert tx["code"] == 0, json.dumps(tx, indent=2)
    assert "events" in tx and isinstance(tx["events"], list), json.dumps(tx, indent=2)
    ev = normalize_events(tx["events"])
    et = "dysonprotocol.whaleswap.v1.EventPoolCreated"
    assert et in ev and len(ev[et]) == 1, json.dumps(ev, indent=2)
    pid = int(ev[et][0]["pool_id"])
    return pid


def test_route_cycle_profit_no_inputs(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]

    # Creator and trader
    [creator, creator_addr] = generate_account("cycle_creator")
    faucet(creator_addr, amount=2_000_000)
    [trader, trader_addr] = generate_account("cycle_trader")
    faucet(trader_addr, amount=1_000_000)

    # Three custom denoms A, B, C
    A = register_name(dysond, creator, creator_addr, "1000udys")
    B = register_name(dysond, creator, creator_addr, "1000udys")
    C = register_name(dysond, creator, creator_addr, "1000udys")

    # Skewed pools to bias each edge favorably
    ab_id = _create_pool(dysond, creator, A, 100, B, 100000)
    bc_id = _create_pool(dysond, creator, B, 100, C, 100000)
    ca_id = _create_pool(dysond, creator, C, 100, A, 110000)

    # Record trader balances before
    before = dysond("query", "bank", "balances", trader_addr)
    assert isinstance(before, dict) and isinstance(
        before["balances"], list
    ), json.dumps(before, indent=2)
    pre = {row["denom"]: int(row["amount"]) for row in before["balances"]}

    # Legs for circular route; no inputs provided
    leg_ab = json.dumps({"pool_id": ab_id, "swap_in": {"denom": A, "amount": "10"}})
    leg_bc = json.dumps({"pool_id": bc_id, "swap_in": {"denom": B, "amount": "10"}})
    leg_ca = json.dumps({"pool_id": ca_id, "swap_in": {"denom": C, "amount": "10"}})

    tx = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--legs",
        leg_ab,
        "--legs",
        leg_bc,
        "--legs",
        leg_ca,
        "--min-output",
        f"1{A}",
        "--from",
        trader,
    )
    assert isinstance(tx, dict), json.dumps(tx, indent=2)
    assert tx["code"] == 0, json.dumps(tx, indent=2)
    assert "events" in tx and isinstance(tx["events"], list), json.dumps(tx, indent=2)

    ev = normalize_events(tx["events"])
    et = "dysonprotocol.whaleswap.v1.EventPoolSwap"
    assert et in ev and len(ev[et]) == 3, json.dumps(ev, indent=2)
    et = "dysonprotocol.whaleswap.v1.EventTradeRecorded"
    # Now 1 Trade with 3 operations, not 3 Trades
    assert (
        et in ev and len(ev[et]) == 1
    ), f"expected 1 EventTradeRecorded: {json.dumps(ev, indent=2)}"
    attrs = ev[et][0]
    assert (
        int(attrs.get("num_operations", 0)) == 3
    ), f"expected 3 operations: {json.dumps(attrs, indent=2)}"

    # Exact net flows from transfer events
    debits, credits = sum_transfers_for_addr(tx, trader_addr)
    assert isinstance(debits, list) and isinstance(credits, list), json.dumps(
        [debits, credits], indent=2
    )
    assert debits == [], json.dumps([debits, credits], indent=2)
    cred_map = {A: 0, B: 0, C: 0}
    for amt, den in credits:
        cred_map[den] = cred_map[den] + int(amt)

    after = dysond("query", "bank", "balances", trader_addr)
    assert isinstance(after, dict) and isinstance(after["balances"], list), json.dumps(
        after, indent=2
    )
    post = {row["denom"]: int(row["amount"]) for row in after["balances"]}

    targets = [A, B, C]
    pre_z = {d: 0 for d in targets} | pre
    post_z = {d: 0 for d in targets} | post
    for d in targets:
        delta = post_z[d] - pre_z[d]
        exp = cred_map[d]
        assert (
            delta == exp
        ), f"{d} delta mismatch: got {delta}, expected {exp}; transfers={json.dumps([debits, credits], indent=2)}"
