import json
import pytest


def test_make_trade_v3_boundary_fail(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker_name = env["acc3"]["name"]
    zero = "0.000000000000000000"

    # Invalid bound (0% drop allowed) should be rejected by validation.
    with pytest.raises(Exception, match="--bound-percent value for"):
        dysond(
            "tx",
            "whaleswap",
            "create-pool",
            "--coins",
            f"100{a}",
            "--coins",
            f"100{b}",
            "--bound-percent",
            zero,
            "--bound-percent",
            zero,
            "--min-collateral-ratio",
            "1.5",
            "--max-borrow-percent",
            "0.8",
            "--from",
            taker_name,
            "--gas",
            "auto",
        )
