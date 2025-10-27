import json
import pytest


def test_make_trade_v3_boundary_fail(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker_name = env["acc3"]["name"]

    # Initial price is 1.0 (100b/100a). Set band edges equal to 1.0 to enforce boundary fail.
    with pytest.raises(Exception, match="max_price must be greater than min_price"):
        dysond(
            "tx",
            "whaleswap",
            "create-pool",
            "--coins",
            f"100{a}",
            "--coins",
            f"100{b}",
            "--min-price",
            f"1{a}",
            "--min-price",
            f"1{b}",
            "--max-price",
            f"1{a}",
            "--max-price",
            f"1{b}",
            "--min-collateral-ratio",
            "1.5",
            "--max-leverage-ratio",
            "3.0",
            "--max-borrow-percent",
            "0.8",
            "--from",
            taker_name,
            "--gas",
            "auto",
        )
