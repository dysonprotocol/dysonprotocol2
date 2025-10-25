import pytest


def test_make_trade_empty_operations_fails(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    taker_name = env["acc1"]["name"]

    # No --op flags provided
    with pytest.raises(Exception, match="operations must be non-empty"):
        dysond(
            "tx",
            "whaleswap",
            "make-trade",
            "--from",
            taker_name,
            "--gas",
            "auto",
        )
