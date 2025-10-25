import pytest


def test_make_trade_invalid_op_empty_object_fails(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    taker_name = env["acc1"]["name"]

    with pytest.raises(Exception, match="operation must be swap, take, or auction"):
        dysond(
            "tx",
            "whaleswap",
            "make-trade",
            "--op",
            "{}",
            "--from",
            taker_name,
            "--gas",
            "auto",
        )
