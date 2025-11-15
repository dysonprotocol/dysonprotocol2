import json


def test_add_liquidity_v2(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account("amm_owner2")
    faucet(owner_addr, amount=2_000_000)
    name = register_name(dysond, owner_name, owner_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 1000
    required_fee = int(units * fee_per_unit)
    mint = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{name}",
        "--mint-fee",
        f"{required_fee}udys",
        "--from",
        owner_name,
    )
    assert mint.get("code", 1) == 0, f"mint-coins failed: {json.dumps(mint, indent=2)}"

    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        "1000udys",
        "--coins",
        f"500{name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        owner_name,
    )
    assert tx.get("code", 1) == 0, f"create-pool failed: {json.dumps(tx, indent=2)}"
    pid = int(
        str(
            [
                a
                for e in tx["events"]
                if e["type"] == "dysonprotocol.whaleswap.v1.EventPoolCreated"
                for a in e["attributes"]
                if a["key"] == "pool_id"
            ][0]["value"]
        ).strip('"')
    )

    # Ensure amounts align with pool's canonical coin order using Pool.coins
    p_pre = dysond("query", "whaleswap", "pool", "--pool-id", str(pid))["pool"]
    coins = p_pre.get("coins", [])
    assert (
        isinstance(coins, list) and len(coins) == 2
    ), f"invalid pool coins: {json.dumps(p_pre, indent=2)}"

    # Build amounts using sorted denom mapping (no positional assumptions)
    sorted_denoms = sorted([name, "udys"])
    amount_map = {name: f"50{name}", "udys": "300udys"}
    a1 = amount_map[sorted_denoms[0]]
    a2 = amount_map[sorted_denoms[1]]

    # First, intentionally misproportional amounts – in v2 this SHOULD succeed with refunds
    # Compute expected refunds deterministically (no branching in test)
    def _amt(coin_str, denom):
        assert coin_str.endswith(
            denom
        ), f"coin '{coin_str}' must end with denom '{denom}'"
        return int(coin_str[: -len(denom)])

    exR1 = int(p_pre["coins"][0]["amount"])  # sorted_denoms[0] reserve
    exR2 = int(p_pre["coins"][1]["amount"])  # sorted_denoms[1] reserve
    add1_i = _amt(a1, sorted_denoms[0])
    add2_i = _amt(a2, sorted_denoms[1])
    # Ceil divisions to match keeper math; compute both sides and then take mins/max without branching
    targetA2 = (add1_i * exR2 + (exR1 - 1)) // exR1
    targetA1 = (add2_i * exR1 + (exR2 - 1)) // exR2
    eff1 = min(add1_i, targetA1)
    eff2 = min(add2_i, targetA2)
    refund1 = add1_i - eff1
    refund2 = add2_i - eff2

    # Capture owner balances before tx using sorted denoms
    def _bal(addr, denom):
        b = dysond("query", "bank", "balances", addr)
        blist = b.get("balances", [])
        return sum(
            [int(c.get("amount", "0")) * int(c.get("denom") == denom) for c in blist]
        )

    pre_b0 = _bal(owner_addr, sorted_denoms[0])
    pre_b1 = _bal(owner_addr, sorted_denoms[1])

    bad = dysond(
        "tx",
        "whaleswap",
        "add-liquidity",
        "--pool-id",
        str(pid),
        "--amounts",
        a1,
        "--amounts",
        a2,
        "--from",
        owner_name,
    )
    assert (
        bad.get("code", 1) == 0
    ), f"misproportional add-liquidity should succeed with refunds: {json.dumps(bad, indent=2)}"
    # Verify minted shares > 0 using event_dict built from events
    event_dict = {
        e.get("type"): {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in bad.get("events", [])
    }
    minted_shares = int(
        str(
            event_dict.get(
                "dysonprotocol.whaleswap.v1.EventPoolLiquidityAdded", {}
            ).get("shares", "0")
        ).strip('"')
    )
    assert (
        minted_shares > 0
    ), f"no shares minted on misproportional add: {json.dumps(bad, indent=2)}"

    # Verify owner balance deltas equal effective adds (refunds implied)
    post_b0 = _bal(owner_addr, sorted_denoms[0])
    post_b1 = _bal(owner_addr, sorted_denoms[1])
    delta0 = pre_b0 - post_b0
    delta1 = pre_b1 - post_b1
    assert (
        delta0 == eff1 and delta1 == eff2
    ), f"unexpected balance deltas: expected ({eff1},{eff2}) got ({delta0},{delta1}); tx: {json.dumps(bad, indent=2)}"

    # Now add proportionally to current reserves using sorted denoms
    prop_amount_map = {name: f"50{name}", "udys": "100udys"}
    prop_a = prop_amount_map[sorted_denoms[0]]
    prop_b = prop_amount_map[sorted_denoms[1]]
    add_ok = dysond(
        "tx",
        "whaleswap",
        "add-liquidity",
        "--pool-id",
        str(pid),
        "--amounts",
        prop_a,
        "--amounts",
        prop_b,
        "--from",
        owner_name,
    )
    assert (
        add_ok.get("code", 1) == 0
    ), f"add-liquidity proportional failed: {json.dumps(add_ok, indent=2)}"
    # Verify shares > 0 via the same event_dict approach
    event_dict2 = {
        e.get("type"): {a.get("key"): a.get("value") for a in e.get("attributes", [])}
        for e in add_ok.get("events", [])
    }
    minted_shares2 = int(
        str(
            event_dict2.get(
                "dysonprotocol.whaleswap.v1.EventPoolLiquidityAdded", {}
            ).get("shares", "0")
        ).strip('"')
    )
    assert minted_shares2 > 0, f"no shares minted: {json.dumps(add_ok, indent=2)}"
