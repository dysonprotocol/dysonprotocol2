import json
import pytest


def test_create_pool_reject_zero_width_band(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [creator_name, creator_addr] = generate_account("amm_creator")
    faucet(creator_addr, amount=2_000_000)

    name = register_name(dysond, creator_name, creator_addr, "1000udys")
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
        creator_name,
    )
    assert mint.get("code", 1) == 0, f"mint-coins failed: {json.dumps(mint, indent=2)}"

    zero = "0.000000000000000000"
    with pytest.raises(Exception, match="0 < x <= 1"):
        dysond(
            "tx",
            "whaleswap",
            "create-pool",
            "--coins",
            "1000udys",
            "--coins",
            f"500{name}",
            "--bound-percent",
            zero,
            "--bound-percent",
            zero,
            "--min-collateral-ratio",
            "1.5",
            "--max-leverage-ratio",
            "3.0",
            "--max-borrow-percent",
            "0.8",
            "--from",
            creator_name,
        )
