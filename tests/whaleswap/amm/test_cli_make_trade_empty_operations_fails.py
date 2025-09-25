import json


def test_make_trade_empty_operations_fails(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    taker_name = env["acc1"]["name"]

    # No --op flags provided
    out = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--from",
        taker_name,
        "--gas",
        "auto",
        raw=True,
    )

    # Expect failure with a helpful error mentioning operations
    assert isinstance(out, str), f"expected error string, got: {out}"
    low = (out or "").lower()
    assert "operations must be non-empty" in low, f"unexpected error message: {out}"
