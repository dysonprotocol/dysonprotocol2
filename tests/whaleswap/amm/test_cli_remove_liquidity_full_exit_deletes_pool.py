import json


def test_remove_liquidity_full_exit_deletes_pool(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [owner_name, owner_addr] = generate_account("amm_owner3")
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
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        owner_name,
    )
    assert tx.get("code", 1) == 0, f"create-pool failed: {json.dumps(tx, indent=2)}"
    pool_id = int(
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

    # Respect canonical pool denom order using Pool.coins (sorted by denom)
    p_pre = dysond("query", "whaleswap", "pool", "--pool-id", str(pool_id))["pool"]
    coins = p_pre.get("coins", [])
    assert isinstance(coins, list) and len(coins) == 2, f"invalid pool coins: {p_pre}"

    # Build amounts using sorted denom mapping (no positional assumptions)
    sorted_denoms = sorted([name, "udys"])
    amount_map = {name: f"100{name}", "udys": "200udys"}
    amount1 = amount_map[sorted_denoms[0]]
    amount2 = amount_map[sorted_denoms[1]]
    add = dysond(
        "tx",
        "whaleswap",
        "add-liquidity",
        "--pool-id",
        str(pool_id),
        "--amounts",
        amount1,
        "--amounts",
        amount2,
        "--from",
        owner_name,
    )
    assert add.get("code", 1) == 0, f"add-liquidity failed: {json.dumps(add, indent=2)}"

    p = dysond("query", "whaleswap", "pool", "--pool-id", str(pool_id))["pool"]
    shares = p["shares_denom"]
    bals = dysond("query", "bank", "balances", owner_addr)
    share_bal = [b for b in bals.get("balances", []) if b.get("denom") == shares]
    assert share_bal, f"owner has no shares balance: {json.dumps(bals, indent=2)}"
    amt = share_bal[0]["amount"]

    rem = dysond(
        "tx",
        "whaleswap",
        "remove-liquidity",
        "--pool-id",
        str(pool_id),
        "--shares",
        amt,
        "--from",
        owner_name,
    )
    assert (
        rem.get("code", 1) == 0
    ), f"remove-liquidity failed: {json.dumps(rem, indent=2)}"
    q = dysond("query", "whaleswap", "pool", "--pool-id", str(pool_id))
    # After full exit, querying the pool must return a deterministic not-found error string
    assert isinstance(
        q, str
    ), f"expected error string on deleted pool: {json.dumps(q, indent=2)}"
    assert (
        "pool not found" in q.lower()
    ), f"unexpected response for deleted pool: {json.dumps(q, indent=2)}"
