import json
from decimal import Decimal, ROUND_CEILING


def test_concentrated_swap_does_not_panic(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]

    # Creator and taker
    [creator_name, creator_addr] = generate_account("amm_conc_creator")
    faucet(creator_addr, amount=2_000_000)
    [taker_name, taker_addr] = generate_account("amm_conc_taker")
    faucet(taker_addr, amount=2_000_000)

    # Mint a custom denom and create a concentrated pool with tight band
    custom = register_name(dysond, creator_name, creator_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = Decimal(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = Decimal(1000)
    mint_fee = int((units * fee_per_unit).to_integral_value(rounding=ROUND_CEILING))
    mint = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{int(units)}{custom}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        creator_name,
    )
    assert mint.get("code", 1) == 0, f"mint-coins failed: {json.dumps(mint, indent=2)}"

    # Create pool: coins sorted lexicographically become [custom, udys]. Initial price P=udys/custom=1000/500=2.
    # Set band 1 < P < 3 with denoms matching [base=custom, quote=udys].
    create = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        "1000udys",
        "--coins",
        f"500{custom}",
        "--min-price",
        f"1{custom}",  # base
        "--min-price",
        f"1udys",  # quote => 1/1 = 1.0
        "--max-price",
        f"1{custom}",  # base
        "--max-price",
        f"3udys",  # quote => 3/1 = 3.0
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "3.0",
        "--max-borrow-percent",
        "0.8",
        "--from",
        creator_name,
    )
    assert (
        create.get("code", 1) == 0
    ), f"create-pool failed: {json.dumps(create, indent=2)}"

    pools = dysond("query", "whaleswap", "pools")
    ids = [int(p.get("pool_id")) for p in pools.get("pools", [])]
    assert ids, f"no pools found after create: {json.dumps(pools, indent=2)}"
    pool_id = max(ids)

    # Aggressive swap that could previously push reserve to zero and trigger panic
    legs = json.dumps(
        {"pool_id": pool_id, "swap_in": {"denom": "udys", "amount": "900"}}
    )
    swap = dysond(
        "tx",
        "whaleswap",
        "swap",
        "--max-input",
        "900udys",
        "--legs",
        legs,
        "--min-output",
        f"1{custom}",
        "--from",
        taker_name,
    )
    msg = json.dumps(swap, indent=2)
    assert "index out of range" not in msg and "panic" not in msg, msg
